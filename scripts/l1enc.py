#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
l1enc.py —— L1 (G1 + 「A=(0,0) 同 B=(0,√3) 同色」→ 4 色) 嘅 CNF 編碼變體 + 對稱性機器核對

變量: var(v,c) = (v-1)*4 + c, c = 1..4 (同 certify4 / cnc.py / Phase 1 一致)
變體:
  a: certify4.build 原版: ALO + edge + 第一個三角形釘 (1,2,3) + same-AB  —— sha 必須同 Phase 2 嘅 G1-4-sameAB.cnf 一樣 (selftest 核對)
  b: a + AMO (每點至多一色), **A、B 除外** —— 咁樣 (b) 嘅任何 DRAT 證明前面加 AMO 子句做 RAT 引理, 就係 (a) 嘅 DRAT 證明
     (pivot 揀一個唔係正 unit 嘅 literal; 見 README「AMO 提升引理」; selftest 用 G510 機器示範 drat-trim -f VERIFIED)
  c: ALO + AMO(除 A,B) + edge + same-AB + 釘 A=1, B=1, p=2, q=3, (A,p,q) = A 所在嘅第一個三角形 (BFS 次序)
     健全: 任何「A,B 同色」嘅 4 色染色, 換色可令 A=1 (B 跟住 =1), p=2, q=3 (A,p,q 兩兩相鄰所以三色相異)
  d: ALO + AMO(除 A,B) + edge + same-AB + 釘 A=1, B=1 + lex-leader(σ) + lex-leader(colour perms of {2,3,4})
     σ(z) = i√3 − z (繞 (0,√3/2) 嘅點反射, A↔B). 機器核對: (i) σ(V)=V, σ(E)=E, 精確坐標; (ii) σ 誘導嘅變量置換
     同每個 colour perm 都係「LL 之前嗰個 CNF」嘅語法自同構 (子句集逐條映返自己); 之後加 LL 健全 (Crawford–Ginsberg–Luks–Roy 1996:
     對一組對稱 g_1..g_m, F ∧ ⋀ LL(g_i) 同 F 等可滿足, 因為 orbit 入面 lex 最細嗰個賦值滿足全部 LL).

用法:
  python3 l1enc.py build --edge G1.edge --cvtx G1.cvtx --variant a|b|c|d --out DIR [--tag TAG] [--plain]
  python3 l1enc.py selftest --edge G1.edge --cvtx G1.cvtx --out DIR [--phase2-cnf PATH] [--g510 PATH/510.edge]
  python3 l1enc.py lift --variant-b-drat P.drat --out-lifted L.drat --edge .. --cvtx ..   # (b) 證明 → (a) 證明 (前綴 AMO RAT 引理)
