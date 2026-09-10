#!/usr/bin/env python3
# 核實 note_v1.tex 一句: G₃ 頂點 #246 同 #1641 浮點距離 1.00000062 但精確唔係 1 (Phase 2 近似陷阱)
import sys, os
sys.path.insert(0, os.path.expanduser("~/hadwiger/phase2"))
from exactfield import read_cvtx
import mpmath as mp
F, P = read_cvtx(os.path.expanduser("~/hadwiger/phase2/out/haugland/G3.cvtx"))
a, b = P[246 - 1], P[1641 - 1]
d2 = (a - b).norm2()
print("exact |z246 - z1641|^2 == 1 ?", d2.is_one(), "; d^2 - 1 (float) =", (d2 - 1).to_float())
mp.mp.dps = 40
za, zb = a.to_mpc(40), b.to_mpc(40)
d = abs(za - zb)
print("distance (40 digits):", mp.nstr(d, 20))
print("float distance:", abs(a.to_float() - b.to_float()))
