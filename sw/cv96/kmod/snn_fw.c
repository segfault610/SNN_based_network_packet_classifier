// SPDX-License-Identifier: GPL-2.0
/*
 * snn_fw - SNN packet firewall hook for the Chameleon96 (Cyclone V SoC).
 *
 * Registers an rx_handler on a network interface (default wlan0). For every
 * received frame - right after the NIC driver, before the IP stack, sockets or
 * any user-space program sees it - the first <=128 bytes are sent to the FPGA
 * SNN classifier (rtl/snn_lookaside_avmm.v) together with the real length.
 * Frames classified malicious are freed (drop=1) or just counted (drop=0).
 *
 *   insmod snn_fw.ko [iface=wlan0] [drop=1] [fw=snn_fw.bin] [base=0xff210000]
 *   cat /proc/snn_fw          ; echo "drop 0" > /proc/snn_fw
 *
 * Weights: /lib/firmware/<fw> = little-endian u32 (word_addr, data) pairs,
 * produced by model/export.py. Fail-open: if the accelerator does not answer
 * in time the frame is passed and counted as a timeout.
 */
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/netdevice.h>
#include <linux/etherdevice.h>
#include <linux/skbuff.h>
#include <linux/io.h>
#include <linux/firmware.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/uaccess.h>
#include <linux/spinlock.h>
#include <linux/delay.h>
#include <linux/if_vlan.h>
#include <linux/rtnetlink.h>
#include <linux/unaligned.h>
#include "../snn_regs.h"

static char *iface = "wlan0";
module_param(iface, charp, 0444);
MODULE_PARM_DESC(iface, "network interface to protect");
static bool drop = true;
module_param(drop, bool, 0644);
MODULE_PARM_DESC(drop, "1 = drop malicious frames, 0 = monitor only");
static char *fw = "snn_fw.bin";
module_param(fw, charp, 0444);
MODULE_PARM_DESC(fw, "weight/config blob in /lib/firmware (empty = keep FPGA state)");
static unsigned long base = SNN_PHYS_BASE;
module_param(base, ulong, 0444);
MODULE_PARM_DESC(base, "physical base address of the SNN accelerator");
static unsigned int poll_max = 4000;
module_param(poll_max, uint, 0644);
MODULE_PARM_DESC(poll_max, "max register polls before failing open");

static void __iomem *regs;
static struct net_device *ndev;
static DEFINE_SPINLOCK(hw_lock);
static u8 next_tag;

static struct {
	u64 seen, malicious, dropped, timeouts, tag_err, nonlinear;
	u64 cycles_total;                       /* jiffies-free: ns via ktime */
} st;

static inline u32 rd(u32 off)          { return ioread32(regs + off); }
static inline void wr(u32 off, u32 v)  { iowrite32(v, regs + off); }

/* Returns verdict word (SNN_V_VALID set) or 0 on timeout. Caller holds hw_lock. */
static u32 snn_classify(const u8 *hdr, unsigned int n, unsigned int frame_len)
{
	unsigned int i, w;
	u32 v = 0;
	u8 tag = next_tag++;

	for (i = 0; i < poll_max; i++)
		if (rd(SNN_STATUS) & SNN_STATUS_READY)
			break;
	if (i == poll_max)
		return 0;

	for (w = 0; w < (n + 3) / 4; w++) {
		u32 word = 0;
		unsigned int k;

		for (k = 0; k < 4 && 4 * w + k < n; k++)
			word |= (u32)hdr[4 * w + k] << (8 * k);
		wr(SNN_HDR(w), word);
	}
	wr(SNN_SUBMIT, SNN_SUBMIT_WORD(frame_len, n, tag));

	for (i = 0; i < poll_max; i++) {
		v = rd(SNN_VERDICT);
		if (v & SNN_V_VALID)
			break;
	}
	if (!(v & SNN_V_VALID))
		return 0;
	if (SNN_V_TAG(v) != tag) {
		st.tag_err++;
		return 0;
	}
	return v;
}

static rx_handler_result_t snn_rx_handler(struct sk_buff **pskb)
{
	struct sk_buff *skb = *pskb;
	u8 hdr[SNN_HDR_MAX];
	unsigned int mhl, len, n;
	u64 t0;
	u32 v;

	if (unlikely(skb->pkt_type == PACKET_LOOPBACK))
		return RX_HANDLER_PASS;

	mhl = skb_mac_header_was_set(skb) ? skb_mac_header_len(skb) : 0;
	if (mhl != ETH_HLEN && mhl != VLAN_ETH_HLEN)
		return RX_HANDLER_PASS;                 /* not an Ethernet frame */
	len = skb->len + mhl;
	n = min_t(unsigned int, len, SNN_HDR_MAX);

	memcpy(hdr, skb_mac_header(skb), mhl);
	if (skb_copy_bits(skb, 0, hdr + mhl, n - mhl)) {
		st.nonlinear++;
		return RX_HANDLER_PASS;
	}

	t0 = ktime_get_ns();
	spin_lock(&hw_lock);
	v = snn_classify(hdr, n, len);
	st.seen++;
	if (!v)
		st.timeouts++;
	else if (v & SNN_V_MAL)
		st.malicious++;
	st.cycles_total += ktime_get_ns() - t0;
	spin_unlock(&hw_lock);

	if (v && (v & SNN_V_MAL) && READ_ONCE(drop)) {
		st.dropped++;
		kfree_skb(skb);
		*pskb = NULL;
		return RX_HANDLER_CONSUMED;
	}
	return RX_HANDLER_PASS;
}

