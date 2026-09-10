#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beam_udg.py —— Phase 3b 第 4 步 (改題): 仿 arXiv:2406.15317 (Engel, Hammond-Lee, Su, Varga, Zsámboki: diverse beam search for densest planar UDGs)
  喺格仔 L (Haugland 84 arc, 精確 Q(ζ84), haugland.py 生成器) 或者 Moser 格仔 ML = Z<1, ω1, ω3, ω1ω3> (精確 Q(√3,√11)) 入面搵 n 點最多邊嘅單位距離子圖.
  搜尋 (格仔無關):
    * 狀態 = 格仔點集 (整數向量 tuple), 邊數 E, gain 字典 (候選點 q → q 同幾多個現有點單位距離; 候選 = 現有點 + 單位向量, 涵蓋論文 Op1/Op2/Op3)
    * forward step: 每個狀態取 gain 最高嘅 m 個候選 → 仔狀態 (E + gain); 全部仔狀態按 E 排, canonization (旋轉 + 反射, 浮點只用嚟去重) 去重, 減 visitation penalty (論文 diversity), 留 top α
    * backward sweep: 由 N_max 嘅 beam 逐粒刪 (刪度數最細嘅點, 留 top α), 更新細 n 嘅最佳
    * 重跑 R 次 (visitation penalty 累積) 直至時間上限
  每個 n 嘅最佳圖 **精確覆核邊數**: L 用 float 預篩 (| |p−q|−1 | < 1e-6) + 非 lattice 方向候選精確 |d|² = 1 (同 haugland.py 標準); Moser 全對精確 (Q(√3,√11))
  Moser 格仔對照: 論文 Table 2 (n = 1..100) 嵌入 PAPER_MOSER; --lattice moser 用同一算法跑一次做同算法對照 (n > 100)