輸出: DIR/L1_<variant>.cnf + .json (sha256, 子句數, A/B/pin/σ 置換, 核對結果)
"""
import sys, os, json, time, argparse, subprocess, hashlib, itertools, random
from fractions import Fraction

if not __debug__:
    sys.exit("!! 唔准用 python -O")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.expanduser("~/hadwiger/phase2"))
from exactfield import load_edges, read_cvtx, CycField
import certify4

K = 4
KISSAT = "/home/user/hadwiger/kissat/build/kissat"
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"

def var(v, c):
    return (v - 1) * K + c

def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def canon(clauses):
    """子句集嘅 canonical form: 每條子句排序 (去重 literal), 再整體排序 (multiset)."""
    return sorted(tuple(sorted(set(c))) for c in clauses)

# ---------------- 幾何: σ ----------------
def sigma_perm(F, pts, A, B):
    """σ(z) = z_B − z (i√3 − z). 回傳 perm[1..n] (1-based, perm[0] 唔用); 搵唔到像即 raise."""
    idx = {(z.num, z.den): i + 1 for i, z in enumerate(pts)}
    zB = pts[B - 1]
    assert pts[A - 1].is_zero(), "A 唔係 (0,0)"
    assert zB == F.i_unit() * F.sqrt_int(3), "B 唔係 (0,√3)"
    perm = [0] * (len(pts) + 1)
    missing = []
    for i, z in enumerate(pts):
        w = zB - z
        j = idx.get((w.num, w.den))
        if j is None:
            missing.append(i + 1)
        else:
            perm[i + 1] = j
    assert not missing, "σ(V) ⊄ V: %d 個頂點嘅像唔喺 V, 例如 %s" % (len(missing), missing[:5])
    return perm

def check_vertex_perm_is_automorphism(n, edges, perm, A=None, B=None):
    assert sorted(perm[1:]) == list(range(1, n + 1)), "perm 唔係 bijection"
    E = {frozenset(e) for e in edges}
    bad = [(u, v) for u, v in edges if frozenset((perm[u], perm[v])) not in E]
    assert not bad, "σ(E) ⊄ E: %d 條邊唔保, 例如 %s" % (len(bad), bad[:5])
    if A is not None:
        assert perm[A] == B and perm[B] == A, "σ 冇交換 A,B: σ(A)=%d σ(B)=%d" % (perm[A], perm[B])
    fixed = [v for v in range(1, n + 1) if perm[v] == v]
    invol = all(perm[perm[v]] == v for v in range(1, n + 1))
    return {"edges_checked": len(edges), "fixed_points": fixed, "involution": invol}

# ---------------- CNF 組件 ----------------
def base_clauses(n, edges, amo_except=()):
    cl = [[var(v, c) for c in range(1, K + 1)] for v in range(1, n + 1)]
    for u, v in edges:
        for c in range(1, K + 1):
            cl.append([-var(u, c), -var(v, c)])
    amo = []
    for v in range(1, n + 1):
        if v in amo_except:
            continue
        for c in range(1, K + 1):
            for c2 in range(c + 1, K + 1):
                amo.append([-var(v, c), -var(v, c2)])
    return cl, amo

def same_clauses(U, V):
    cl = []
    for c in range(1, K + 1):
        cl.append([-var(U, c), var(V, c)]); cl.append([var(U, c), -var(V, c)])
    return cl

def bfs_order(n, edges, roots):
    adj = [set() for _ in range(n + 1)]
    for u, v in edges:
        adj[u].add(v); adj[v].add(u)
    seen, order, frontier = set(roots), list(roots), list(roots)
    while frontier:
        nxt = []
        for v in frontier:
            for w in sorted(adj[v]):
                if w not in seen:
                    seen.add(w); order.append(w); nxt.append(w)
        frontier = nxt
    for v in range(1, n + 1):
        if v not in seen:
            order.append(v)
    return order, adj

def triangle_at(adj, v, avoid=()):
    for x in sorted(adj[v]):
        if x in avoid:
            continue
        for y in sorted(adj[v] & adj[x]):
            if x < y and y not in avoid:
                return (x, y)
    return None

# ---------------- lex-leader ----------------
def lex_leader(vperm, order, next_aux):
    """
    vperm: dict 變量→變量 (置換, 正變量). order: 變量次序 (list). 回傳 (clauses, next_aux).
    constraint: x ≤_lex π(x) 喺 order 之下. 標準 chain 編碼 (Aloul et al. 2003), aux p_i ↔ (前 i 位全等).
    2-cycle 只入第一個元素 (第二個喺前綴相等之下係冗餘).
    """
    pos = {x: i for i, x in enumerate(order)}
    idx = []
    for x in order:
        y = vperm.get(x, x)
        if y == x:
            continue
        if vperm.get(y, y) == x and pos[y] < pos[x]:
            continue
        idx.append((x, y))
    cl = []
    prev = None            # aux var for p_{i-1} (None = true)
    for i, (x, y) in enumerate(idx):
        # p_{i-1} → (x ≤ y)  ≡  (¬p_{i-1} ∨ ¬x ∨ y)
        cl.append(([-prev] if prev is not None else []) + [-x, y])
        if i == len(idx) - 1:
            break
        p = next_aux; next_aux += 1
        # p ↔ p_{i-1} ∧ (x ↔ y)
        if prev is not None:
            cl.append([-p, prev])
        cl.append([-p, -x, y]); cl.append([-p, x, -y])
        pre = [-prev] if prev is not None else []
        cl.append([p] + pre + [-x, -y]); cl.append([p] + pre + [x, y])
        prev = p
    return cl, next_aux

def lex_holds(assign, vperm, order):
    """assign: set of true vars. 直接檢查 x ≤_lex π(x) (唔經 aux)."""
    for x in order:
        y = vperm.get(x, x)
        if y == x:
            continue
        a, b = (x in assign), (y in assign)
        if a != b:
            return (not a) and b
    return True

# ---------------- 變體 ----------------
def build_variant(variant, n, edges, A, B, plain=False, sigma=None):
    """回傳 dict: clauses, nvars, meta. plain=True: 冇 same-AB (G1 單獨, 應該 SAT), pin 相應收窄 (冇釘 B)."""
    order, adj = bfs_order(n, edges, [A, B])
    meta = {"variant": variant, "plain": plain, "A": A, "B": B}
    same = [] if plain else same_clauses(A, B)
    if variant == "a":
        cl, nvars, tri = certify4.build(n, edges, K, None if plain else (A, B), True)
        meta["pin"] = {"triangle": tri, "colours": [1, 2, 3]}
        return {"clauses": cl, "nvars": nvars, "meta": meta}
    if variant == "b":
        cl, nvars, tri = certify4.build(n, edges, K, None if plain else (A, B), True)
        _, amo = base_clauses(n, edges, amo_except=(A, B))
        meta["pin"] = {"triangle": tri, "colours": [1, 2, 3]}; meta["amo_except"] = [A, B]; meta["amo_clauses"] = len(amo)
        return {"clauses": cl + amo, "nvars": nvars, "meta": meta}
    if variant == "c":
        cl, amo = base_clauses(n, edges, amo_except=(A, B))
        p, q = triangle_at(adj, A, avoid=(B,))
        pins = [[var(A, 1)], [var(p, 2)], [var(q, 3)]] + ([] if plain else [[var(B, 1)]])
        meta["pin"] = {"A": A, "p": p, "q": q, "B_pinned": not plain, "colours": {"A": 1, "p": 2, "q": 3, "B": 1}}
        meta["amo_except"] = [A, B]; meta["amo_clauses"] = len(amo)
        return {"clauses": cl + amo + same + pins, "nvars": n * K, "meta": meta}
    if variant == "d":
        assert sigma is not None
        cl, amo = base_clauses(n, edges, amo_except=(A, B))
        pins = [] if plain else [[var(A, 1)], [var(B, 1)]]
        F0 = cl + amo + same + pins
        # 變量置換
        vp_sigma = {var(v, c): var(sigma[v], c) for v in range(1, n + 1) for c in range(1, K + 1)}
        colours = [1, 2, 3, 4] if plain else [2, 3, 4]
        cperms = []
        for tau in itertools.permutations(colours):
            if list(tau) == colours:
                continue
            m = dict(zip(colours, tau))
            cperms.append({"tau": m, "vp": {var(v, c): var(v, m.get(c, c)) for v in range(1, n + 1) for c in range(1, K + 1)}})
        # 語法自同構核對 (LL 之前)
        C0 = canon(F0)
        chk = {}
        assert canon([[(-1 if l < 0 else 1) * vp_sigma[abs(l)] for l in c] for c in F0]) == C0, "σ 唔係 F0 嘅語法自同構"
        chk["sigma_syntactic"] = True
        for cp in cperms:
            assert canon([[(-1 if l < 0 else 1) * cp["vp"][abs(l)] for l in c] for c in F0]) == C0, "colour perm %s 唔係 F0 嘅語法自同構" % cp["tau"]
        chk["colour_perms_syntactic"] = len(cperms)
        vorder = [var(v, c) for v in order for c in range(1, K + 1)]
        next_aux = n * K + 1
        ll_s, next_aux = lex_leader(vp_sigma, vorder, next_aux)
        ll_c = []
        for cp in cperms:
            x, next_aux = lex_leader(cp["vp"], vorder, next_aux); ll_c += x
        meta.update({"pin": {"A": A, "B": B, "colour": 1, "B_pinned": not plain}, "amo_except": [A, B], "amo_clauses": len(amo),
                     "sigma_fixed": [v for v in range(1, n + 1) if sigma[v] == v], "ll_sigma_clauses": len(ll_s),
                     "ll_colour_clauses": len(ll_c), "colour_perms": [cp["tau"] for cp in cperms], "checks": chk, "aux_vars": next_aux - 1 - n * K})
        return {"clauses": F0 + ll_s + ll_c, "nvars": next_aux - 1, "meta": meta,
                "ll": {"sigma": (vp_sigma, vorder), "colours": [(cp["vp"], vorder) for cp in cperms]}}
    raise ValueError(variant)

def write_cnf(path, nvars, clauses):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("p cnf %d %d\n" % (nvars, len(clauses)))
        for c in clauses:
            f.write(" ".join(map(str, c)) + " 0\n")
    os.replace(tmp, path)

def amo_lemmas(n, A, B, positive_units):
    """AMO RAT 引理 (for lift): 每條 (¬x_{v,c} ∨ ¬x_{v,c'}), pivot (第一個 literal) 揀唔係正 unit 嘅嗰個."""
    out = []
    for v in range(1, n + 1):
        if v in (A, B):
            continue
        for c in range(1, K + 1):
            for c2 in range(c + 1, K + 1):
                a, b = var(v, c), var(v, c2)
                assert not (a in positive_units and b in positive_units), "cube/pin 同時釘咗 %d 兩隻色?" % v
                out.append([-b, -a] if a in positive_units else [-a, -b])
    return out

def solve_and_check_colouring(cnf_path, n, edges, timeout=600, extra_check=None):
    r = subprocess.run([KISSAT, "-q", cnf_path], capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 10, "預期 SAT, 但 rc=%d" % r.returncode
    model = set()
    for line in r.stdout.splitlines():
        if line.startswith("v"):
            model.update(int(t) for t in line.split()[1:] if int(t) > 0)
    col = {}
    for v in range(1, n + 1):
        cs = [c for c in range(1, K + 1) if var(v, c) in model]
        assert cs, "頂點 %d 冇色" % v
        col[v] = cs
    bad = [(u, v) for u, v in edges if set(col[u]) & set(col[v])]
    assert not bad, "染色覆核失敗: %s" % bad[:5]
    if extra_check:
        extra_check(model, col)
    return model, col

# ---------------- 命令 ----------------
def cmd_build(a):
    n, edges = load_edges(a.edge)
    F, pts = read_cvtx(a.cvtx)
    A, B = certify4.locate_AB(a.cvtx)
    sigma = None
    if a.variant == "d":
        sigma = sigma_perm(F, pts, A, B)
        geo = check_vertex_perm_is_automorphism(n, edges, sigma, A, B)
    r = build_variant(a.variant, n, edges, A, B, plain=a.plain, sigma=sigma)
    os.makedirs(a.out, exist_ok=True)
    tag = a.tag or ("L1_%s%s" % (a.variant, "_plain" if a.plain else ""))
    cnf = os.path.join(a.out, tag + ".cnf")
    write_cnf(cnf, r["nvars"], r["clauses"])
    meta = dict(r["meta"]); meta.update({"n": n, "m": len(edges), "nvars": r["nvars"], "clauses": len(r["clauses"]), "cnf": cnf,
                                         "cnf_sha256": sha_file(cnf), "edge_sha256": sha_file(a.edge), "cvtx_sha256": sha_file(a.cvtx)})
    if sigma is not None:
        meta["sigma_geo"] = geo; meta["sigma_perm_sha256"] = hashlib.sha256(json.dumps(sigma).encode()).hexdigest()
        json.dump(sigma, open(os.path.join(a.out, tag + ".sigma.json"), "w"))
    json.dump(meta, open(os.path.join(a.out, tag + ".json"), "w"), indent=1)
    print("[build] %s: %d 變量 %d 子句, sha %s; meta: %s" % (tag, r["nvars"], len(r["clauses"]), meta["cnf_sha256"][:16],
          {k: v for k, v in meta.items() if k in ("pin", "amo_clauses", "ll_sigma_clauses", "ll_colour_clauses", "checks", "sigma_geo")}), flush=True)

def cmd_lift(a):
    n, edges = load_edges(a.edge)
    A, B = certify4.locate_AB(a.cvtx)
    units = set()
    for line in open(a.cnf_b):
        t = line.split()
        if not t or t[0] in ("c", "p"):
            continue
        if len(t) == 2 and t[1] == "0" and int(t[0]) > 0:
            units.add(int(t[0]))
    lem = amo_lemmas(n, A, B, units)
    with open(a.out_lifted, "w") as f:
        for c in lem:
            f.write(" ".join(map(str, c)) + " 0\n")
        with open(a.drat_b) as g:
            for line in g:
                f.write(line)
    print("[lift] %d 條 AMO RAT 引理 + %s → %s" % (len(lem), a.drat_b, a.out_lifted))

def cmd_selftest(a):
    t0 = time.time()
    n, edges = load_edges(a.edge)
    F, pts = read_cvtx(a.cvtx)
    A, B = certify4.locate_AB(a.cvtx)
    os.makedirs(a.out, exist_ok=True)
    log = []
    def ok(msg):
        log.append(msg); print("  ✓ " + msg, flush=True)
    def expect_fail(label, fn):
        try:
            fn()
        except AssertionError as e:
            log.append("poison rejected: " + label + " :: " + str(e)[:80]); print("  ✓ 毒藥被拒: %s :: %s" % (label, str(e)[:80]), flush=True); return
        raise AssertionError("!! 毒藥冇被拒: " + label)
    print("[selftest] A=#%d B=#%d, n=%d m=%d" % (A, B, n, len(edges)), flush=True)
    # 1. variant a == Phase 2 CNF
    ra = build_variant("a", n, edges, A, B)
    p = os.path.join(a.out, "st_a.cnf"); write_cnf(p, ra["nvars"], ra["clauses"])
    if a.phase2_cnf:
        assert sha_file(p) == sha_file(a.phase2_cnf), "variant a sha != Phase 2 G1-4-sameAB.cnf"
        ok("variant a 同 Phase 2 G1-4-sameAB.cnf byte 級一致 (sha %s)" % sha_file(p)[:16])
    # 2. σ 幾何
    sigma = sigma_perm(F, pts, A, B)
    geo = check_vertex_perm_is_automorphism(n, edges, sigma, A, B)
    ok("σ(z)=i√3−z: σ(V)=V, σ(E)=E (%d 條邊), σ(A)=B, involution=%s, fixed=%s" % (geo["edges_checked"], geo["involution"], geo["fixed_points"]))
    def poison_shift():
        idx = {(z.num, z.den): i + 1 for i, z in enumerate(pts)}
        zB = pts[B - 1]; shift = F.rational(1, 1000)
        miss = sum(1 for z in pts if idx.get(((zB + shift - z).num, (zB + shift - z).den)) is None)
        assert miss == 0, "shifted σ: %d 個像唔喺 V" % miss
    expect_fail("σ 中心移 1/1000", poison_shift)
    def poison_swap():
        pm = list(sigma); u, v = 1, 2
        while sigma[u] == u or sigma[v] == v or v in (sigma[u],):
            u += 1; v += 2
        pm[u], pm[v] = pm[v], pm[u]
        check_vertex_perm_is_automorphism(n, edges, pm, A, B)
    expect_fail("σ 兩個像對調", poison_swap)
    def poison_rot():   # 繞原點轉 π/21 (lattice 對稱, 但唔固定 {A,B})
        idx = {(z.num, z.den): i + 1 for i, z in enumerate(pts)}
        rot = F.zeta(2)
        miss = sum(1 for z in pts if idx.get(((z * rot).num, (z * rot).den)) is None)
        assert miss == 0, "rot π/21: %d 個像唔喺 V" % miss
    expect_fail("繞原點轉 π/21", poison_rot)
    # 3. 語法自同構 (variant d 內部會 assert); 毒藥: σ 對 variant c (三角形釘色) 一定唔係語法自同構
    rd = build_variant("d", n, edges, A, B, sigma=sigma)
    ok("variant d: σ + %d 個 colour perm 都係 F0 嘅語法自同構; LL(σ) %d 子句, LL(colour) %d 子句, aux %d" % (
        len(rd["meta"]["colour_perms"]), rd["meta"]["ll_sigma_clauses"], rd["meta"]["ll_colour_clauses"], rd["meta"]["aux_vars"]))
    rc = build_variant("c", n, edges, A, B)
    def poison_syntax():
        vp = {var(v, c): var(sigma[v], c) for v in range(1, n + 1) for c in range(1, K + 1)}
        assert canon([[(-1 if l < 0 else 1) * vp[abs(l)] for l in c] for c in rc["clauses"]]) == canon(rc["clauses"]), "σ 唔係 variant c 嘅語法自同構 (三角形釘色唔係 σ-不變)"
    expect_fail("σ 對 variant c (釘 p=2,q=3)", poison_syntax)
    def poison_colour1():
        cl, amo = base_clauses(n, edges, amo_except=(A, B)); F0 = cl + amo + same_clauses(A, B) + [[var(A, 1)], [var(B, 1)]]
        m = {1: 2, 2: 1, 3: 3, 4: 4}; vp = {var(v, c): var(v, m[c]) for v in range(1, n + 1) for c in range(1, K + 1)}
        assert canon([[(-1 if l < 0 else 1) * vp[abs(l)] for l in c] for c in F0]) == canon(F0), "colour perm (1 2) 唔係 F0 嘅語法自同構 (釘咗色 1)"
    expect_fail("colour perm (1 2) 對釘 A=B=1", poison_colour1)
    # 4. LL 編碼暴力核對: 全部 120 個 5-變量置換 (所有 cycle type) × 3 個隨機次序 × 32 賦值, 加 7-變量 (1 2 3)(4 5)(6 7) × 20 次序 × 128 賦值:
    #    aux 可滿足 ⇔ x ≤lex π(x)
    rng = random.Random(20260905)
    def ll_check(vp, order):
        m = len(order); cl, na = lex_leader(vp, order, m + 1); naux = na - 1 - m
        for bits in range(1 << m):
            assign = {v for v in order if bits >> (v - 1) & 1}
            sat = False
            for ab in range(1 << naux):
                full = set(assign) | {m + 1 + j for j in range(naux) if ab >> j & 1}
                if all(any((l > 0) == (abs(l) in full) for l in c) for c in cl):
                    sat = True; break
            assert sat == lex_holds(assign, vp, order), "LL 編碼錯: perm %s order %s assign %s: enc=%s truth=%s" % (vp, order, sorted(assign), sat, lex_holds(assign, vp, order))
    cases = 0
    for img in itertools.permutations(range(1, 6)):
        vp = dict(zip(range(1, 6), img))
        for _ in range(3):
            order = list(range(1, 6)); rng.shuffle(order); ll_check(vp, order); cases += 32
    vp7 = {1: 2, 2: 3, 3: 1, 4: 5, 5: 4, 6: 7, 7: 6}
    for _ in range(20):
        order = list(range(1, 8)); rng.shuffle(order); ll_check(vp7, order); cases += 128
    ok("lex-leader 編碼: 120 個 5-變量置換 × 3 次序 × 32 賦值 + (1 2 3)(4 5)(6 7) × 20 次序 × 128 賦值 = %d 個 case 全部同直接 lex 比較一致" % cases)
    # 4b. σ 毒藥: identity 置換 (係自同構但冇交換 A,B) 必須被 A↔B 檢查拒絕
    expect_fail("identity 置換 (冇交換 A,B)", lambda: check_vertex_perm_is_automorphism(n, edges, list(range(n + 1)), A, B))
    # 4c. 非 plain 管線嘅 SAT 對照: 揀一個 u 令 G1 + same(u, σ(u)) 4 色 SAT, 用完整生產編碼 (pins + same + AMO + LL) 建 b/c/d, 必須 SAT 且 model 通過全部約束
    order_far = bfs_order(n, edges, [A, B])[0][::-1]
    ctrl = None
    for u in order_far[:12]:
        v = sigma[u]
        if u == v or u in (A, B):
            continue
        cl_t, nv_t, _ = certify4.build(n, edges, K, (u, v), True)
        p = os.path.join(a.out, "st_ctrl_probe.cnf"); write_cnf(p, nv_t, cl_t)
        r = subprocess.run([KISSAT, "-q", "-n", "--time=30", p], capture_output=True, text=True, timeout=90)   # 30s 內 SAT 先用; UNSAT/未知就跳過
        if r.returncode == 10:
            ctrl = (u, v); break
    assert ctrl, "搵唔到 σ-對稱嘅 SAT 對照 pair"
    for vname in "bcd":
        r = build_variant(vname, n, edges, ctrl[0], ctrl[1], plain=False, sigma=sigma)
        p = os.path.join(a.out, "st_%s_ctrl.cnf" % vname); write_cnf(p, r["nvars"], r["clauses"])
        def extra(model, col, r=r, vname=vname):
            assert set(col[ctrl[0]]) & set(col[ctrl[1]]), "對照 pair 冇同色"
            assert all(any((l > 0) == (abs(l) in model) for l in c) for c in r["clauses"]), "model 唔滿足全部子句"
            if vname == "d":
                vp, vo = r["ll"]["sigma"]; assert lex_holds(model, vp, vo), "ctrl d model 違反 LL(σ)"
                for vp2, vo2 in r["ll"]["colours"]:
                    assert lex_holds(model, vp2, vo2), "ctrl d model 違反 LL(colour)"
        solve_and_check_colouring(p, n, edges, extra_check=extra)
    ok("非 plain SAT 對照: pair (u,σu)=(%d,%d) 用生產編碼 b/c/d (pins + same + AMO + LL) 全部 kissat SAT, model 逐子句/逐邊/LL 核對通過" % ctrl)
    # 5. plain 冒煙: 每個變體去 same-AB → kissat SAT + 逐邊覆核 (+ d: model 直接驗 LL)
    for vname in "abcd":
        r = build_variant(vname, n, edges, A, B, plain=True, sigma=sigma)
        p = os.path.join(a.out, "st_%s_plain.cnf" % vname); write_cnf(p, r["nvars"], r["clauses"])
        def extra(model, col, r=r, vname=vname):
            if vname == "d":
                vp, vo = r["ll"]["sigma"]
                assert lex_holds(model, vp, vo), "d-plain model 違反 LL(σ)"
                for vp2, vo2 in r["ll"]["colours"]:
                    assert lex_holds(model, vp2, vo2), "d-plain model 違反 LL(colour)"
            if vname in "bcd":
                assert all(len(cs) == 1 for v, cs in col.items() if v not in (A, B)), "AMO 冇生效?"
        t1 = time.time(); model, col = solve_and_check_colouring(p, n, edges, extra_check=extra)
        ok("variant %s plain (G1 單獨): kissat SAT %.1fs, %d/%d 條邊覆核異色%s" % (vname, time.time() - t1, len(edges), len(edges),
           "; model 直接驗 LL(σ)+LL(colour) 全過" if vname == "d" else ""))
    # 6. AMO 提升引理機器示範 (G510 + 假 same 對): (b)-式 CNF 嘅 kissat DRAT, 前綴 AMO 引理, drat-trim -f 對 (a)-式 CNF VERIFIED
    if a.g510:
        n5, e5 = load_edges(a.g510)
        adj5 = [set() for _ in range(n5 + 1)]
        for u, v in e5:
            adj5[u].add(v); adj5[v].add(u)
        tri5 = certify4.find_triangle(n5, e5)
        near = set(tri5) | set().union(*(adj5[t] for t in tri5))          # 釘色三角形 + 佢哋嘅鄰居
        U = next(v for v in range(1, n5 + 1) if v not in near)
        V = next(v for v in range(U + 1, n5 + 1) if v not in near and v not in adj5[U])
        cla, nv, tri = certify4.build(n5, e5, K, (U, V), True)
        _, amo5 = base_clauses(n5, e5, amo_except=(U, V))
        pa = os.path.join(a.out, "st_510a.cnf"); pb = os.path.join(a.out, "st_510b.cnf")
        write_cnf(pa, nv, cla); write_cnf(pb, nv, cla + amo5)
        db = os.path.join(a.out, "st_510b.drat")
        r = subprocess.run([KISSAT, "-q", "--no-binary", pb, db], capture_output=True, text=True, timeout=600)
        assert r.returncode == 20, "G510 (b) 應該 UNSAT"
        units = {c[0] for c in cla if len(c) == 1 and c[0] > 0}
        lem = amo_lemmas(n5, U, V, units)
        lifted = os.path.join(a.out, "st_510_lifted.drat")
        with open(lifted, "w") as f:
            for c in lem:
                f.write(" ".join(map(str, c)) + " 0\n")
            f.write(open(db).read())
        dr = subprocess.run([DRATTRIM, pa, lifted, "-f"], capture_output=True, text=True, timeout=1800)
        assert any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()), "提升證明 drat-trim -f 冇 VERIFIED:\n" + dr.stdout[-600:]
        ok("AMO 提升引理 (G510+same(%d,%d)): (b) DRAT %d 行 + %d 條 AMO 引理 → 對 (a) CNF drat-trim -f 's VERIFIED'" % (
            U, V, sum(1 for _ in open(db)), len(lem)))
        # 毒藥: 引理入面加一條假 unit → forward mode 一定 NOT VERIFIED
        bad = os.path.join(a.out, "st_510_bad.drat")
        with open(bad, "w") as f:
            f.write("%d 0\n" % (-var(U, 1)))     # 「U 唔係色 1」唔係 RAT/RUP
            f.write(open(lifted).read())
        dr = subprocess.run([DRATTRIM, pa, bad, "-f"], capture_output=True, text=True, timeout=1800)
        assert not any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()), "假引理竟然 VERIFIED"
        ok("毒藥: 提升證明前面加一條假 unit → drat-trim -f 唔 VERIFIED")
        # 毒藥 2/3/4 (審核員要求): 先確認 (a) 唔係 UP-refutable (只有空子句嘅證明必須 NOT VERIFIED), 否則以下毒藥冇牙
        guard = os.path.join(a.out, "st_510_empty.drat"); open(guard, "w").write("0\n")
        dr = subprocess.run([DRATTRIM, pa, guard, "-f"], capture_output=True, text=True, timeout=600)
        assert not any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()), "G510 (a) 竟然 UP-refutable, 毒藥冇牙"
        # 毒藥 3: 加埋 U (same pair 成員) 嘅 AMO 引理 → RAT 唔成立 → -f NOT VERIFIED
        badU = os.path.join(a.out, "st_510_badU.drat")
        with open(badU, "w") as f:
            f.write("%d %d 0\n" % (-var(U, 1), -var(U, 2)))
            f.write(open(lifted).read())
        dr = subprocess.run([DRATTRIM, pa, badU, "-f"], capture_output=True, text=True, timeout=1800)
        amoU_ver = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
        # 資訊性 (唔 assert): AMO(U) 引理一般唔係 RAT (審核員用 Mycielski M5 示範咗 NOT VERIFIED), 但喺個別實例可以係 RUP 可推導 → 合法 VERIFIED;
        # 排除 A,B 係「一定安全」嘅做法, 唔係「一定必要」
        log.append("AMO(U=%d) 引理 (same pair 成員) drat-trim -f: %s" % (U, "VERIFIED (呢個實例 RUP 可推導)" if amoU_ver else "NOT VERIFIED (RAT 唔成立, 排除 A,B 係必要)"))
        print("  · " + log[-1], flush=True)
        # 毒藥 4: 釘色頂點嘅 AMO 引理 pivot 擺錯 (unit literal 嘅否定行先), 另一隻色揀三角形冇用嘅第 4 色 → RUP 唔成立, RAT pivot 頂層為假 → 失敗
        tpin = next(c[0] for c in cla if len(c) == 1 and c[0] > 0)          # 例如 x_{t,1}
        tv, tc = (tpin - 1) // K + 1, (tpin - 1) % K + 1
        oc = 4
        badP = os.path.join(a.out, "st_510_badpivot.drat")
        with open(badP, "w") as f:
            f.write("%d %d 0\n" % (-var(tv, tc), -var(tv, oc)))
            f.write(open(lifted).read())
        dr = subprocess.run([DRATTRIM, pa, badP, "-f"], capture_output=True, text=True, timeout=1800)
        assert not any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()), "錯 pivot 引理竟然 VERIFIED"
        ok("毒藥: 釘色頂點 %d 嘅 AMO 引理 pivot 擺錯 → drat-trim -f NOT VERIFIED (證明 pivot 規則係必要)" % tv)
        # 對照: (b) 嘅 DRAT 直接對 (a) CNF (冇引理)
        dr = subprocess.run([DRATTRIM, pa, db], capture_output=True, text=True, timeout=1800)
        log.append("(b) DRAT 直接對 (a) CNF (冇引理): %s" % ("VERIFIED (kissat 冇用到 AMO)" if any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()) else "NOT VERIFIED (預期: 證明依賴 AMO)"))
        print("  · " + log[-1], flush=True)
    json.dump({"ok": log, "t_s": round(time.time() - t0, 1), "A": A, "B": B, "sigma_fixed": geo["fixed_points"]},
              open(os.path.join(a.out, "selftest.json"), "w"), indent=1, ensure_ascii=False)
    print("[selftest] 全部通過 (%.1fs)" % (time.time() - t0), flush=True)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--edge", required=True); b.add_argument("--cvtx", required=True)
    b.add_argument("--variant", required=True, choices=list("abcd")); b.add_argument("--out", required=True)
    b.add_argument("--tag", default=None); b.add_argument("--plain", action="store_true")
    s = sub.add_parser("selftest"); s.add_argument("--edge", required=True); s.add_argument("--cvtx", required=True); s.add_argument("--out", required=True)
    s.add_argument("--phase2-cnf", default=None); s.add_argument("--g510", default=None)
    l = sub.add_parser("lift"); l.add_argument("--edge", required=True); l.add_argument("--cvtx", required=True)
    l.add_argument("--cnf-b", required=True, help="(b)-式 CNF (用嚟讀正 unit: pin + cube)"); l.add_argument("--drat-b", required=True); l.add_argument("--out-lifted", required=True)
    a = ap.parse_args()
    {"build": cmd_build, "selftest": cmd_selftest, "lift": cmd_lift}[a.cmd](a)

if __name__ == "__main__":
    main()
