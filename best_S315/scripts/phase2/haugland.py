#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
haugland.py —— Phase 2 Step 3: 精確重建 Haugland (arXiv:2608.04542v4) 嘅 H / u_j / L / G1 / G2 / G3

全部坐標用 exactfield.py 嘅分圓整數 (H, L, G1, G2 ⊂ Q(ζ_84); G3 ⊂ Q(ζ_420)), 去重同搵邊全部精確;
浮點只用嚟做「非 lattice 方向單位距離對」嘅候選掃描 (候選再精確核實)。
每一級嘅數字都同論文對數 (21 / 42 / 84 / 83581 / 1042 / 12856 / 740 / 3985 / 1066 / 6264 / 2131 / 12530),
對唔上即 assert 死 (鐵律 6: 以論文為準, 唔准夾硬砌落去)。

用法: python3 haugland.py --out DIR [--paths refs/appendixA_paths.json]
輸出: H.{cvtx,edge}  uvec.json  G1.{cvtx,edge,xy,special.json}  G2.{...}  G3.{...}  counts.json
"""
import sys, os, json, time, argparse, math
from fractions import Fraction

if not __debug__:
    sys.exit("!! 唔准用 python -O 跑 (assert 會被剝走)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exactfield import CycField, El, write_cvtx, check_files, read_cvtx

PAPER = {"H_vertices": 21, "H_edges": 42, "unit_vectors": 84, "ball3": 83581,
         "T5": 1042, "T6": 12856, "G1_v": 740, "G1_e": 3985,
         "G2_v": 1066, "G2_e": 6264, "G3_v": 2131, "G3_e": 12530, "G3_new_edges": 2,
         "theta": 0.42363201413287}

TABLE1 = {  # r: (tail, head), 索引 mod 7
    0: ("P", 3, "P", 4), 1: ("R", 0, "Q", 0), 2: ("R", 1, "R", 4), 3: ("R", 6, "P", 6),
    4: ("Q", 4, "Q", 6), 5: ("Q", 5, "P", 5), 6: ("P", 1, "P", 0), 7: ("Q", 4, "R", 4),
    8: ("R", 1, "R", 5), 9: ("P", 3, "R", 3), 10: ("Q", 3, "Q", 1), 11: ("P", 2, "Q", 2),
}

def log(msg):
    print(msg, flush=True)

def must(cond, what, mine, paper):
    if cond:
        log(f"    [對數] {what}: 我方 {mine} = 論文 {paper} ✓")
    else:
        raise AssertionError(f"!! [對數失敗] {what}: 我方 {mine} ≠ 論文 {paper} —— 停, 以論文為準")

def write_edge(path, n, edges):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"p edge {n} {len(edges)}\n")
        for u, v in edges:
            f.write(f"e {u} {v}\n")
    os.replace(tmp, path)

def write_xy(path, pts):
    with open(path, "w") as f:
        for z in pts:
            c = z.to_float()
            f.write(f"{c.real:.15f} {c.imag:.15f}\n")

# ============================================================
# 1. H
# ============================================================

def build_H(F):
    z = F.zeta
    half = Fraction(1, 2)
    minus_i_over_2 = z(63) * half                       # 1/(2i) = -i/2, -i = ζ^63
    sin27 = (z(12) - z(72)) * minus_i_over_2            # sin(2π/7) = (ζ7 - ζ7⁻¹)/(2i), ζ7 = ζ84^12
    sin47 = (z(24) - z(60)) * minus_i_over_2
    sin87 = (z(48) - z(36)) * minus_i_over_2
    alpha, beta, gamma = F.inv(sin27), F.inv(sin47), F.inv(sin87)
    # 論文 (1) (2): 精確驗證
    assert (alpha + beta + gamma).is_zero(), "α+β+γ != 0"
    assert (alpha * alpha + beta * beta + gamma * gamma) == F.rational(8), "α²+β²+γ² != 8"
    log(f"    α ≈ {alpha.to_float().real:.6f}, β ≈ {beta.to_float().real:.6f}, γ ≈ {gamma.to_float().real:.6f}; "
        f"精確: α+β+γ = 0 ✓, α²+β²+γ² = 8 ✓ (論文 (1)(2))")
    P = [(-gamma) * half * z(21 + 12 * j) for j in range(7)]
    Q = [alpha * half * z(7 + 12 * j) for j in range(7)]
    R = [beta * half * z(35 + 12 * j) for j in range(7)]
    H = P + Q + R                                        # index: P_j = j, Q_j = 7+j, R_j = 14+j
    names = [f"P{j}" for j in range(7)] + [f"Q{j}" for j in range(7)] + [f"R{j}" for j in range(7)]
    edges = []
    for a in range(21):
        for b in range(a + 1, 21):
            if (H[a] - H[b]).norm2().is_one():
                edges.append((a, b))
    must(len(H) == 21, "H 頂點數", len(H), 21)
    must(len(edges) == 42, "H 邊數", len(edges), 42)
    # 結構: 七邊形 P_j P_{j+1}, 七角星 Q_j Q_{j+2}, R_j R_{j+3}, 三角形 P_j Q_j R_j
    expect = set()
    for j in range(7):
        expect.add(frozenset((j, (j + 1) % 7)))
        expect.add(frozenset((7 + j, 7 + (j + 2) % 7)))
        expect.add(frozenset((14 + j, 14 + (j + 3) % 7)))
        expect.add(frozenset((j, 7 + j))); expect.add(frozenset((7 + j, 14 + j))); expect.add(frozenset((14 + j, j)))
    assert {frozenset(e) for e in edges} == expect, "H 嘅邊結構同 Proposition 2.1 唔符"
    log("    H 邊結構 = 七邊形(7) + 七角星{7/2}(7) + 七角星{7/3}(7) + 7 個等邊三角形(21) ✓ (Prop 2.1)")
    return H, names, edges, (alpha, beta, gamma)

# ============================================================
# 2. 84 個單位向量 + Table 1
# ============================================================

def build_uvec(F, H):
    z = F.zeta
    u = [None] * 84
    u1 = (H[0] - H[7]) * z(56)                           # (P0 - Q0)·ζ3⁻¹, ζ3⁻¹ = ζ84^-28 = ζ84^56
    for j in range(42):
        u[2 * j] = z(2 * j)
        u[2 * j + 1] = u1 * z(2 * j)
    for k in range(84):
        assert u[k].norm2().is_one(), f"|u_{k}| != 1"
        assert u[(k + 42) % 84] == -u[k], f"u_{k+42} != -u_{k}"
        assert u[(k + 2) % 84] == u[k] * z(2), f"u_{k+2} != u_k·ζ²"
    assert len({(x.num, x.den) for x in u}) == 84, "84 個向量唔係全部相異"
    angles = [math.atan2(x.to_float().imag, x.to_float().real) % (2 * math.pi) for x in u]
    assert all(angles[k] < angles[k + 1] for k in range(83)), "u_k 角度唔係遞增"
    theta = 21 * angles[1] / math.pi
    log(f"    u_0..u_83: 全部 |u|=1 ✓, u_{{k+42}} = -u_k ✓, u_{{k+2}} = u_k·ζ² ✓, 角度遞增 ✓; θ = {theta:.14f} "
        f"(論文 ≈ {PAPER['theta']}, 差 {abs(theta - PAPER['theta']):.1e})")
    assert abs(theta - PAPER["theta"]) < 1e-12
    # Table 1: u_{r+12j} == head - tail (精確, 84 條)
    idx = {"P": 0, "Q": 7, "R": 14}
    for r, (tk, ti, hk, hi) in TABLE1.items():
        for j in range(7):
            k = r + 12 * j
            tail = H[idx[tk] + (ti + j) % 7]
            head = H[idx[hk] + (hi + j) % 7]
            assert u[k] == head - tail, f"Table 1 對唔上: u_{k} != {hk}{(hi+j)%7} - {tk}{(ti+j)%7}"
    log("    Table 1: 84 條 arc 逐條精確核對 u_k == head − tail ✓")
    assert (u[0] + u[35] + u[22] + u[53] + u[72]).is_zero(), "Remark 2.1 閉路唔閉"
    log("    Remark 2.1: u0+u35+u22+u53+u72 = 0 ✓")
    return u

# ============================================================
# 3. Lattice (整數向量, 公分母 D)
# ============================================================

class Lat:
    """L 嘅點 = 24-int tuple (代表 z·D)。"""
    def __init__(self, F, u):
        self.F = F
        D = 1
        for x in u:
            D = D * x.den // math.gcd(D, x.den)
        self.D = D
        self.U = [tuple(c * (D // x.den) for c in x.num) for x in u]
        self.zero = tuple([0] * F.dim)
        self.dim = F.dim

    def add(self, a, b):
        return tuple(x + y for x, y in zip(a, b))

    def sub(self, a, b):
        return tuple(x - y for x, y in zip(a, b))

    def rot(self, a, k):
        """乘 ζ^k (整數係數線性映射, D 唔變)"""
        return tuple(self.F.mulvec(a, self.F.pw[k % self.F.N]))

    def el(self, a):
        return El(self.F, a, self.D)

    def const(self, e):
        """El (den | D) -> tuple"""
        assert self.D % e.den == 0
        return tuple(c * (self.D // e.den) for c in e.num)

    def ball(self, radius):
        """BFS 由原點, 回傳 dist dict (tuple -> 步數)"""
        dist = {self.zero: 0}
        frontier = [self.zero]
        for r in range(1, radius + 1):
            nxt = []
            for p in frontier:
                for uk in self.U:
                    q = self.add(p, uk)
                    if q not in dist:
                        dist[q] = r
                        nxt.append(q)
            frontier = nxt
            log(f"      {r}-ball: {len(dist)} 點")
        return dist

def lattice_edges(lat, pts_set):
    """pts_set: set of tuples; 回傳 [(p, q)] (每對一次), p + u_k = q, k < 42"""
    out = []
    for p in pts_set:
        for k in range(42):
            q = lat.add(p, lat.U[k])
            if q in pts_set:
                out.append((p, q))
    return out

def to_floats(lat, pts):
    import numpy as np
    roots = np.array([complex(math.cos(2 * math.pi * k / lat.F.N), math.sin(2 * math.pi * k / lat.F.N))
                      for k in range(lat.dim)])
    M = np.array([list(p) for p in pts], dtype=float)
    return (M @ roots) / lat.D

def scan_extra_unit_pairs(name, zs, edge_set_idx, exact_of, tol=1e-6):
    """全對浮點掃描 |d-1|<tol 嘅對; 唔喺 edge_set_idx 嘅候選逐對精確核實。
    回傳 (extra_exact_pairs, near_misses)。exact_of(i) -> El"""
    import numpy as np
    n = len(zs)
    cand = []
    B = 1024
    for i0 in range(0, n, B):
        blk = zs[i0:i0 + B]
        d = np.abs(blk[:, None] - zs[None, :])
        ii, jj = np.nonzero(np.abs(d - 1.0) < tol)
        for a, b in zip(ii, jj):
            i, j = i0 + int(a), int(b)
            if i < j:
                cand.append((i, j))
    n_lat = sum(1 for c in cand if c in edge_set_idx)
    others = [c for c in cand if c not in edge_set_idx]
    extra, near = [], []
    for i, j in others:
        d2 = (exact_of(i) - exact_of(j)).norm2()
        if d2.is_one():
            extra.append((i, j))
        else:
            near.append((i, j))
            df = abs(zs[i] - zs[j])
            log(f"    [{name}] 近似陷阱: 頂點 #{i + 1}–#{j + 1} 浮點距離 {df!r} (差 1 得 {df - 1:.3e}), "
                f"但精確 d² ≠ 1 (d² − 1 ≈ {(d2 - 1).to_float().real:.3e}, 精確向量非零) → 唔係邊")
    log(f"    [{name}] 全對浮點掃描 ({n} 點, {n * (n - 1) // 2} 對): |d-1|<{tol} 嘅候選 {len(cand)} 對, "
        f"其中 lattice 方向邊 {n_lat}; 非 lattice 候選 {len(others)} → 精確核實: 真單位 {len(extra)}, 近似 {len(near)}")
    assert n_lat == len(edge_set_idx), f"浮點掃描漏咗 lattice 邊? {n_lat} vs {len(edge_set_idx)}"
    return extra, near

# ============================================================
# 4. T_n / G0 / G1
# ============================================================

def build_G1(lat, paths):
    A = lat.zero
    Bt = lat.add(lat.U[14], lat.U[28])
    Bel = lat.el(Bt)
    assert Bel == lat.F.i_unit() * lat.F.sqrt_int(3), "B != i√3"
    log("    B = u14 + u28 = i√3 = (0, √3) ✓ (精確)")
    log("    BFS 3-ball (由 (0,0)):")
    dist = lat.ball(3)
    must(len(dist) == PAPER["ball3"], "3-ball 點數", len(dist), PAPER["ball3"])
    ball2 = [p for p, d in dist.items() if 1 <= d <= 2]
    U = lat.U

    def d_le(p, m):
        """原點到 p 嘅 lattice 距離 <= m ? (m <= 5, 精確)"""
        dp = dist.get(p)
        if dp is not None:
            return dp <= m
        if m <= 3:
            return False
        if m == 4:
            return any(lat.add(p, uk) in dist for uk in U)
        if m == 5:
            return any(lat.add(p, s) in dist for s in ball2)
        raise ValueError(m)

    def d_exact(p, cap):
        """精確距離 (<= cap) 或 None (> cap); cap <= 5"""
        for m in range(0, cap + 1):
            if d_le(p, m):
                return m
        return None

    cand = set(dist)
    for p in dist:
        cand.add(lat.add(p, Bt))
    T5, T6 = set(), set()
    for v in cand:
        dA = dist.get(v)
        dB = dist.get(lat.sub(v, Bt))
        if dA is not None:
            capB = 6 - dA
            dB = d_exact(lat.sub(v, Bt), capB) if dB is None else dB
            if dB is None:
                continue
        else:
            assert dB is not None
            dA = d_exact(v, 6 - dB)
            if dA is None:
                continue
        if dA + dB <= 6:
            T6.add(v)
        if dA + dB <= 5:
            T5.add(v)
    must(len(T5) == PAPER["T5"], "|V(T5)|", len(T5), PAPER["T5"])
    must(len(T6) == PAPER["T6"], "|V(T6)|", len(T6), PAPER["T6"])
    E6 = lattice_edges(lat, T6)
    adj = {v: set() for v in T6}
    for p, q in E6:
        adj[p].add(q); adj[q].add(p)
    log(f"    T6: {len(T6)} 點 {len(E6)} 條 lattice 邊; T5: {len(T5)} 點 {sum(1 for p, q in E6 if p in T5 and q in T5)} 條")
    # 非 lattice 單位距離對掃描 (T6 全對)
    T6l = sorted(T6)
    pos = {v: i for i, v in enumerate(T6l)}
    zs = to_floats(lat, T6l)
    eidx = {(min(pos[p], pos[q]), max(pos[p], pos[q])) for p, q in E6}
    extra, near = scan_extra_unit_pairs("T6", zs, eidx, lambda i: lat.el(T6l[i]))
    assert not extra, f"!! T6 有 {len(extra)} 對非 lattice 方向嘅精確單位距離對 —— 論文冇講, 停"
    # G0
    G0 = {v for v in T6 if v in T5 or len(adj[v] & T5) >= 7}
    log(f"    G0: {len(G0)} 點 (∈T5 或 T5 鄰居 ≥ 7)")
    # 7-core
    core = set(G0)
    deg = {v: len(adj[v] & core) for v in core}
    changed = True
    rounds = 0
    while changed:
        changed = False
        rounds += 1
        drop = [v for v in core if deg[v] < 7]
        if drop:
            changed = True
            for v in drop:
                core.discard(v)
            for v in drop:
                for w in adj[v]:
                    if w in core:
                        deg[w] -= 1
    G1 = sorted(core)
    E1 = [(p, q) for p, q in E6 if p in core and q in core]
    log(f"    7-core: {rounds} 輪 → G1 {len(G1)} 點 {len(E1)} 邊")
    must(len(G1) == PAPER["G1_v"], "|V(G1)|", len(G1), PAPER["G1_v"])
    must(len(E1) == PAPER["G1_e"], "|E(G1)|", len(E1), PAPER["G1_e"])
    assert A in core and Bt in core, "A / B 唔喺 G1 入面"
    # Appendix A 路徑對數
    visited = set()
    for pth in paths:
        p = A
        for i in pth:
            p = lat.add(p, U[i])
            assert p in core, f"Appendix A 路徑 {pth} 經過唔喺 G1 嘅點"
            visited.add(p)
        assert p == Bt, f"Appendix A 路徑 {pth} 終點唔係 B"
    visited.add(A)
    log(f"    Appendix A: {len(paths)} 條路徑全部由 A 精確落喺 B, 經過嘅點全部 ∈ V(G1); 聯集 {len(visited)} 點"
        + (" = V(G1) ✓" if visited == core else f" ≠ V(G1) ({len(core)}) !!"))
    assert visited == core, "Appendix A 路徑聯集 != V(G1) (論文只保證 ⊇; 我方要求 =, 唔等就報告)"
    return G1, E1, A, Bt

# ============================================================
# 5. G2
# ============================================================

def build_G2(lat, G1, E1):
    one = lat.const(lat.F.one())
    m1 = lat.const(lat.F.zeta(42))
    V1 = {lat.add(lat.rot(v, 70), m1) for v in G1}      # z·e^{-iπ/3} - 1
    V2 = {lat.add(lat.rot(v, 14), one) for v in G1}     # z·e^{iπ/3} + 1
    assert len(V1) == len(G1) == len(V2)
    V = V1 | V2
    must(len(V) == PAPER["G2_v"], "|V(G2)|", len(V), PAPER["G2_v"])
    log(f"    V1 ∩ V2 = {len(V1 & V2)} 點 (2×740 − 1066 = 414)")
    E = lattice_edges(lat, V)
    must(len(E) == PAPER["G2_e"], "|E(G2)| (lattice 方向)", len(E), PAPER["G2_e"])
    # 旋轉後 G1 嘅邊應該全部出現
    Eset = {frozenset(e) for e in E}
    for p, q in E1:
        assert frozenset((lat.add(lat.rot(p, 70), m1), lat.add(lat.rot(q, 70), m1))) in Eset
        assert frozenset((lat.add(lat.rot(p, 14), one), lat.add(lat.rot(q, 14), one))) in Eset
    log("    G1 兩個 copy 嘅 3985×2 條邊全部 ⊂ E(G2) ✓")
    Vl = sorted(V)
    pos = {v: i for i, v in enumerate(Vl)}
    zs = to_floats(lat, Vl)
    eidx = {(min(pos[p], pos[q]), max(pos[p], pos[q])) for p, q in E}
    extra, near = scan_extra_unit_pairs("G2", zs, eidx, lambda i: lat.el(Vl[i]))
    assert not extra, f"!! G2 有 {len(extra)} 對非 lattice 精確單位距離對"
    special = {"(-1,0)": m1, "(0,0)": lat.zero, "(1,0)": one,
               "(-1/2,√3/2)": lat.const(lat.F.zeta(28)), "(1/2,√3/2)": lat.const(lat.F.zeta(14))}
    for nm, t in special.items():
        assert t in V, f"特殊點 {nm} 唔喺 G2"
    log("    五個特殊點 (-1,0),(0,0),(1,0),(-½,√3/2),(½,√3/2) 全部 ∈ V(G2) ✓")
    return Vl, E, special

# ============================================================
# 6. G3 (N = 420)
# ============================================================

def build_G3(lat, F420, Vl2, E2):
    F84 = lat.F
    I = F420.i_unit()
    s15 = F420.sqrt_int(15)
    rho_mul = (F420.rational(7) + I * s15) * Fraction(1, 8)
    assert rho_mul.norm2().is_one(), "|(7+i√15)/8| != 1"
    one420 = F420.one()
    pts2 = [F420.embed(lat.el(v)) for v in Vl2]
    t0 = time.time()
    rho = [(z + one420) * rho_mul - one420 for z in pts2]
    log(f"    ρ(z) = (z+1)(7+i√15)/8 − 1 計咗 {len(rho)} 點 ({time.time() - t0:.1f}s, N=420 dim {F420.dim})")
    key = lambda e: (e.num, e.den)
    idx = {}
    pts3 = []
    for z in pts2:
        idx[key(z)] = len(pts3); pts3.append(z)
    shared = 0
    map_rho = []
    for z in rho:
        k = key(z)
        if k in idx:
            shared += 1
            map_rho.append(idx[k])
        else:
            idx[k] = len(pts3); pts3.append(z); map_rho.append(idx[k])
    must(len(pts3) == PAPER["G3_v"], "|V(G3)|", len(pts3), PAPER["G3_v"])
    m1 = F420.rational(-1)
    assert shared == 1 and idx[key(m1)] < len(pts2) and rho[idx[key(m1)]] == m1, "共用點應該只有 (-1,0)"
    log("    G2 ∩ ρ(G2) = {(-1,0)} ✓ (2×1066 − 1 = 2131)")
    pos2 = {v: i for i, v in enumerate(Vl2)}
    E3 = set()
    for p, q in E2:
        a, b = pos2[p], pos2[q]
        E3.add((min(a, b), max(a, b)))
        ra, rb = map_rho[a], map_rho[b]
        E3.add((min(ra, rb), max(ra, rb)))
    assert len(E3) == 2 * len(E2), "G2 邊同 ρ(G2) 邊有重疊?"
    # 交叉候選: 浮點全對 (G3 全部 2131 點), 非現有邊嘅候選精確核實
    import numpy as np
    zs = np.array([z.to_float() for z in pts3])
    extra, near = scan_extra_unit_pairs("G3", zs, E3, lambda i: pts3[i])
    log(f"    交叉新邊 (精確核實為 1): {len(extra)} 條 → {[(i, j) for i, j in extra]}; 近似但唔係 1: {len(near)}")
    must(len(extra) == PAPER["G3_new_edges"], "G3 新增邊數", len(extra), PAPER["G3_new_edges"])
    for e in extra:
        E3.add(e)
    must(len(E3) == PAPER["G3_e"], "|E(G3)|", len(E3), PAPER["G3_e"])
    # 特殊點
    one = idx[key(one420)]
    rho_one = map_rho[one]
    assert (min(one, rho_one), max(one, rho_one)) in E3, "(1,0)–ρ(1,0) 唔係邊?"
    r1 = pts3[rho_one]
    assert r1 == F420.rational(3, 4) + I * F420.sqrt_int(15) * Fraction(1, 4), "ρ(1,0) != (3/4, √15/4)"
    log("    (1,0) ↦ (3/4, √15/4) ✓ 精確, 而且係邊 ✓")
    special = {"(-1,0)": idx[key(m1)], "(1,0)": one, "(3/4,√15/4)": rho_one,
               "(0,0)": idx[key(F420.zero())], "rho(0,0)": map_rho[idx[key(F420.zero())]]}
    return pts3, sorted(E3), special, extra

# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/hadwiger/phase2/out/haugland"))
    ap.add_argument("--paths", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "refs", "appendixA_paths.json"))
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)
    T0 = time.time()
    counts = {}

    log("== 1. H (21 點, N=84) ==")
    F = CycField(84)
    H, names, HE, abg = build_H(F)
    write_cvtx(os.path.join(out, "H.cvtx"), F, H)
    write_edge(os.path.join(out, "H.edge"), 21, [(a + 1, b + 1) for a, b in HE])
    check_files(os.path.join(out, "H.cvtx"), os.path.join(out, "H.edge"), selftest=True)
    counts.update(H_vertices=21, H_edges=len(HE))

    log("== 2. 84 個單位向量 u_j + Table 1 ==")
    u = build_uvec(F, H)
    lat = Lat(F, u)
    log(f"    lattice 公分母 D = {lat.D}; u_1 = {list(u[1].num)}/{u[1].den}")
    with open(os.path.join(out, "uvec.json"), "w") as f:
        json.dump({"N": 84, "D": lat.D, "u": [{"k": k, "num": list(x.num), "den": x.den,
                                              "x": x.to_float().real, "y": x.to_float().imag} for k, x in enumerate(u)],
                   "table1_verified": True, "remark21_verified": True}, f)
    counts["unit_vectors"] = 84

    log("== 3. T5 / T6 / G0 / G1 ==")
    paths = json.load(open(a.paths))
    log(f"    Appendix A: 讀入 {len(paths)} 條路徑")
    G1, E1, A, Bt = build_G1(lat, paths)
    pos1 = {v: i for i, v in enumerate(G1)}
    pts1 = [lat.el(v) for v in G1]
    write_cvtx(os.path.join(out, "G1.cvtx"), F, pts1)
    write_edge(os.path.join(out, "G1.edge"), len(G1), sorted((min(pos1[p], pos1[q]) + 1, max(pos1[p], pos1[q]) + 1) for p, q in E1))
    write_xy(os.path.join(out, "G1.xy"), pts1)
    json.dump({"A_(0,0)": pos1[A] + 1, "B_(0,sqrt3)": pos1[Bt] + 1, "note": "1-based, 同 G1.edge/G1.cvtx"},
              open(os.path.join(out, "G1.special.json"), "w"), indent=1)
    log(f"    A = (0,0) 係頂點 #{pos1[A] + 1}, B = (0,√3) 係頂點 #{pos1[Bt] + 1} (1-based, 精確對認)")
    check_files(os.path.join(out, "G1.cvtx"), os.path.join(out, "G1.edge"), selftest=True)
    counts.update(ball3=PAPER["ball3"], T5=PAPER["T5"], T6=PAPER["T6"], G1_v=len(G1), G1_e=len(E1))

    log("== 4. G2 (兩個 copy) ==")
    Vl2, E2, sp2 = build_G2(lat, G1, E1)
    pos2 = {v: i for i, v in enumerate(Vl2)}
    pts2 = [lat.el(v) for v in Vl2]
    write_cvtx(os.path.join(out, "G2.cvtx"), F, pts2)
    write_edge(os.path.join(out, "G2.edge"), len(Vl2), sorted((min(pos2[p], pos2[q]) + 1, max(pos2[p], pos2[q]) + 1) for p, q in E2))
    write_xy(os.path.join(out, "G2.xy"), pts2)
    json.dump({k: pos2[v] + 1 for k, v in sp2.items()} | {"note": "1-based"},
              open(os.path.join(out, "G2.special.json"), "w"), indent=1, ensure_ascii=False)
    check_files(os.path.join(out, "G2.cvtx"), os.path.join(out, "G2.edge"), selftest=True)
    counts.update(G2_v=len(Vl2), G2_e=len(E2))

    log("== 5. G3 (spindle, N=420) ==")
    F420 = CycField(420)
    pts3, E3, sp3, extra = build_G3(lat, F420, Vl2, E2)
    write_cvtx(os.path.join(out, "G3.cvtx"), F420, pts3)
    write_edge(os.path.join(out, "G3.edge"), len(pts3), [(i + 1, j + 1) for i, j in E3])
    write_xy(os.path.join(out, "G3.xy"), pts3)
    json.dump({k: v + 1 for k, v in sp3.items()} | {"new_edges_1based": [(i + 1, j + 1) for i, j in extra], "note": "1-based"},
              open(os.path.join(out, "G3.special.json"), "w"), indent=1, ensure_ascii=False)
    t0 = time.time()
    check_files(os.path.join(out, "G3.cvtx"), os.path.join(out, "G3.edge"), selftest=True)
    counts.update(G3_v=len(pts3), G3_e=len(E3), G3_new_edges=len(extra))

    counts["paper"] = {k: v for k, v in PAPER.items() if k != "theta"}
    counts["all_match"] = all(counts[k] == v for k, v in counts["paper"].items())
    counts["total_time_s"] = round(time.time() - T0, 1)
    json.dump(counts, open(os.path.join(out, "counts.json"), "w"), indent=1)
    log(f"== 完成: 全部數字同論文一致 = {counts['all_match']}; 總用時 {counts['total_time_s']}s; 輸出喺 {out} ==")

if __name__ == "__main__":
    main()