用法: python3 beam_udg.py --lattice L|moser --out DIR [--alpha 200] [--m 16] [--nmax 300] [--restarts 4] [--time-cap 8400] [--seed 1]
輸出: DIR/beam_<lattice>.json (每個 n: 邊數, 精確覆核, 點), DIR/beam_<lattice>.md, DIR/status.json (每分鐘)
"""
import sys, os, json, time, argparse, random, heapq, math
from fractions import Fraction
if not __debug__:
    sys.exit("!! 唔准用 python -O")
import numpy as np
PH2 = os.path.expanduser("~/hadwiger/phase2"); sys.path.insert(0, PH2)
from exactfield import CycField
import haugland

# arXiv:2406.15317 Table 2 (Moser lattice, densest known, n = 1..100) — transcribed 2026-09-06 from the HTML version; u(n) for n ≤ 30 agrees with OEIS A186705
PAPER_MOSER = {1: 0, 2: 1, 3: 3, 4: 5, 5: 7, 6: 9, 7: 12, 8: 14, 9: 18, 10: 20, 11: 23, 12: 27, 13: 30, 14: 33, 15: 37, 16: 41, 17: 43, 18: 46, 19: 50, 20: 54,
               21: 57, 22: 60, 23: 64, 24: 68, 25: 72, 26: 76, 27: 81, 28: 85, 29: 89, 30: 93, 31: 97, 32: 101, 33: 105, 34: 109, 35: 114, 36: 119, 37: 123, 38: 128, 39: 132, 40: 137,
               41: 141, 42: 146, 43: 150, 44: 155, 45: 160, 46: 164, 47: 169, 48: 174, 49: 180, 50: 183, 51: 188, 52: 192, 53: 197, 54: 202, 55: 206, 56: 211, 57: 216, 58: 221, 59: 226, 60: 231,
               61: 235, 62: 240, 63: 246, 64: 252, 65: 256, 66: 261, 67: 266, 68: 271, 69: 276, 70: 281, 71: 286, 72: 291, 73: 296, 74: 301, 75: 306, 76: 312, 77: 317, 78: 322, 79: 327, 80: 332,
               81: 338, 82: 345, 83: 350, 84: 355, 85: 360, 86: 365, 87: 370, 88: 375, 89: 380, 90: 385, 91: 390, 92: 396, 93: 401, 94: 406, 95: 412, 96: 418, 97: 423, 98: 429, 99: 434, 100: 439}

# ---------------- 精確 Q(√3, √11) (Moser 格仔用) ----------------
class QF:
    __slots__ = ("v",)
    def __init__(self, v):
        self.v = tuple(Fraction(x) for x in v)          # a + b√3 + c√11 + d√33
    def __add__(s, o):
        return QF(tuple(a + b for a, b in zip(s.v, o.v)))
    def __sub__(s, o):
        return QF(tuple(a - b for a, b in zip(s.v, o.v)))
    def __mul__(s, o):
        a1, b1, c1, d1 = s.v; a2, b2, c2, d2 = o.v
        return QF((a1 * a2 + 3 * b1 * b2 + 11 * c1 * c2 + 33 * d1 * d2,
                   a1 * b2 + b1 * a2 + 11 * (c1 * d2 + d1 * c2),
                   a1 * c2 + c1 * a2 + 3 * (b1 * d2 + d1 * b2),
                   a1 * d2 + d1 * a2 + b1 * c2 + c1 * b2))
    def is_one(s):
        return s.v == (1, 0, 0, 0)
    def to_float(s):
        a, b, c, d = (float(x) for x in s.v)
        return a + b * math.sqrt(3) + c * math.sqrt(11) + d * math.sqrt(33)

def qf_selftest():
    r3 = QF((0, 1, 0, 0)); r11 = QF((0, 0, 1, 0)); r33 = QF((0, 0, 0, 1))
    assert (r3 * r3).v == (3, 0, 0, 0) and (r11 * r11).v == (11, 0, 0, 0) and (r3 * r11).v == (0, 0, 0, 1) and (r3 * r33).v == (0, 0, 3, 0) and (r11 * r33).v == (0, 11, 0, 0) and (r33 * r33).v == (33, 0, 0, 0)

# ---------------- 格仔抽象 ----------------
class LatticeL:
    name = "L"
    def __init__(self):
        F = CycField(84); Hpts, names, HE, abg = haugland.build_H(F); u = haugland.build_uvec(F, Hpts)
        self.lat = haugland.Lat(F, u); self.U = list(self.lat.U); self.dim = self.lat.dim; self.D = self.lat.D; self.F = F
        self.roots = np.array([complex(math.cos(2 * math.pi * k / F.N), math.sin(2 * math.pi * k / F.N)) for k in range(self.dim)])
        self.uc = [self.emb(x) for x in self.U]
        self.origin = self.lat.zero
        z2 = complex(math.cos(2 * math.pi / 42), math.sin(2 * math.pi / 42)); u1 = self.uc[1]
        self.transforms = [(z2 ** j, False) for j in range(42)] + [(u1 * z2 ** j, True) for j in range(42)]   # 旋轉 2π/42 × 42, 反射 z ↦ u1·z̄ (角度集合 {2πj/42} ∪ {θ1 + 2πj/42} 對稱)
        self.n_unit = 84
    def emb(self, p):
        return complex(np.dot(np.array(p, dtype=float), self.roots)) / self.D
    def add(self, p, k):
        return self.lat.add(p, self.U[k])
    def el(self, p):
        return self.lat.el(p)
    def exact_unit(self, p, q):
        return (self.el(p) - self.el(q)).norm2().is_one()

class LatticeMoser:
    name = "moser"
    def __init__(self):
        qf_selftest()
        w1 = complex(0.5, math.sqrt(3) / 2); w3 = complex(5 / 6, math.sqrt(11) / 6)
        self.basis = np.array([1, w1, w3, w1 * w3]); self.dim = 4; self.D = 1
        # 精確 re/im 向量 (基 1, √3, √11, √33)
        self.re = [QF((1, 0, 0, 0)), QF((Fraction(1, 2), 0, 0, 0)), QF((Fraction(5, 6), 0, 0, 0)), QF((Fraction(5, 12), 0, 0, Fraction(-1, 12)))]
        self.im = [QF((0, 0, 0, 0)), QF((0, Fraction(1, 2), 0, 0)), QF((0, 0, Fraction(1, 6), 0)), QF((0, Fraction(5, 12), Fraction(1, 12), 0))]
        # 單位向量: 枚舉 |係數| ≤ 6, 精確 |z|² = 1
        U = []
        rng = range(-6, 7)
        for a in rng:
            for b in rng:
                for c in rng:
                    for d in rng:
                        if (a, b, c, d) != (0, 0, 0, 0) and self.norm2((a, b, c, d)).is_one():
                            U.append((a, b, c, d))
        assert len(U) == 18, "Moser 格仔單位向量應該係 18 個, 得 %d" % len(U)
        self.U = U; self.uc = [self.emb(x) for x in U]; self.origin = (0, 0, 0, 0); self.n_unit = 18
        self.transforms = [(w1 ** j, False) for j in range(6)] + [(w3 * w1 ** j, True) for j in range(6)]   # 旋轉 60° × 6, 反射 z ↦ ω3·z̄ (ML 對呢個反射封閉)
    def emb(self, p):
        return complex(np.dot(np.array(p, dtype=float), self.basis))
    def add(self, p, k):
        u = self.U[k]; return (p[0] + u[0], p[1] + u[1], p[2] + u[2], p[3] + u[3])
    def parts(self, p):
        re = QF((0, 0, 0, 0)); im = QF((0, 0, 0, 0))
        for c, r_, i_ in zip(p, self.re, self.im):
            if c:
                cq = QF((c, 0, 0, 0)); re = re + cq * r_; im = im + cq * i_
        return re, im
    def norm2(self, p):
        re, im = self.parts(p); return re * re + im * im
    def exact_unit(self, p, q):
        return self.norm2(tuple(a - b for a, b in zip(p, q))).is_one()

def transforms_selftest(L):
    """對稱群檢查: 每個 (mult, conj) 將單位向量集合映到自己 (浮點, 1e-9)."""
    S = np.array(L.uc)
    for mult, cj in L.transforms:
        W = (np.conj(S) if cj else S) * mult
        for w in W:
            assert np.min(np.abs(S - w)) < 1e-9, "transform 唔封閉: %s conj=%s" % (mult, cj)

# ---------------- canonization (浮點, 只用嚟去重) ----------------
def canon_key(L, coords):
    arr = np.array(coords); best = None
    for mult, cj in L.transforms:
        w = (np.conj(arr) if cj else arr) * mult
        x = np.round(w.real * 1e6).astype(np.int64); y = np.round(w.imag * 1e6).astype(np.int64)
        order = np.lexsort((y, x)); x = x[order] - x[order[0]]; y = y[order] - y[order[0]]
        # 平移之後再排一次 (減去最細點唔改次序, 但為穩陣)
        key = np.stack([x, y], axis=1).tobytes()
        if best is None or key < best:
            best = key
    return best

# ---------------- 狀態 ----------------
class State:
    __slots__ = ("pts", "coords", "E", "gain", "key", "score")
    def __init__(self, pts, coords, E, gain, key=None):
        self.pts = pts; self.coords = coords; self.E = E; self.gain = gain; self.key = key; self.score = E

def add_point(L, s, q):
    """s + q → 新狀態 (gain 字典複製更新)."""
    g = s.gain; gq = g.get(q, 0)
    ng = dict(g); ng.pop(q, None)
    pset = s.pts
    for k in range(L.n_unit):
        r = L.add(q, k)
        if r not in pset:
            ng[r] = ng.get(r, 0) + 1
    npts = dict(pset); npts[q] = len(pset)
    return State(npts, s.coords + [L.emb(q)], s.E + gq, ng)

def degree(L, pts, v):
    return sum(1 for k in range(L.n_unit) if L.add(v, k) in pts)

def rebuild(L, pts_list):
    """由點 list 由零起狀態 (backward sweep 用)."""
    pset = {p: i for i, p in enumerate(pts_list)}; gain = {}; E = 0
    for p in pts_list:
        for k in range(L.n_unit):
            r = L.add(p, k)
            if r in pset:
                E += 1
            else:
                gain[r] = gain.get(r, 0) + 1
    return State(pset, [L.emb(p) for p in pts_list], E // 2, gain)

# ---------------- beam search ----------------
def forward(L, a, best, visits, rng, deadline, log, run_id):
    s0 = State({L.origin: 0}, [L.emb(L.origin)], 0, {L.add(L.origin, k): 1 for k in range(L.n_unit)})
    beam = [s0]; n = 1; t0 = time.time()
    while n < a.nmax and time.time() < deadline:
        cands = []
        for s in beam:
            items = s.gain.items()
            top = heapq.nlargest(a.m, items, key=lambda kv: (kv[1], rng.random()))
            for q, g in top:
                cands.append((s.E + g, rng.random(), s, q))
        cands.sort(key=lambda t: (-t[0], t[1]))
        new = []; seen = set(); tried = 0
        # 先按 E 取 top 3α 做 canonization + penalty, 再按 (E − visits) 揀 α
        pool = []
        for E2, _, s, q in cands[:3 * a.alpha]:
            child = add_point(L, s, q); child.key = canon_key(L, child.coords); tried += 1
            if child.key in seen:
                continue
            seen.add(child.key); child.score = child.E - a.lam * visits.get(child.key, 0); pool.append(child)
        pool.sort(key=lambda c: (-c.score, -c.E, rng.random()))
        beam = pool[:a.alpha]; n += 1
        for c in beam:
            visits[c.key] = visits.get(c.key, 0) + 1
        top = max(beam, key=lambda c: c.E)
        if n not in best or top.E > best[n]["edges"]:
            best[n] = {"edges": top.E, "points": [list(p) for p in top.pts], "found": "forward run %d" % run_id, "improved_at": time.strftime("%H:%M:%S")}
        if n % 25 == 0 or n <= 12:
            log("  fwd run %d n=%d: beam %d (pool %d, tried %d), best E=%d (record %d), %.0fs" % (run_id, n, len(beam), len(pool), tried, top.E, best[n]["edges"], time.time() - t0))
    return beam, n

def backward(L, a, beam, best, rng, deadline, log, run_id, n_start):
    n = n_start; t0 = time.time()
    while n > 2 and time.time() < deadline:
        cands = []
        for s in beam:
            pts = s.pts
            degs = [(degree(L, pts, v), rng.random(), v) for v in pts]
            degs.sort()
            for d, _, v in degs[:a.m]:
                cands.append((s.E - d, rng.random(), s, v))
        cands.sort(key=lambda t: (-t[0], t[1]))
        pool = []; seen = set()
        for E2, _, s, v in cands[:3 * a.alpha]:          # 先用坐標做 canonization 去重, 只為留低嘅重建 gain 字典
            iv = s.pts[v]; coords = s.coords[:iv] + s.coords[iv + 1:]
            key = canon_key(L, coords)
            if key in seen:
                continue
            seen.add(key); pool.append((E2, rng.random(), s, v, key))
            if len(pool) >= a.alpha:
                break
        pool.sort(key=lambda t: (-t[0], t[1]))
        beam = []
        for E2, _, s, v, key in pool[:a.alpha]:
            pts_list = [p for p in s.pts if p != v]
            child = rebuild(L, pts_list); assert child.E == E2, (child.E, E2); child.key = key; beam.append(child)
        n -= 1
        top = max(beam, key=lambda c: c.E)
        if n not in best or top.E > best[n]["edges"]:
            best[n] = {"edges": top.E, "points": [list(p) for p in top.pts], "found": "backward run %d" % run_id, "improved_at": time.strftime("%H:%M:%S")}
            log("  bwd run %d n=%d: NEW best E=%d" % (run_id, n, top.E))
        if n % 50 == 0:
            log("  bwd run %d n=%d: beam %d, best E=%d (record %d), %.0fs" % (run_id, n, len(beam), top.E, best[n]["edges"], time.time() - t0))
    return n

# ---------------- 精確覆核 ----------------
def verify_exact(L, pts):
    """回傳 (精確邊數, lattice 方向邊數, 非 lattice 精確單位對數, 浮點候選數, 近似對數)."""
    n = len(pts); pset = set(pts)
    lat_pairs = set()
    for i, p in enumerate(pts):
        for k in range(L.n_unit):
            r = L.add(p, k)
            if r in pset:
                j = pts.index(r) if n < 64 else None
                lat_pairs.add(frozenset((p, r)))
    m_lat = len(lat_pairs)
    zs = np.array([L.emb(p) for p in pts])
    d = np.abs(zs[:, None] - zs[None, :]); ii, jj = np.nonzero(np.abs(d - 1.0) < 1e-6)
    cand = {(int(i), int(j)) for i, j in zip(ii, jj) if i < j}
    extra = 0; near = 0; lat_found = 0
    for i, j in cand:
        if frozenset((pts[i], pts[j])) in lat_pairs:
            lat_found += 1
        elif L.exact_unit(pts[i], pts[j]):
            extra += 1
        else:
            near += 1
    assert lat_found == m_lat, "浮點掃描漏咗 lattice 邊 (%d vs %d)" % (lat_found, m_lat)
    if L.name == "moser":      # Moser: 全對精確 (n ≤ 300 平)
        m_exact = sum(1 for i in range(n) for j in range(i + 1, n) if L.exact_unit(pts[i], pts[j]))
        assert m_exact == m_lat + extra
    return m_lat + extra, m_lat, extra, len(cand), near

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lattice", required=True, choices=["L", "moser"]); ap.add_argument("--out", required=True)
    ap.add_argument("--alpha", type=int, default=200); ap.add_argument("--m", type=int, default=16); ap.add_argument("--nmax", type=int, default=300)
    ap.add_argument("--restarts", type=int, default=4); ap.add_argument("--time-cap", type=float, default=8400); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--lam", type=float, default=1.0); ap.add_argument("--no-backward", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); T0 = time.time(); deadline = T0 + a.time_cap
    logf = open(os.path.join(a.out, "beam_%s.log" % a.lattice), "a")
    def log(m):
        line = "[%s %5.0fs] %s" % (time.strftime("%H:%M:%S"), time.time() - T0, m); print(line, flush=True); logf.write(line + "\n"); logf.flush()
    L = LatticeL() if a.lattice == "L" else LatticeMoser()
    transforms_selftest(L)
    log("lattice %s: %d unit vectors, dim %d, D=%d, %d symmetry transforms (closure selftest ✓); alpha %d, m %d, nmax %d, restarts %d, cap %.0fs, seed %d" % (
        L.name, L.n_unit, L.dim, L.D, len(L.transforms), a.alpha, a.m, a.nmax, a.restarts, a.time_cap, a.seed))
    rng = random.Random(a.seed); best = {}; visits = {}; runs = []
    jp = os.path.join(a.out, "beam_%s.json" % a.lattice)
    def save(final=False):
        out = {"lattice": L.name, "n_unit": L.n_unit, "params": vars(a), "runs": runs, "elapsed_s": round(time.time() - T0, 1), "final": final,
               "best": {str(n): {k: v for k, v in best[n].items()} for n in sorted(best)}}
        json.dump(out, open(jp + ".tmp", "w"), indent=0); os.replace(jp + ".tmp", jp)
        json.dump({"lattice": L.name, "elapsed_s": round(time.time() - T0, 1), "runs_done": len(runs), "n_best": len(best), "max_n": max(best) if best else 0, "updated": time.strftime("%H:%M:%S")},
                  open(os.path.join(a.out, "status_%s.json" % a.lattice), "w"))
    for run_id in range(1, a.restarts + 1):
        if time.time() > deadline:
            break
        t0 = time.time(); beam, n_reached = forward(L, a, best, visits, rng, deadline, log, run_id)
        fw = time.time() - t0; runs.append({"run": run_id, "forward_n": n_reached, "forward_s": round(fw, 1)}); save()
        log("run %d forward done: n=%d in %.0fs" % (run_id, n_reached, fw))
        if not a.no_backward and time.time() < deadline:
            t1 = time.time(); n_end = backward(L, a, beam, best, rng, deadline, log, run_id, n_reached); runs[-1]["backward_to"] = n_end; runs[-1]["backward_s"] = round(time.time() - t1, 1); save()
            log("run %d backward done: down to n=%d in %.0fs" % (run_id, n_end, time.time() - t1))
    # 精確覆核
    log("exact verification of %d best graphs" % len(best))
    t0 = time.time(); bad = 0
    for n in sorted(best):
        pts = [tuple(p) for p in best[n]["points"]]
        assert len(pts) == n and len(set(pts)) == n
        m_exact, m_lat, extra, ncand, near = verify_exact(L, pts)
        best[n].update({"edges_exact": m_exact, "lattice_pairs": m_lat, "extra_unit_pairs": extra, "float_candidates": ncand, "near_misses": near, "verified": (m_exact == best[n]["edges"])})
        if m_exact != best[n]["edges"]:
            bad += 1; log("  !! n=%d: search E=%d but exact edges %d (lattice %d + extra %d)" % (n, best[n]["edges"], m_exact, m_lat, extra))
    log("verification done in %.0fs: %d graphs, %d mismatches" % (time.time() - t0, len(best), bad))
    save(final=True)
    # markdown
    L_ = ["# beam_%s.md — densest unit-distance subgraphs found by beam search in %s (n = 2..%d)" % (L.name, "Haugland's lattice L (84 unit vectors, exact Q(zeta_84))" if L.name == "L" else "the Moser lattice ML (18 unit vectors, exact Q(sqrt3,sqrt11))", max(best) if best else 0), "",
          "Method: forward beam search (candidates = existing point + unit vector, scored by edges gained; beam width alpha=%d, m=%d children per state, canonization under %d symmetries, visitation penalty lambda=%g across %d restarts) + backward sweep (delete lowest-degree vertices). Every reported edge count is re-verified exactly (see columns)." % (a.alpha, a.m, len(L.transforms), a.lam, len(runs)),
          "Runs: %s; elapsed %.0f s (cap %.0f s)." % (runs, time.time() - T0, a.time_cap), "",
          "| n | edges (exact) | lattice-direction pairs | extra unit pairs | found by | paper Moser E(n) (arXiv:2406.15317 Table 2) | diff |", "|---|---|---|---|---|---|---|"]
    for n in sorted(best):
        pm = PAPER_MOSER.get(n); e = best[n]["edges_exact"]
        L_.append("| %d | %d | %d | %d | %s | %s | %s |" % (n, e, best[n]["lattice_pairs"], best[n]["extra_unit_pairs"], best[n]["found"], pm if pm is not None else "—", ("%+d" % (e - pm)) if pm is not None else "—"))
    open(os.path.join(a.out, "beam_%s.md" % a.lattice), "w").write("\n".join(L_) + "\n")
    log("BEAM DONE → %s" % jp)

if __name__ == "__main__":
    main()
