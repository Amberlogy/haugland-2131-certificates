#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
g2common.py —— Phase 3b 共用層 (G₂ 縮圖戰役, Haugland 方向)
  * 讀 G₂ (1066 點, Q(ζ84)) / G₃ (2131 點, Q(ζ420)) 精確坐標 + 邊表, sha 對數 (Phase 2 重建, 同論文數字一致)
  * ρ(z) = (z+1)(7+i√15)/8 − 1 精確映射: rho_idx[w] = ρ(G₂ #w) 喺 G₃ 嘅 1-based 索引 (對唔上即死); G₂ #w = G₃ #w (identity 嵌入, 逐點核對)
  * 保護集 P₂ = {u=(−1,0), v=(1,0), (0,√3)} ∪ {w : w 或 ρ(w) 係 G₃ 特殊點 / 兩條交叉邊端點}
  * CNF 編碼同 phase4/g2recon.py `build` 一字不改 (S=∅ 要同 g2_mono.cnf byte 級一致, sha 9bfbffbc…)
  * 染色解碼 + 逐邊覆核
"""
import sys, os, json, hashlib
from fractions import Fraction
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); PH2B = os.path.expanduser("~/hadwiger/phase2b"); PH3B = os.path.expanduser("~/hadwiger/phase3b")
sys.path.insert(0, PH2)
from exactfield import read_cvtx, load_edges, write_cvtx, CycField   # noqa: E402
import certify4                                                       # noqa: E402
KISSAT = certify4.KISSAT; DRATTRIM = certify4.DRATTRIM
MARCH = "/home/user/hadwiger/tools/CnC/march_cu/march_cu"
H = os.path.join(PH2, "out", "haugland")
K = 4
INPUT_SHA = {"G2.cvtx": "849ff7a23b1cb6031598b33d2bc028fb49b7d20b385c1cf30e58b65b0b800d3d",
             "G2.edge": "32ba405060ba59d799ee3e8ee193c46d25c8494bfbb50d7f1037fe2007398f5d",
             "G3.cvtx": "441f31210dae1ab14e700a2b7e34e70264aa1b1f9307c2f47c8ea3534c6e6d1f",
             "G3.edge": "992936f8779b3baedb70b6518ae3a870a1278969d6deae8c0008df172302ae0b"}
G2_MONO_SHA = "9bfbffbcb30673a497bbd3d2e3ba175d07d7ceac449c55d45c368f72e606c0eb"   # Phase 4 run p4r2_g2recon g2_mono.cnf (S=∅, 32525 子句)
G2_PLAIN_SHA = "efe573a0c0d6947579ef8fce66225ef853f5b4f8781feacc5c3cafeb46a96be1"  # 同上, 冇反 pair 子句 (32521 子句)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def var(v, c):
    return (v - 1) * K + c

def write_cnf(path, nvars, cl):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("p cnf %d %d\n" % (nvars, len(cl)))
        for c in cl:
            f.write(" ".join(map(str, c)) + " 0\n")
    os.replace(tmp, path)
    return sha(path)

def write_edge(path, n, edges):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("p edge %d %d\n" % (n, len(edges)))
        for a, b in edges:
            f.write("e %d %d\n" % (a, b))
    os.replace(tmp, path)

class G2:
    """G₂ 精確坐標 + 邊表 + 特殊點 (全部由檔案 + 精確代數對認, 唔信 json 單方面)."""
    def __init__(self, hdir=H, check_sha=True):
        self.hdir = hdir
        self.cvtx = os.path.join(hdir, "G2.cvtx"); self.edge = os.path.join(hdir, "G2.edge")
        if check_sha:
            for f in ("G2.cvtx", "G2.edge"):
                assert sha(os.path.join(hdir, f)) == INPUT_SHA[f], "%s sha 對唔上 Phase 2 重建版本" % f
        self.F, self.P = read_cvtx(self.cvtx); self.n, self.E = load_edges(self.edge)
        assert self.F.N == 84 and self.n == len(self.P) == 1066 and len(self.E) == 6264, "G₂ 唔係 1066 點 6264 邊"
        self.adj = [set() for _ in range(self.n + 1)]
        for a, b in self.E:
            self.adj[a].add(b); self.adj[b].add(a)
        F = self.F
        def locate(z, name):
            hits = [i + 1 for i, p in enumerate(self.P) if p == z]
            assert len(hits) == 1, "%s 對認唔到或者唔唯一: %s" % (name, hits)
            return hits[0]
        self.u = locate(F.rational(-1), "(-1,0)"); self.v = locate(F.one(), "(1,0)")
        self.b = locate(F.i_unit() * F.sqrt_int(3), "(0,√3)"); self.o = locate(F.zero(), "(0,0)")
        assert (self.P[self.u - 1] - self.P[self.v - 1]).norm2() == F.rational(4), "|u−v| 應該係 2"
        sp = json.load(open(os.path.join(hdir, "G2.special.json")))
        assert sp["(-1,0)"] == self.u and sp["(1,0)"] == self.v and sp["(0,0)"] == self.o, (sp, self.u, self.v, self.o)
        self.deg = [len(self.adj[w]) for w in range(self.n + 1)]
        self.axis = [None] + [abs(z.to_float().imag) for z in self.P]     # 離 u–v 軸線 (直線 y=0) 嘅距離 (浮點, 只用嚟排序)
        self.sha = {"G2.cvtx": sha(self.cvtx), "G2.edge": sha(self.edge)}

class G3:
    """G₃ + ρ 映射 (精確): rho_idx[w] (w = G₂ 1-based) = G₃ 1-based 索引; identity: G₂ #w == G₃ #w 逐點核對."""
    def __init__(self, g2, hdir=H, check_sha=True):
        self.hdir = hdir
        self.cvtx = os.path.join(hdir, "G3.cvtx"); self.edge = os.path.join(hdir, "G3.edge")
        if check_sha:
            for f in ("G3.cvtx", "G3.edge"):
                assert sha(os.path.join(hdir, f)) == INPUT_SHA[f], "%s sha 對唔上 Phase 2 重建版本" % f
        self.F, self.P = read_cvtx(self.cvtx); self.n, self.E = load_edges(self.edge)
        assert self.F.N == 420 and self.n == len(self.P) == 2131 and len(self.E) == 12530, "G₃ 唔係 2131 點 12530 邊"
        F = self.F
        self.idx = {(z.num, z.den): i + 1 for i, z in enumerate(self.P)}
        I = F.i_unit(); s15 = F.sqrt_int(15)
        self.rho_mul = (F.rational(7) + I * s15) * Fraction(1, 8); one = F.one()
        assert self.rho_mul.norm2().is_one(), "|(7+i√15)/8| != 1"
        self.rho = lambda w: (w + one) * self.rho_mul - one
        # identity 嵌入 + ρ 映射
        self.rho_idx = [None] * (g2.n + 1)
        for w in range(1, g2.n + 1):
            z = F.embed(g2.P[w - 1])
            assert self.idx.get((z.num, z.den)) == w, "G₂ #%d 唔係 G₃ #%d (identity 嵌入失敗)" % (w, w)
            r = self.rho(z); j = self.idx.get((r.num, r.den))
            assert j is not None, "ρ(G₂ #%d) 唔喺 V(G₃)" % w
            self.rho_idx[w] = j
        assert len(set(self.rho_idx[1:])) == g2.n, "ρ 唔係 injective"
        assert self.rho_idx[g2.u] == g2.u, "ρ 應該固定 (−1,0)"
        assert sum(1 for w in range(1, g2.n + 1) if self.rho_idx[w] <= g2.n) == 1, "G₂ ∩ ρ(G₂) 應該只有 (−1,0)"
        assert set(range(1, g2.n + 1)) | set(self.rho_idx[1:]) == set(range(1, self.n + 1)), "G₂ ∪ ρ(G₂) != V(G₃)"
        self.sp3 = json.load(open(os.path.join(hdir, "G3.special.json")))
        assert self.sp3["(-1,0)"] == g2.u and self.sp3["(1,0)"] == g2.v and self.sp3["(0,0)"] == g2.o
        assert self.sp3["(3/4,√15/4)"] == self.rho_idx[g2.v] and self.sp3["rho(0,0)"] == self.rho_idx[g2.o]
        self.cross = [tuple(e) for e in self.sp3["new_edges_1based"]]
        E3set = {frozenset(e) for e in self.E}
        assert frozenset((g2.v, self.rho_idx[g2.v])) in E3set, "(1,0)–ρ(1,0) 唔係 G₃ 嘅邊?!"
        assert frozenset((g2.b, self.rho_idx[g2.b])) in E3set, "(0,√3)–ρ(0,√3) 唔係 G₃ 嘅邊?!"
        assert {frozenset(e) for e in self.cross} == {frozenset((g2.v, self.rho_idx[g2.v])), frozenset((g2.b, self.rho_idx[g2.b]))}, "交叉邊同 G3.special.json 唔一致"
        self.E3set = E3set
        self.sha = {"G3.cvtx": sha(self.cvtx), "G3.edge": sha(self.edge)}

def protected_set(g2, g3):
    """P₂ + 每粒點嘅理由 (dict w -> [理由])."""
    S3 = {g3.sp3[k] for k in ("(-1,0)", "(1,0)", "(3/4,√15/4)", "(0,0)", "rho(0,0)")} | {w for e in g3.cross for w in e}
    why = {}
    def add(w, r):
        why.setdefault(w, []).append(r)
    add(g2.u, "u = (−1,0): pair 端點, G₂ ∩ ρ(G₂) 嘅共用點, 引理 col(u)=col(v) / col(u)=col(ρv) 用到")
    add(g2.v, "v = (1,0): pair 端點, 交叉邊 (1,0)–ρ(1,0) 端點, 引理用到")
    add(g2.b, "(0,√3): 第二條交叉邊 (0,√3)–ρ(0,√3) 端點 (題目指定保護)")
    for w in range(1, g2.n + 1):
        if w in S3:
            add(w, "G₂ #%d 本身係 G₃ 特殊點 / 交叉邊端點 (G₃ 索引 %d)" % (w, w))
        if g3.rho_idx[w] in S3:
            add(w, "ρ(G₂ #%d) = G₃ #%d 係 G₃ 特殊點 / 交叉邊端點" % (w, g3.rho_idx[w]))
    return sorted(why), why

def build_cnf(g2, S=(), amo=True, anti=True, protected=()):
    """同 phase4/g2recon.py build() 一字不改 (子句次序都一樣), 加多一重保護集檢查. 回傳 (cl, E', tri)."""
    n, edges, u, v = g2.n, g2.E, g2.u, g2.v
    S = set(S)
    assert all(1 <= w <= n for w in S), "S 有越界索引"
    assert u not in S and v not in S, "!! 唔准剪走 u=(−1,0) 或 v=(1,0)"
    bad = S & set(protected)
    assert not bad, "!! S 含保護集 P₂ 嘅頂點: %s" % sorted(bad)
    adj = g2.adj
    tri = next(((x, y) for x in sorted(adj[u]) for y in sorted(adj[u] & adj[x]) if x < y and x not in S and y not in S), None)
    assert tri, "u 冇避開 S 嘅三角形"
    E = [(x, y) for x, y in edges if x not in S and y not in S]
    cl = [[var(w, c) for c in range(1, K + 1)] for w in range(1, n + 1) if w not in S]
    if amo:
        for w in range(1, n + 1):
            if w in S:
                continue
            for c in range(1, K + 1):
                for c2 in range(c + 1, K + 1):
                    cl.append([-var(w, c), -var(w, c2)])
    for x, y in E:
        for c in range(1, K + 1):
            cl.append([-var(x, c), -var(y, c)])
    cl += [[var(u, 1)], [var(tri[0], 2)], [var(tri[1], 3)]]
    if anti:
        for c in range(1, K + 1):
            cl.append([-var(u, c), -var(v, c)])
    return cl, E, tri

def decode_model(model_pos, n, S=()):
    pos = set(int(t) for t in model_pos if int(t) > 0); S = set(S); col = {}
    for w in range(1, n + 1):
        if w in S:
            continue
        cs = [c for c in range(1, K + 1) if var(w, c) in pos]
        col[w] = cs[0] if cs else None
    return col

def verify_colouring(g2, S, col):
    """G₂ − S 嘅染色逐邊覆核; 回傳 dict (ok ⇔ 全部染咁, 冇同色邊, col(u) != col(v))."""
    S = set(S)
    missing = [w for w in range(1, g2.n + 1) if w not in S and col.get(w) is None]
    bad_val = [w for w, c in col.items() if c is not None and not (isinstance(c, int) and 1 <= c <= K)]   # 審查 finding: 色值必須喺 1..K
    extra = [w for w in col if w in S or not (1 <= w <= g2.n)]                                            # S 入面 / 越界嘅頂點唔應該有色
    checked = [(x, y) for x, y in g2.E if x not in S and y not in S]
    bad = [(x, y) for x, y in checked if col.get(x) == col.get(y)]
    cu, cv = col.get(g2.u), col.get(g2.v)
    return {"ok": (not missing and not bad and not bad_val and not extra and cu is not None and cu != cv), "n_coloured": g2.n - len(S) - len(missing), "missing": len(missing),
            "edges_checked": len(checked), "bad_edges": len(bad), "bad_values": len(bad_val), "extra_vertices": len(extra), "col_u": cu, "col_v": cv}

def write_col(path, S, col, header):
    with open(path, "w") as f:
        f.write(header.rstrip("\n") + "\n")
        for w in sorted(col):
            f.write("%d %d\n" % (w, col[w] if col[w] is not None else 0))
    return sha(path)

def read_col(path):
    S = None; col = {}
    for line in open(path):
        if line.startswith("c") and " minus [" in line:
            S = sorted(int(x) for x in line[line.index("[") + 1:line.index("]")].split(",") if x.strip())
            continue
        t = line.split()
        if len(t) == 2 and t[0].isdigit():
            c = int(t[1])
            assert 0 <= c <= K, "col 檔色值 %d 唔喺 0..%d (頂點 %s)" % (c, K, t[0])      # 0 = 冇色 (write_col 寫 None 做 0)
            col[int(t[0])] = None if c == 0 else c
    assert S is not None and col, "col 檔冇 header / 冇染色"
    return S, col
