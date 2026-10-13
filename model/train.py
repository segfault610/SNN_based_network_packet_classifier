"""
Quantization-aware surrogate-gradient training of the packet SNN.
Forward pass reproduces the integer hardware arithmetic exactly (int8 weights
via STE rounding, arithmetic-shift leak via STE floor, hard reset to 0).

Usage: .venv/bin/python model/train.py                      synthetic traffic
       .venv/bin/python model/train.py --data a.npz [b.npz]  real captures (model/pcap_io.py)
       -> writes model/params.json
"""
import json, os, sys, time
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(__file__))
import argparse
import gen_traffic, pktfeat, snn_int, pcap_io

H, T, LEAK = snn_int.N_HID, snn_int.T_STEPS, snn_int.LEAK
TH1, TH2 = 256, 128
torch.manual_seed(0)


def dataset(seed, n):
    s = gen_traffic.Gen(seed).stream(n)
    X = np.array(pktfeat.encode_stream([f for f, _, _ in s]), dtype=np.float32)
    y = np.array([l for _, l, _ in s], dtype=np.int64)
    k = np.array([a for _, _, a in s])
    return X, y, k


class Spike(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, a):
        ctx.save_for_backward(x)
        ctx.a = a
        return (x >= 0).float()

    @staticmethod
    def backward(ctx, g):
        (x,) = ctx.saved_tensors
        a = ctx.a
        return g / (a * (1 + x.abs() / a) ** 2), None


def ste_round(w):
    return (w.round().clamp(-128, 127) - w).detach() + w


def ste_floor(x):
    return (x.floor() - x).detach() + x


def forward(X, W1, W2, B2):
    w1, w2, b2 = ste_round(W1), ste_round(W2), ste_round(B2)
    I1 = X @ w1
    v1 = torch.zeros_like(I1)
    v2 = torch.zeros(X.shape[0], 2)
    cnt = torch.zeros(X.shape[0], 2)
    for _ in range(T):
        v1 = v1 - ste_floor(v1 / (1 << LEAK)) + I1
        s1 = Spike.apply(v1 - TH1, TH1 / 4)
        v1 = v1 * (1 - s1.detach())
        v2 = v2 - ste_floor(v2 / (1 << LEAK)) + s1 @ w2 + b2
        s2 = Spike.apply(v2 - TH2, TH2 / 4)
        v2 = v2 * (1 - s2.detach())
        cnt = cnt + s2
    return cnt, v2


def to_params(W1, W2, B2):
    q = lambda t: t.detach().round().clamp(-128, 127).int().tolist()
    return dict(W1=q(W1), W2=q(W2), B2=q(B2), TH1=TH1, TH2=TH2, T=T, LEAK=LEAK,
                N_IN=pktfeat.N_IN, N_HID=H)


def evaluate(P, X, y, k, tag):
    pred = np.array([snn_int.infer(list(map(int, x)), P)[0] for x in X])
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    acc = (tp + tn) / len(y)
    print(f"[{tag}] int-model acc={acc:.4f}  TPR(detect)={tp/max(1,tp+fn):.4f}  FPR={fp/max(1,fp+tn):.4f}  "
          f"(tp={tp} fp={fp} tn={tn} fn={fn})")
    per = {}
    for a in sorted(set(k)):
        m = k == a
        per[a] = float((pred[m] == y[m]).mean())
    print("   per-class accuracy:", {a: round(v, 3) for a, v in per.items()})
    return dict(acc=acc, tpr=tp / max(1, tp + fn), fpr=fp / max(1, fp + tn), per_class=per)


def real_dataset(paths):
    """Encode each capture in arrival order, then split chronologically 70/15/15."""
    parts = [[], [], []]
    for p in paths:
        frames, y, k = pcap_io.load_npz(p)
        X = np.array(pktfeat.encode_stream(frames), dtype=np.float32)
        n = len(y); a, b = int(n * 0.70), int(n * 0.85)
        for i, sl in enumerate((slice(0, a), slice(a, b), slice(b, n))):
            parts[i].append((X[sl], y[sl].astype(np.int64), np.asarray(k[sl])))
    return [tuple(np.concatenate([q[j] for q in part]) for j in range(3)) for part in parts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="*", help="npz files from pcap_io.py (default: synthetic)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "params.json"))
    args = ap.parse_args()
    t0 = time.time()
    if args.data:
        (Xtr, ytr, _), (Xva, yva, kva), test = real_dataset(args.data)
    else:
        Xtr, ytr, _ = dataset(1, 60000)
        Xva, yva, kva = dataset(2, 20000)
        test = None
    print(f"data: train {len(ytr)} (mal {ytr.mean():.3f}), val {len(yva)}  [{time.time()-t0:.1f}s]")
    Xt, yt = torch.tensor(Xtr), torch.tensor(ytr)
    W1 = torch.nn.Parameter(torch.randn(pktfeat.N_IN, H) * 30)
    W2 = torch.nn.Parameter(torch.randn(H, 2) * 30)
    B2 = torch.nn.Parameter(torch.zeros(2))
    opt = torch.optim.Adam([W1, W2, B2], lr=1.0)
    E = args.epochs
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, E)
    cw = torch.tensor([1.0, float((ytr == 0).sum() / max(1, (ytr == 1).sum())) ** 0.5])
    for ep in range(E):
        perm = torch.randperm(len(yt))
        tot = 0.0
        for i in range(0, len(yt), 256):
            idx = perm[i:i + 256]
            cnt, v2 = forward(Xt[idx], W1, W2, B2)
            logits = cnt + 0.5 * v2 / TH2
            loss = torch.nn.functional.cross_entropy(logits, yt[idx], weight=cw)
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(idx)
        sched.step()
        if ep % 5 == 4 or ep == E - 1:
            with torch.no_grad():
                c, v = forward(torch.tensor(Xva), W1, W2, B2)
                pred = ((c[:, 1] > c[:, 0]) | ((c[:, 1] == c[:, 0]) & (v[:, 1] > v[:, 0]))).long().numpy()
            print(f"ep {ep+1:2d} loss {tot/len(yt):.4f}  val acc {(pred == yva).mean():.4f}")
    P = to_params(W1, W2, B2)
    P["data"] = args.data or "synthetic"
    P["metrics_val"] = evaluate(P, Xva, yva, kva, "val")
    Xte, yte, kte = test if test is not None else dataset(3, 20000)
    P["metrics_test"] = evaluate(P, Xte, yte, kte, "test")
    json.dump(P, open(args.out, "w"), indent=1)
    print(f"saved {args.out}  [{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
