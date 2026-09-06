#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain.py —— 5-chromatic 認證鏈嘅 L2 + L3 (L1 = G1 pair 性質, 由 certify4 / cnc 另出)

L2: G3 入面 4 個 copy 嘅映射 φ_k (精確坐標): φ1(z) = z·e^{-iπ/3} − 1, φ2(z) = z·e^{iπ/3} + 1, φ3 = ρ∘φ1, φ4 = ρ∘φ2,
    ρ(w) = (w+1)(7+i√15)/8 − 1。機器核對: φ_k(V(G1)) ⊂ V(G3), 而且 E(G1) 每條邊映落 E(G3) (4 × 3985 條)。
    ⇒ 任何 G3 嘅 4 色染色限制喺 copy k 就係 G1 嘅 4 色染色 ⇒ (L1) col(A_k) ≠ col(B_k), A_k = φ_k(A), B_k = φ_k(B)。
L3: G3 4 色 CNF + 16 條引理子句 (¬x_{A_k,c} ∨ ¬x_{B_k,c}, k=1..4, c=1..4) → solver UNSAT → drat-trim VERIFIED。
L1 + L2 + L3 ⇒ G3 冇 4 色染色。

用法: python3 chain.py --haugland DIR --out DIR [--solver kissat] [--timeout 1800]
輸出: pairs.json (A_k, B_k 索引 + 坐標), L2.json, L3.cnf / L3.drat / L3.json
"""
import sys, os, json, time, argparse, subprocess, hashlib
from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exactfield import read_cvtx, load_edges, CycField
from certify4 import DRATTRIM_TIMEOUT, find_triangle, KISSAT, CADICAL, DRATTRIM

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--haugland", default=os.path.expanduser("~/hadwiger/phase2/out/haugland"))
    ap.add_argument("--out", default=os.path.expanduser("~/hadwiger/phase2/out/cert/chain"))
    ap.add_argument("--solver", default="kissat", choices=["kissat", "cadical"]); ap.add_argument("--timeout", type=float, default=1800)
    a = ap.parse_args()
    H, out = os.path.expanduser(a.haugland), os.path.expanduser(a.out); os.makedirs(out, exist_ok=True)
    F84, P1 = read_cvtx(os.path.join(H, "G1.cvtx"))
    F, P3 = read_cvtx(os.path.join(H, "G3.cvtx"))
    n1, E1 = load_edges(os.path.join(H, "G1.edge"))
    n3, E3 = load_edges(os.path.join(H, "G3.edge"))
    assert F84.N == 84 and F.N == 420 and len(P1) == n1 == 740 and len(P3) == n3 == 2131
    E3set = {frozenset(e) for e in E3}
    idx3 = {(z.num, z.den): i + 1 for i, z in enumerate(P3)}
    I = F.i_unit(); s15 = F.sqrt_int(15); s3 = F.sqrt_int(3)
    rho_mul = (F.rational(7) + I * s15) * Fraction(1, 8)
    one = F.one()
    rho = lambda w: (w + one) * rho_mul - one
    phi = {1: lambda z: z * F.zeta(350) - one,          # e^{-iπ/3} = ζ84^70 = ζ420^350
           2: lambda z: z * F.zeta(70) + one,           # e^{iπ/3} = ζ84^14 = ζ420^70
           3: lambda z: rho(z * F.zeta(350) - one),
           4: lambda z: rho(z * F.zeta(70) + one)}
    A = F.zero(); B = I * s3
    iA = [i for i, z in enumerate(P1) if F.embed(z) == A]; iB = [i for i, z in enumerate(P1) if F.embed(z) == B]
    assert len(iA) == 1 and len(iB) == 1
    print(f"[L2] G1: A=(0,0) #{iA[0] + 1}, B=(0,√3) #{iB[0] + 1}; G3: {n3} 點 {len(E3)} 邊", flush=True)
    pairs = {}
    l2 = {}
    t0 = time.time()
    for k in (1, 2, 3, 4):
        img = []
        for z in P1:
            w = phi[k](F.embed(z))
            j = idx3.get((w.num, w.den))
            assert j is not None, f"copy {k}: φ 嘅像唔喺 V(G3)"
            img.append(j)
        assert len(set(img)) == n1, f"copy {k}: φ 唔係 injective"
        bad = [(u, v) for u, v in E1 if frozenset((img[u - 1], img[v - 1])) not in E3set]
        assert not bad, f"copy {k}: {len(bad)} 條 G1 邊冇映落 E(G3), 例如 {bad[:3]}"
        Ak, Bk = img[iA[0]], img[iB[0]]
        za, zb = P3[Ak - 1].to_float(), P3[Bk - 1].to_float()
        pairs[k] = {"A": Ak, "B": Bk, "A_xy": [round(za.real, 6), round(za.imag, 6)], "B_xy": [round(zb.real, 6), round(zb.imag, 6)]}
        l2[k] = {"vertices_mapped": n1, "edges_checked": len(E1), "A_k": Ak, "B_k": Bk}
        print(f"[L2] copy {k}: φ_{k}(V(G1)) ⊂ V(G3) (740 點, injective) ✓, E(G1) 3985/3985 條映落 E(G3) ✓; "
              f"A_{k} = #{Ak} {pairs[k]['A_xy']}, B_{k} = #{Bk} {pairs[k]['B_xy']}", flush=True)
    assert (P3[pairs[1]["A"] - 1] - P3[pairs[2]["A"] - 1]).norm2() == F.rational(4), "(−1,0),(1,0) 距離應該係 2"
    json.dump({"pairs": pairs, "L2": l2, "sha": {"G1.cvtx": sha(os.path.join(H, "G1.cvtx")), "G1.edge": sha(os.path.join(H, "G1.edge")),
               "G3.cvtx": sha(os.path.join(H, "G3.cvtx")), "G3.edge": sha(os.path.join(H, "G3.edge"))},
               "t_s": round(time.time() - t0, 1)}, open(os.path.join(out, "pairs.json"), "w"), indent=1)
    # L3
    k4 = 4
    var = lambda v, c: (v - 1) * k4 + c
    cl = [[var(v, c) for c in range(1, k4 + 1)] for v in range(1, n3 + 1)]
    for u, v in E3:
        for c in range(1, k4 + 1):
            cl.append([-var(u, c), -var(v, c)])
    tri = find_triangle(n3, E3)
    for i, v in enumerate(tri):
        cl.append([var(v, i + 1)])
    nlem = 0
    for k in (1, 2, 3, 4):
        for c in range(1, k4 + 1):
            cl.append([-var(pairs[k]["A"], c), -var(pairs[k]["B"], c)]); nlem += 1
    cnf = os.path.join(out, "L3.cnf"); drat = os.path.join(out, "L3.drat")
    with open(cnf, "w") as f:
        f.write(f"p cnf {n3 * k4} {len(cl)}\n")
        for c in cl:
            f.write(" ".join(map(str, c)) + " 0\n")
    print(f"[L3] G3 4 色 CNF + {nlem} 條引理子句 (4 copy × 4 色), 三角形釘色 {tri}: {n3 * k4} 變量 {len(cl)} 子句", flush=True)
    exe = KISSAT if a.solver == "kissat" else CADICAL
    t0 = time.time()
    r = subprocess.run([exe, "-q", "--no-binary", cnf, drat], capture_output=True, text=True, timeout=a.timeout)
    dt = time.time() - t0
    assert r.returncode == 20, f"!! L3 唔係 UNSAT (rc={r.returncode})"
    t1 = time.time()
    dr = subprocess.run([DRATTRIM, cnf, drat], capture_output=True, text=True, timeout=DRATTRIM_TIMEOUT)
    ok = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
    lines = sum(1 for _ in open(drat, errors="ignore"))
    print(f"[L3] {a.solver} UNSAT {dt:.2f}s; DRAT {lines} 行 ({os.path.getsize(drat)} bytes); drat-trim "
          f"{'s VERIFIED ✓' if ok else '!! 冇 VERIFIED'} ({time.time() - t1:.1f}s)", flush=True)
    assert ok
    json.dump({"status": "UNSAT", "verified": True, "solver": a.solver, "solve_s": round(dt, 2), "drat_lines": lines,
               "lemma_clauses": nlem, "tri": tri, "sha": {"L3.cnf": sha(cnf), "L3.drat": sha(drat)}},
              open(os.path.join(out, "L3.json"), "w"), indent=1)
    print(f"[鏈] L2 ✓ + L3 ✓; 淨欠 L1 (G1 + A=B 同色 → UNSAT) 就係 G3 5-chromatic 嘅完整機器認證鏈", flush=True)

if __name__ == "__main__":
    main()
