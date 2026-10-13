"""
Bit-exact integer model of rtl/snn_core.v (2-layer LIF SNN, direct encoding).

  hidden: I1[h] = sum_i x[i] * W1[i][h]          (x[0] is the always-on bias line)
  for t in 0..T-1:
     v1 = v1 - (v1 >>> LEAK) + I1 ; s1 = v1 >= TH1 ; if s1: v1 = 0
     I2 = B2 + sum_h s1[h] * W2[h]
     v2 = v2 - (v2 >>> LEAK) + I2 ; s2 = v2 >= TH2 ; if s2: v2 = 0 ; cnt += s2
  malicious = cnt[1] > cnt[0]  or  (cnt[1] == cnt[0] and v2[1] > v2[0])

All weights int8, membranes V_W-bit two's complement (no overflow possible for
the chosen sizes -- asserted here).
"""
N_IN, N_HID, N_OUT = 64, 16, 2
T_STEPS = 8
LEAK = 2
V_W = 20
VMAX, VMIN = (1 << (V_W - 1)) - 1, -(1 << (V_W - 1))


def infer(x, P, trace=False):
    W1, W2, B2, th1, th2 = P["W1"], P["W2"], P["B2"], P["TH1"], P["TH2"]
    T, leak = P.get("T", T_STEPS), P.get("LEAK", LEAK)
    H = len(W1[0])
    I1 = [sum(W1[i][h] for i in range(len(x)) if x[i]) for h in range(H)]
    v1 = [0] * H
    v2 = [0] * N_OUT
    cnt = [0] * N_OUT
    for t in range(T):
        s1 = []
        for h in range(H):
            v = v1[h] - (v1[h] >> leak) + I1[h]
            assert VMIN <= v <= VMAX
            if v >= th1:
                s1.append(1)
                v = 0
            else:
                s1.append(0)
            v1[h] = v
        for o in range(N_OUT):
            I2 = B2[o] + sum(W2[h][o] for h in range(H) if s1[h])
            v = v2[o] - (v2[o] >> leak) + I2
            assert VMIN <= v <= VMAX
            if v >= th2:
                cnt[o] += 1
                v = 0
            v2[o] = v
    mal = int(cnt[1] > cnt[0] or (cnt[1] == cnt[0] and v2[1] > v2[0]))
    return mal, cnt, v2