static int snn_load_fw(struct device *dev)
{
	const struct firmware *f;
	size_t i;
	int ret;

	if (!fw || !*fw)
		return 0;
	ret = request_firmware(&f, fw, dev);
	if (ret) {
		pr_warn("snn_fw: firmware %s not found (%d), keeping current weights\n", fw, ret);
		return 0;
	}
	if (f->size % 8) {
		release_firmware(f);
		pr_err("snn_fw: bad firmware size %zu\n", f->size);
		return -EINVAL;
	}
	spin_lock_bh(&hw_lock);
	for (i = 0; i < f->size; i += 8) {
		u32 a = get_unaligned_le32(f->data + i);
		u32 d = get_unaligned_le32(f->data + i + 4);

		wr(SNN_W(a & 0x3FF), d);
	}
	spin_unlock_bh(&hw_lock);
	pr_info("snn_fw: loaded %zu config words from %s\n", f->size / 8, fw);
	release_firmware(f);
	return 0;
}

static int snn_proc_show(struct seq_file *m, void *v)
{
	u32 sub, rej, mal;

	spin_lock_bh(&hw_lock);
	sub = rd(SNN_ST_SUBMITTED);
	rej = rd(SNN_ST_REJECTED);
	mal = rd(SNN_ST_MALICIOUS);
	spin_unlock_bh(&hw_lock);
	seq_printf(m, "iface      %s\nmode       %s\n", iface, READ_ONCE(drop) ? "drop" : "monitor");
	seq_printf(m, "seen       %llu\nmalicious  %llu\ndropped    %llu\ntimeouts   %llu\ntag_err    %llu\nnonlinear  %llu\n",
		   st.seen, st.malicious, st.dropped, st.timeouts, st.tag_err, st.nonlinear);
	seq_printf(m, "avg_ns     %llu\n", st.seen ? div64_u64(st.cycles_total, st.seen) : 0);
	seq_printf(m, "hw_submitted %u\nhw_rejected  %u\nhw_malicious %u\n", sub, rej, mal);
	return 0;
}

static int snn_proc_open(struct inode *inode, struct file *file)
{
	return single_open(file, snn_proc_show, NULL);
}

static ssize_t snn_proc_write(struct file *file, const char __user *ubuf, size_t cnt, loff_t *ppos)
{
	char buf[32];
	unsigned int val;

	if (cnt >= sizeof(buf))
		return -EINVAL;
	if (copy_from_user(buf, ubuf, cnt))
		return -EFAULT;
	buf[cnt] = 0;
	if (sscanf(buf, "drop %u", &val) == 1)
		WRITE_ONCE(drop, !!val);
	else if (!strncmp(buf, "reload", 6))
		snn_load_fw(&ndev->dev);
	else
		return -EINVAL;
	return cnt;
}

static const struct proc_ops snn_proc_ops = {
	.proc_open    = snn_proc_open,
	.proc_read    = seq_read,
	.proc_lseek   = seq_lseek,
	.proc_release = single_release,
	.proc_write   = snn_proc_write,
};

static int __init snn_fw_init(void)
{
	u32 id;
	int ret;

	regs = ioremap(base, SNN_SPAN);
	if (!regs)
		return -ENOMEM;
	id = rd(SNN_ID);
	if (id != SNN_ID_VALUE) {
		pr_err("snn_fw: no accelerator at %#lx (ID %#x) - is the RBF loaded and the LW bridge enabled?\n",
		       base, id);
		ret = -ENODEV;
		goto err_unmap;
	}
	ndev = dev_get_by_name(&init_net, iface);
	if (!ndev) {
		pr_err("snn_fw: interface %s not found\n", iface);
		ret = -ENODEV;
		goto err_unmap;
	}
	ret = snn_load_fw(&ndev->dev);
	if (ret)
		goto err_put;

	rtnl_lock();
	ret = netdev_rx_handler_register(ndev, snn_rx_handler, NULL);
	rtnl_unlock();
	if (ret) {
		pr_err("snn_fw: %s already has an rx_handler (bridge/bond?) (%d)\n", iface, ret);
		goto err_put;
	}
	proc_create("snn_fw", 0644, NULL, &snn_proc_ops);
	pr_info("snn_fw: protecting %s, mode=%s\n", iface, drop ? "drop" : "monitor");
	return 0;

err_put:
	dev_put(ndev);
err_unmap:
	iounmap(regs);
	return ret;
}

static void __exit snn_fw_exit(void)
{
	remove_proc_entry("snn_fw", NULL);
	rtnl_lock();
	netdev_rx_handler_unregister(ndev);
	rtnl_unlock();
	synchronize_net();
	dev_put(ndev);
	iounmap(regs);
	pr_info("snn_fw: unloaded (seen %llu, dropped %llu)\n", st.seen, st.dropped);
}

module_init(snn_fw_init);
module_exit(snn_fw_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("SNN FPGA packet firewall rx hook");
