#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exactfield.py —— Phase 2 Step 1: 分圓數域精確代數層 (Q(ζ_N), 無浮點判定)

點 = 複數 z = x + iy ∈ Q(ζ_N), ζ_N = exp(2πi/N).
表示: φ(N) 個整數係數 (基 1, ζ, ..., ζ^{φ(N)-1}) + 一個正整數公分母, 永遠約到最簡.
乘法: 多項式乘法之後 mod Φ_N(x) (Φ_N 由整數多項式除法計出, selftest 同 sympy 對數).
共軛: conj(ζ^k) = ζ^{N-k}.
距離²: |z1 - z2|² = (z1 - z2) · conj(z1 - z2);「== 1」= canonical form 係 (1, 0, ..., 0)/1.

.cvtx 檔案格式 (精確坐標):
    p cvtx N=<N> dim=<φ(N)> n=<頂點數>
    <D> <c0> <c1> ... <c_{φ(N)-1}>        # 一行一個頂點, 代表 (Σ c_k ζ^k) / D, 全部整數, D > 0
.edge 檔案格式: 同 CNP-SAT (p edge n m / e u v, 1-based).

用法:
    python3 exactfield.py check <cvtx> <edge> [--selftest]   # 逐條邊精確驗 |z_u - z_v|² == 1
    python3 exactfield.py convert <vtx> <cvtx> [--N 660]      # Mathematica {x, y} (Sqrt[..]) -> .cvtx
    python3 exactfield.py selftest [--old-vtx V --old-edge E] # 全套自檢 + 毒藥測試 (預設用 CNP-SAT 553)
"""
import sys, os, math, random, time, argparse, tempfile, io, contextlib, hashlib
from fractions import Fraction
from math import gcd

if not __debug__:
    sys.exit("!! 唔准用 python -O 跑呢個檢查器 (assert 會被剝走, 檢查形同虛設)")

# ============================================================
# 整數多項式工具 (係數 list, index = 次數)
# ============================================================

def poly_mul(a, b):
    r = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x:
            for j, y in enumerate(b):
                r[i + j] += x * y
    return r

def poly_div_exact(a, b):
    """a / b, b 必須 monic, 必須整除 (否則 raise)。"""
    assert b[-1] == 1, "除數唔係 monic"
    a = list(a)
    q = [0] * (len(a) - len(b) + 1)
    for i in range(len(a) - len(b), -1, -1):
        c = a[i + len(b) - 1]
        q[i] = c
        if c:
            for j, y in enumerate(b):
                a[i + j] -= c * y
    assert all(x == 0 for x in a), "多項式除法有餘數 —— Φ_N 計算出錯"
    return q

def divisors(n):
    return [d for d in range(1, n + 1) if n % d == 0]

def prime_factors(n):
    ps, p = [], 2
    while p * p <= n:
        if n % p == 0:
            ps.append(p)
            while n % p == 0:
                n //= p
        p += 1
    if n > 1:
        ps.append(n)
    return ps

def is_squarefree(n):
    for p in prime_factors(n):
        if n % (p * p) == 0:
            return False
    return True

def euler_phi(n):
    r = n
    for p in prime_factors(n):
        r = r // p * (p - 1)
    return r

_cyc_memo = {}
def cyclotomic_int(n):
    """Φ_n(x) 整數係數 (低次到高次): Φ_n = (x^n - 1) / ∏_{d|n, d<n} Φ_d。"""
    if n in _cyc_memo:
        return _cyc_memo[n]
    num = [-1] + [0] * (n - 1) + [1]
    for d in divisors(n):
        if d < n:
            num = poly_div_exact(num, cyclotomic_int(d))
    _cyc_memo[n] = num
    return num

# ============================================================
# 數域 Q(ζ_N)
# ============================================================

class CycField:
    def __init__(self, N):
        assert isinstance(N, int) and N >= 1
        self.N = N
        self.Phi = cyclotomic_int(N)
        self.dim = len(self.Phi) - 1
        assert self.dim == euler_phi(N), f"Φ_{N} 次數 {self.dim} != φ({N}) = {euler_phi(N)}"
        d = self.dim
        # pw[k] = x^k mod Φ_N, k = 0 .. max(2d-2, N)
        top_k = max(2 * d - 2, N)
        pw = [None] * (top_k + 1)
        cur = [0] * d
        cur[0] = 1
        pw[0] = tuple(cur)
        for k in range(1, top_k + 1):
            lead = cur[d - 1]
            cur = [0] + cur[:d - 1]
            if lead:
                for i in range(d):
                    cur[i] -= lead * self.Phi[i]
            pw[k] = tuple(cur)
        self.pw = pw
        assert pw[N] == pw[0], "ζ^N != 1 —— 約簡表出錯"
        # 數值用 (只用於候選搜尋 / 排序, 永遠唔用嚟落判定)
        self._roots = [complex(math.cos(2 * math.pi * k / N), math.sin(2 * math.pi * k / N))
                       for k in range(d)]

    # ---- 向量層 ----
    def mulvec(self, a, b):
        d = self.dim
        c = [0] * (2 * d - 1)
        for i, x in enumerate(a):
            if x:
                for j, y in enumerate(b):
                    if y:
                        c[i + j] += x * y
        out = c[:d]
        for k in range(d, 2 * d - 1):
            ck = c[k]
            if ck:
                pk = self.pw[k]
                for i in range(d):
                    if pk[i]:
                        out[i] += ck * pk[i]
        return out

    def conjvec(self, a):
        d = self.dim
        out = [0] * d
        N = self.N
        for k, x in enumerate(a):
            if x:
                pk = self.pw[(N - k) % N]
                for i in range(d):
                    if pk[i]:
                        out[i] += x * pk[i]
        return out

    # ---- 元素工廠 ----
    def el(self, num, den=1):
        return El(self, num, den)

    def rational(self, p, q=1):
        v = [0] * self.dim
        v[0] = p
        return El(self, v, q)

    def zero(self):
        return self.rational(0)

    def one(self):
        return self.rational(1)

    def zeta(self, k):
        return El(self, self.pw[k % self.N], 1)

    def i_unit(self):
        assert self.N % 4 == 0, f"N={self.N} 無 i (要 4 | N)"
        return self.zeta(self.N // 4)

    def embed(self, other_el):
        """將 Q(ζ_M) 嘅元素嵌入 Q(ζ_N), 要求 M | N: ζ_M = ζ_N^{N/M}。"""
        M = other_el.F.N
        assert self.N % M == 0, f"{M} 唔整除 {self.N}, 無法嵌入"
        step = self.N // M
        v = [0] * self.dim
        for k, x in enumerate(other_el.num):
            if x:
                pk = self.pw[(k * step) % self.N]
                for i in range(self.dim):
                    v[i] += x * pk[i]
        return El(self, v, other_el.den)

    def inv(self, a):
        """1/a: 解線性方程組 (Fraction 高斯消去), 之後精確驗證 a · b == 1。"""
        d = self.dim
        assert not a.is_zero(), "唔可以除以 0"
        cols = [self.mulvec(a.num, self.pw[j]) for j in range(d)]   # a·ζ^j (未除 a.den)
        M = [[Fraction(cols[j][i]) for j in range(d)] + [Fraction(1 if i == 0 else 0)]
             for i in range(d)]
        for c in range(d):
            piv = next((r for r in range(c, d) if M[r][c] != 0), None)
            assert piv is not None, "矩陣奇異 —— a 唔可逆?"
            M[c], M[piv] = M[piv], M[c]
            pv = M[c][c]
            M[c] = [x / pv for x in M[c]]
            for r in range(d):
                if r != c and M[r][c] != 0:
                    f = M[r][c]
                    M[r] = [x - f * y for x, y in zip(M[r], M[c])]
        xs = [M[r][d] * a.den for r in range(d)]      # 補返 a.den
        L = 1
        for x in xs:
            L = L * x.denominator // gcd(L, x.denominator)
        b = El(self, [int(x * L) for x in xs], L)
        assert (a * b).is_one(), "inv 驗證失敗: a·b != 1"
        return b

    def sqrt_int(self, dd):
        """√dd (dd 正無平方因子整數) 用 Gauss sum 砌出嚟, 精確驗證 s² == dd, 數值揀正號。"""
        assert dd >= 1 and is_squarefree(dd), f"√{dd}: 要正無平方因子整數"
        s = self.one()
        for p in prime_factors(dd):
            if p == 2:
                assert self.N % 8 == 0, f"√2 要 8 | N (N={self.N})"
                s = s * (self.zeta(self.N // 8) + self.zeta(-(self.N // 8)))
            else:
                assert self.N % p == 0, f"√{p} 要 {p} | N (N={self.N})"
                g = self.zero()
                for a in range(1, p):
                    leg = pow(a, (p - 1) // 2, p)          # Legendre symbol (a/p)
                    leg = 1 if leg == 1 else -1
                    g = g + self.zeta(a * (self.N // p)) * leg
                if p % 4 == 1:
                    s = s * g                              # g² = p
                else:
                    assert self.N % 4 == 0, f"√{p} (p≡3 mod 4) 要 4 | N"
                    s = s * g * self.zeta(-(self.N // 4))  # g = ±i√p → 乘 -i
        assert (s * s) == self.rational(dd), f"√{dd} 精確驗證失敗: s² != {dd}"
        if s.to_float().real < 0:
            s = -s
        val = s.to_float()
        assert abs(val - math.sqrt(dd)) < 1e-9, f"√{dd} 數值對唔上: {val}"
        return s


class El:
    __slots__ = ("F", "num", "den")

    def __init__(self, F, num, den=1):
        num = list(num)
        assert len(num) == F.dim, f"向量長度 {len(num)} != dim {F.dim}"
        assert isinstance(den, int) and den != 0, "分母必須係非零整數"
        for x in num:
            assert isinstance(x, int), f"係數必須係整數, 收到 {type(x).__name__}: {x!r}"
        if den < 0:
            num = [-x for x in num]
            den = -den
        g = den
        for x in num:
            g = gcd(g, x)
            if g == 1:
                break
        if g > 1:
            num = [x // g for x in num]
            den //= g
        self.F = F
        self.num = tuple(num)
        self.den = den

    def _coerce(self, o):
        if isinstance(o, El):
            assert o.F is self.F, "唔同數域嘅元素唔可以直接運算 (用 embed)"
            return o
        if isinstance(o, int):
            return self.F.rational(o)
        if isinstance(o, Fraction):
            return self.F.rational(o.numerator, o.denominator)
        raise TypeError(f"唔識同 {type(o).__name__} 運算")

    def __add__(self, o):
        o = self._coerce(o)
        if self.den == o.den:
            return El(self.F, [a + b for a, b in zip(self.num, o.num)], self.den)
        return El(self.F, [a * o.den + b * self.den for a, b in zip(self.num, o.num)],
                  self.den * o.den)

    __radd__ = __add__

    def __neg__(self):
        return El(self.F, [-a for a in self.num], self.den)

    def __sub__(self, o):
        return self + (-self._coerce(o))

    def __rsub__(self, o):
        return self._coerce(o) - self

    def __mul__(self, o):
        if isinstance(o, int):
            return El(self.F, [a * o for a in self.num], self.den)
        o = self._coerce(o)
        return El(self.F, self.F.mulvec(self.num, o.num), self.den * o.den)

    __rmul__ = __mul__

    def __truediv__(self, o):
        if isinstance(o, int):
            return El(self.F, self.num, self.den * o)
        return self * self.F.inv(self._coerce(o))

    def conj(self):
        return El(self.F, self.F.conjvec(self.num), self.den)

    def norm2(self):
        """|z|² = z · conj(z) (精確)"""
        return self * self.conj()

    def __eq__(self, o):
        if isinstance(o, (int, Fraction)):
            o = self._coerce(o)
        if not isinstance(o, El):
            return NotImplemented
        return self.F is o.F and self.num == o.num and self.den == o.den

    def __ne__(self, o):
        r = self.__eq__(o)
        return r if r is NotImplemented else (not r)

    def __hash__(self):
        return hash((self.num, self.den))

    def is_zero(self):
        return not any(self.num)

    def is_one(self):
        return self.den == 1 and self.num[0] == 1 and not any(self.num[1:])

    def to_float(self):
        """數值 (float complex) —— 只用於候選搜尋, 唔准用嚟落判定"""
        return sum(c * r for c, r in zip(self.num, self.F._roots) if c) / self.den

    def to_mpc(self, dps=50):
        import mpmath as mp
        with mp.workdps(dps):
            z = mp.mpc(0)
            for k, c in enumerate(self.num):
                if c:
                    z += c * mp.expjpi(mp.mpf(2 * k) / self.F.N)
            return z / self.den

    def __repr__(self):
        return f"El(N={self.F.N}, {list(self.num)}/{self.den})"


# ============================================================
# 檔案 I/O
# ============================================================

def write_cvtx(path, F, points):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"p cvtx N={F.N} dim={F.dim} n={len(points)}\n")
        for z in points:
            assert z.F is F
            f.write(str(z.den) + " " + " ".join(map(str, z.num)) + "\n")
    os.replace(tmp, path)

_INT_OK = set("-0123456789")

MAX_DIGITS = 60      # 整數 token 位數上限 (攻擊者: 10^400 級坐標令浮點預篩 OverflowError; 我哋嘅係數得幾位數)

def _strict_int(tok, where):
    # 只收純整數字面值: 唔收 '1.5', '1e3', '1/2', '+3', ' 3 ', 前導零
    assert tok and set(tok) <= _INT_OK and tok.lstrip("-").isdigit() and tok.count("-") <= 1 \
        and (not tok.startswith("-") or len(tok) > 1), f"{where}: 唔係整數字面值 {tok!r}"
    d = tok.lstrip("-")
    assert len(d) <= MAX_DIGITS, f"{where}: 整數 {tok[:20]}… 有 {len(d)} 位, 超過上限 {MAX_DIGITS}"
    assert d == "0" or not d.startswith("0"), f"{where}: 唔收前導零 {tok!r}"
    return int(tok)

MAX_VERTICES = 200000  # .edge / .cvtx 頂點數上限 (攻擊者: 一行 header n=1e8 可以迫爆記憶體)
MAX_N = 1000          # 分圓指數上限 (防 attacker 用 header N 迫檢查器起 O(N²) 表 / 長時間 DoS); 我哋只用 84, 420, 660

def _split(line, where):
    """只收 ASCII 空格/tab 做分隔; 其他空白字元 (NBSP, form-feed, U+001C ...) 一律拒收"""
    assert all((ch == " " or ch == "\t" or not ch.isspace()) for ch in line), \
        f"{where}: 有非 ASCII 空白字元 {[hex(ord(c)) for c in line if c.isspace() and c not in ' \t']}"
    return line.split()

def read_cvtx(path):
    raw = open(path, "rb").read()
    lines = [ln.rstrip("\r") for ln in raw.decode("ascii").split("\n")]   # 非 ASCII 直接讀唔到; 只認 LF 做行尾
    if lines and lines[-1] == "":
        lines.pop()
    assert lines, ".cvtx 係空嘅"
    hdr = _split(lines[0], "header")
    assert len(hdr) == 5 and hdr[0] == "p" and hdr[1] == "cvtx", f"header 唔啱: {lines[0]!r}"
    kv = {}
    for t in hdr[2:]:
        k, _, v = t.partition("=")
        kv[k] = _strict_int(v, "header")
    assert set(kv) == {"N", "dim", "n"}, f"header 欄位唔啱: {kv}"
    N, dim, n = kv["N"], kv["dim"], kv["n"]
    assert 1 <= N <= MAX_N and 1 <= n <= MAX_VERTICES, f"header N 必須喺 1..{MAX_N}, n 必須喺 1..{MAX_VERTICES}"
    F = CycField(N)
    assert F.dim == dim, f"header dim={dim} 但 φ({N}) = {F.dim}"
    pts = []
    for ln_no, line in enumerate(lines[1:], 2):
        assert line.strip(), f"第 {ln_no} 行: .cvtx 唔收空行"
        assert not line.startswith("c"), f"第 {ln_no} 行: .cvtx 唔收注釋行"
        toks = _split(line, f"第 {ln_no} 行")
        assert len(toks) == dim + 1, f"第 {ln_no} 行: 要 {dim + 1} 個整數, 得 {len(toks)} 個"
        D = _strict_int(toks[0], f"第 {ln_no} 行分母")
        assert D > 0, f"第 {ln_no} 行: 分母 {D} 必須 > 0"
        cs = [_strict_int(t, f"第 {ln_no} 行") for t in toks[1:]]
        pts.append(El(F, cs, D))
    assert len(pts) == n, f"header 話 n={n}, 實際 {len(pts)} 個頂點"
    # 單位距離圖嘅頂點必須係相異嘅點: 重合點會令 K_{2,3} 之類「非 UDG」照樣全邊長 1 (攻擊者搵到嘅漏洞)
    seen = {}
    for i, z in enumerate(pts):
        k = (z.num, z.den)
        assert k not in seen, f"頂點 #{i + 1} 同頂點 #{seen[k] + 1} 坐標完全相同 —— 唔係合法單位距離圖"
        seen[k] = i
    F.src_sha256 = hashlib.sha256(raw).hexdigest()          # 同一份 bytes 嘅 hash (無 TOCTOU)
    return F, pts

_edge_sha = {}
def load_edges(path):
    n = m = None
    edges = []
    rawb = open(path, "rb").read()
    _edge_sha[os.path.abspath(path)] = hashlib.sha256(rawb).hexdigest()
    raw = rawb.decode("ascii").split("\n")               # 只認 LF (唔用 splitlines: \x0b \x0c \x1c-\x1e 會被當行尾)
    for ln_no, line in enumerate(raw, 1):
        line = line.rstrip("\r")
        t = _split(line, f".edge 第 {ln_no} 行")
        if not t:
            continue
        assert t[0] != "c", f".edge 第 {ln_no} 行: 唔收注釋行 (注釋 = 免費 nonce 空間, 會溝亂證書綁定)"
        if t[0] == "p":
            assert n is None, "p 行出現多過一次"
            assert len(t) == 4 and t[1] == "edge", f"p 行格式唔啱: {line!r}"
            n, m = _strict_int(t[2], "p 行"), _strict_int(t[3], "p 行")
        elif t[0] == "e":
            assert len(t) == 3, f"e 行格式唔啱: {line!r}"
            edges.append((_strict_int(t[1], "e 行"), _strict_int(t[2], "e 行")))
        else:
            raise AssertionError(f"唔識嘅行: {line!r}")
    assert n is not None and n > 0, "冇 p 行 / n <= 0"
    assert n <= MAX_VERTICES, f"header n={n} 超過上限 {MAX_VERTICES} (防 header 造假迫爆記憶體)"
    assert len(edges) == m, f"邊數對唔上: p 行話 {m}, 實際 {len(edges)}"
    assert edges, "邊表係空嘅 —— 冇嘢可驗, 唔可以算通過"
    for u, v in edges:
        assert 1 <= u <= n and 1 <= v <= n, f"邊 ({u},{v}) 索引超出 1..{n}"
        assert u != v, f"邊 ({u},{v}) 係 self-loop"
    assert len({frozenset(e) for e in edges}) == m, "邊表有重複邊"
    return n, edges

# ============================================================
# 核心檢查
# ============================================================

def check_edges(pts, edges):
    """回傳 (壞邊 list [(u, v, d2)], 用時)"""
    bad = []
    t0 = time.time()
    for u, v in edges:
        d2 = (pts[u - 1] - pts[v - 1]).norm2()
        if not d2.is_one():
            bad.append((u, v, d2))
    return bad, time.time() - t0

def check_files(cvtx_path, edge_path, selftest=False, quiet=False):
    """全套: 讀檔 → 逐邊精確驗證 → (可選) 整壞坐標睇檢查器揭唔揭發。出錯 raise AssertionError。"""
    name = os.path.basename(cvtx_path)
    t0 = time.time()
    F, pts = read_cvtx(cvtx_path)
    n, edges = load_edges(edge_path)
    assert len(pts) == n, f"頂點數對唔上: .cvtx 有 {len(pts)}, .edge 話 {n}"
    t_parse = time.time() - t0
    bad, t_check = check_edges(pts, edges)
    if not quiet:
        print(f"[{name}] N={F.N} (dim {F.dim}), {len(pts)} 個頂點 (parse {t_parse:.1f}s), {len(edges)} 條邊")
        print(f"[{name}] sha256 cvtx={F.src_sha256}\n[{name}] sha256 edge={_edge_sha[os.path.abspath(edge_path)]} "
              f"(證書只對應呢兩個檔案; hash 同 parse 用同一份 bytes)")
    if bad:
        msg = f"[{name}] !! 有 {len(bad)} 條邊唔係長度 1:\n" + "\n".join(
            f"      邊 ({u},{v}): 距離平方 = {d2}" for u, v, d2 in bad[:10])
        raise AssertionError(msg)
    if not quiet:
        print(f"[{name}] {len(edges)}/{len(edges)} 條邊精確長度 1  (驗證 {t_check:.1f}s, 全程無浮點) ✓")
    if selftest:
        u0 = edges[0][0]
        pts_bad = list(pts)
        pts_bad[u0 - 1] = pts[u0 - 1] + F.zeta(1) * Fraction(1, 1000)
        touched = [(u, v) for (u, v) in edges if u == u0 or v == u0]
        bad2, _ = check_edges(pts_bad, touched)
        assert len(bad2) == len(touched), "!! selftest 失敗: 整壞咗坐標, 檢查器竟然冇發現!"
        if not quiet:
            print(f"[{name}] selftest: 故意整壞頂點 {u0} 後, {len(bad2)}/{len(touched)} 條相關邊即刻被揭發 ✓ (檢查器有牙)")
    return F, pts, edges

def check_complete(cvtx_path, edge_path, tol=1e-6, quiet=False):
    """「.edge 係呢個點集嘅完整單位距離圖」認證 (攻擊者指出嘅前提):
    全對浮點預篩 |d-1| < tol (真單位對嘅浮點誤差 ~1e-13, 唔可能漏), 候選逐對精確核實 norm2 == 1,
    然後要求 {精確單位對} == {邊表}: 唔可以漏單位對, 亦唔可以有非單位邊。回傳 (n_unit_pairs, near_misses)。"""
    import numpy as np
    F, pts = read_cvtx(cvtx_path)
    n, edges = load_edges(edge_path)
    assert len(pts) == n, f"頂點數對唔上: .cvtx {len(pts)} vs .edge {n}"
    # 浮點預篩嘅嚴格性: to_float 絕對誤差 <= 4·dim·S·2^-53 (S = Σ|c_k|/D), 一對點嘅距離誤差 <= 兩者之和。
    # 要求最壞情況 < tol/4, 否則預篩可能漏真單位對 (攻擊者搵到: 巨大係數) → 退回精確全對 (慢但穩)
    S = max(sum(abs(c) for c in z.num) / z.den for z in pts)
    err_bound = 2 * 4 * F.dim * S * 2.0 ** -53
    exact_all = err_bound >= tol / 4
    if exact_all and not quiet:
        print(f"[{os.path.basename(cvtx_path)}] !! 係數太大 (S={S:.3g}, 浮點誤差上界 {err_bound:.2e} >= tol/4), 預篩唔可靠 → 退回精確全對掃描")
    zs = np.array([z.to_float() for z in pts])
    eset = {(min(u, v), max(u, v)) for u, v in edges}
    unit, near = set(), []
    Bk = 1024
    t0 = time.time()
    for i0 in range(0, n, Bk):
        d = np.abs(zs[i0:i0 + Bk, None] - zs[None, :])
        ii, jj = np.nonzero(np.abs(d - 1.0) < tol) if not exact_all else np.nonzero(d >= -1)   # exact_all: 全部對精確核
        for a, b in zip(ii, jj):
            i, j = i0 + int(a) + 1, int(b) + 1
            if i < j:
                if (pts[i - 1] - pts[j - 1]).norm2().is_one():
                    unit.add((i, j))
                else:
                    near.append((i, j, float(d[a, b])))
    missing = unit - eset
    extra_e = eset - unit
    name = os.path.basename(cvtx_path)
    if not quiet:
        print(f"[{name}] sha256 cvtx={F.src_sha256} edge={_edge_sha[os.path.abspath(edge_path)]}")
        print(f"[{name}] 完整性: {n} 點 {n * (n - 1) // 2} 對全掃 ({time.time() - t0:.1f}s; 浮點誤差上界 {err_bound:.1e} "
              f"{'<' if not exact_all else '>='} tol/4={tol / 4:.1e}{' ✓' if not exact_all else ' → 已精確全對'}); "
              f"精確單位距離對 {len(unit)}, 邊表 {len(eset)}; 漏咗 {len(missing)}, 非單位邊 {len(extra_e)}; "
              f"近似陷阱 (|d-1|<{tol} 但精確≠1) {len(near)}" + (f" 例如 {near[:3]}" if near else ""))
    assert not missing, f"!! 邊表漏咗 {len(missing)} 對精確單位距離對, 例如 {sorted(missing)[:5]} —— 唔係完整 UDG"
    assert not extra_e, f"!! 邊表有 {len(extra_e)} 條非單位邊, 例如 {sorted(extra_e)[:5]}"
    if not quiet:
        print(f"[{name}] 邊表 == 點集嘅完整單位距離圖 ✓ ({len(unit)} 條)")
    return len(unit), near

# ============================================================
# Mathematica .vtx -> .cvtx (老圖用, 域 Q(√3, √5, √11) ⊂ Q(ζ_660))
# ============================================================

def _old_layer():
    """借用 Phase 0 加固版 exact_check.py 嘅 parser (原封不動)"""
    sys.path.insert(0, os.path.expanduser("~/hadwiger"))
    import exact_check
    return exact_check

def sympy_to_el(F, expr, sq):
    import sympy as sp
    expr = sp.expand(expr)
    total = F.zero()
    for term in sp.Add.make_args(expr):
        coef = Fraction(1)
        rad = F.one()
        for fac in sp.Mul.make_args(term):
            if fac.is_Rational:
                coef *= Fraction(int(fac.p), int(fac.q))
            elif fac.is_Pow and fac.exp == sp.Rational(1, 2) and fac.base.is_Integer and fac.base > 0:
                b = int(fac.base)
                assert is_squarefree(b), f"sqrt({b}) 唔係無平方因子"
                for p in prime_factors(b):
                    if p not in sq:
                        sq[p] = F.sqrt_int(p)
                    rad = rad * sq[p]
            else:
                raise AssertionError(f"唔識將 {fac!r} 轉入 Q(ζ_{F.N})")
        total = total + rad * F.rational(coef.numerator, coef.denominator)
    # 數值守門: 轉換結果必須同 sympy 數值一致 (防 parser 錯配)
    val = complex(sp.N(expr, 20))
    got = total.to_float()
    assert abs(val - got) <= 1e-9 * max(1.0, abs(val)), f"轉換數值對唔上: sympy {val} vs 分圓 {got} ({expr})"
    return total

_VTX_OK = set("0123456789+-*/(){}[], \tSqrt\r\n")
def convert_vtx(vtx_path, cvtx_path, N=660):
    # parse_vtx 用 sympify (等同 eval): 先做字元白名單 (攻擊者: .vtx 可以塞 Python 碼)
    bad = sorted({ch for ch in open(vtx_path, encoding="ascii").read() if ch not in _VTX_OK})
    assert not bad, f".vtx 含白名單以外字元 {bad!r} —— 拒絕交俾 sympify"
    ec = _old_layer()
    F = CycField(N)
    I = F.i_unit()
    sq = {}
    pts = []
    for (x, y) in ec.parse_vtx(vtx_path):
        pts.append(sympy_to_el(F, x, sq) + I * sympy_to_el(F, y, sq))
    write_cvtx(cvtx_path, F, pts)
    return F, pts

# ============================================================
# Selftest 全套
# ============================================================

def _expect_reject(label, fn):
    try:
        fn()
    except (AssertionError, ValueError, TypeError, KeyError) as e:
        print(f"    毒藥「{label}」被拒 ✓  ({str(e).splitlines()[0][:90]})")
        return
    raise AssertionError(f"!! 毒藥「{label}」竟然通過 —— 檢查器有漏洞")

def selftest(old_vtx, old_edge, seed=20260905):
    import sympy as sp
    rng = random.Random(seed)
    print("== A. Φ_N: 自家整數多項式 vs sympy.cyclotomic_poly ==")
    x = sp.Symbol("x")
    for N in (1, 2, 3, 4, 6, 7, 12, 28, 84, 420, 660):
        mine = cyclotomic_int(N)
        theirs = [int(c) for c in reversed(sp.Poly(sp.cyclotomic_poly(N, x), x).all_coeffs())]
        assert mine == theirs, f"Φ_{N} 對唔上 sympy"
        assert len(mine) - 1 == euler_phi(N)
    print("    Φ_N 對 N ∈ {1,2,3,4,6,7,12,28,84,420,660} 全部一致, 次數 = φ(N) ✓")

    print("== B. 環算術 vs sympy Poly mod Φ_N + 50 位數值 ==")
    import mpmath as mp
    for N in (84, 420, 660):
        F = CycField(N)
        Phi = sp.Poly(sp.cyclotomic_poly(N, x), x)
        for trial in range(20 if N != 660 else 5):
            a = F.el([rng.randint(-9, 9) for _ in range(F.dim)], rng.randint(1, 7))
            b = F.el([rng.randint(-9, 9) for _ in range(F.dim)], rng.randint(1, 7))
            ab = a * b
            pa = sp.Poly([Fraction(c, a.den) for c in reversed(a.num)], x, domain="QQ")
            pb = sp.Poly([Fraction(c, b.den) for c in reversed(b.num)], x, domain="QQ")
            r = (pa * pb).rem(Phi)
            coeffs = list(reversed(r.all_coeffs())) + [0] * F.dim
            for k in range(F.dim):
                assert Fraction(ab.num[k], ab.den) == Fraction(str(coeffs[k])), f"N={N} 乘法同 sympy 唔一致"
            with mp.workdps(50):
                va, vb, vab = a.to_mpc(), b.to_mpc(), ab.to_mpc()
                assert abs(va * vb - vab) < mp.mpf(10) ** -40, "乘法數值對唔上"
                vc = a.conj().to_mpc()
                assert abs(vc - mp.conj(va)) < mp.mpf(10) ** -40, "conj 數值對唔上"
                assert abs(a.norm2().to_mpc() - abs(va) ** 2) < mp.mpf(10) ** -40, "norm2 數值對唔上"
            assert a.conj().conj() == a
            assert (a + b) - b == a
        for k in range(N):
            assert F.zeta(k).norm2().is_one(), f"|ζ^{k}|² != 1"
            assert F.zeta(k) * F.zeta(N - k) == F.one()
        a = F.el([rng.randint(-5, 5) for _ in range(F.dim)], 3)
        assert (a * F.inv(a)).is_one()
        assert F.rational(2, 2) == F.one() and F.rational(6, 4) == F.rational(3, 2)
        print(f"    N={N}: {20 if N != 660 else 5} 對隨機元素乘法/conj/norm2 同 sympy + mpmath(50 位) 全部一致; |ζ^k|²=1 全 {N} 個 ✓; inv ✓")

    print("== C. 根號 (Gauss sum) 精確驗證 ==")
    F84, F420, F660 = CycField(84), CycField(420), CycField(660)
    s3 = F84.sqrt_int(3)
    assert s3 == F84.zeta(7) + F84.zeta(77), "√3 應該 = ζ_12 + ζ_12^{-1}"
    I = F84.i_unit()
    assert I * I == F84.rational(-1)
    s5 = F420.sqrt_int(5)
    s15 = F420.sqrt_int(15)
    assert s15 == F420.sqrt_int(3) * s5
    assert F420.embed(s3) == F420.sqrt_int(3), "嵌入 84→420 後 √3 唔一致"
    s11 = F660.sqrt_int(11)
    print(f"    N=84: √3 = ζ_12+ζ_12⁻¹ ✓, i² = -1 ✓;  N=420: √5² = 5 ✓, √15 = √3·√5 ✓, embed(√3) ✓;  N=660: √11² = 11 ✓")
    print(f"    √3 ≈ {s3.to_float().real:.12f}, √5 ≈ {s5.to_float().real:.12f}, √11 ≈ {s11.to_float().real:.12f}")

    print(f"== D. 老圖交叉驗證 (Phase 0 sympy 層 vs 新分圓層): {os.path.basename(old_vtx)} ==")
    ec = _old_layer()
    pts_old = ec.parse_vtx(old_vtx)
    n, edges = ec.load_edges(old_edge)
    assert len(pts_old) == n
    tmpd = tempfile.mkdtemp(prefix="exactfield_")
    cv = os.path.join(tmpd, "old.cvtx")
    t0 = time.time()
    F, pts_new = convert_vtx(old_vtx, cv, 660)
    print(f"    轉換 {n} 點入 Q(ζ_660) (dim {F.dim}) 用時 {time.time() - t0:.1f}s")
    F2, pts_re = read_cvtx(cv)
    assert [(p.num, p.den) for p in pts_re] == [(p.num, p.den) for p in pts_new], "寫檔再讀返唔一致"

    def old_is_unit(u, v):
        d2 = ec.edge_d2(pts_old, u, v)
        return d2 == 1 or sp.simplify(d2 - 1) == 0

    def new_is_unit(P, u, v):
        return (P[u - 1] - P[v - 1]).norm2().is_one()

    sample_e = rng.sample(edges, 50)
    agree = 0
    for u, v in sample_e:
        o, nw = old_is_unit(u, v), new_is_unit(pts_new, u, v)
        assert o and nw, f"邊 ({u},{v}): 舊層 {o} 新層 {nw}"
        agree += 1
    print(f"    50 條隨機邊: 兩層都話距離 1 ({agree}/50) ✓")
    eset = {frozenset(e) for e in edges}
    non = []
    while len(non) < 50:
        u, v = rng.randint(1, n), rng.randint(1, n)
        if u != v and frozenset((u, v)) not in eset:
            non.append((u, v))
    n_unit = 0
    for u, v in non:
        o, nw = old_is_unit(u, v), new_is_unit(pts_new, u, v)
        assert o == nw, f"非邊對 ({u},{v}): 舊層 {o} 新層 {nw} 唔一致"
        n_unit += nw
    print(f"    50 對隨機非邊: 兩層判定完全一致 (其中 {n_unit} 對其實係單位距離) ✓")
    # 合成「單位距離但唔係邊」嘅對: q = p + (1,0) 同 q = p + (1/2, √3/2); 兩層都必須話 1 (攻擊者: 舊樣本冇正例)
    syn_ok = 0
    for u, v in sample_e[:10]:
        for (dx, dy, dz) in ((1, 0, F.one()), (sp.Rational(1, 2), sp.sqrt(3) / 2, F.zeta(F.N // 6))):
            xo, yo = pts_old[u - 1]
            pts_old_b = list(pts_old); pts_old_b.append((xo + dx, yo + dy))
            d2 = ec.edge_d2(pts_old_b, u, len(pts_old_b))
            o = (d2 == 1 or sp.simplify(d2 - 1) == 0)
            pn = list(pts_new); pn.append(pts_new[u - 1] + dz)
            nw = new_is_unit(pn, u, len(pn))
            assert o and nw, f"合成單位對 ({u}, +{dx},{dy}): 舊層 {o} 新層 {nw}"
            syn_ok += 1
    print(f"    {syn_ok} 對合成單位距離非邊 (p+(1,0), p+(½,√3/2)): 兩層都話 1 ✓")
    s3_660 = F.sqrt_int(3)
    for u, v in sample_e[:10]:
        xo, yo = pts_old[u - 1]
        pts_old_b = list(pts_old)
        pts_old_b[u - 1] = (xo + sp.sqrt(3) / 1000, yo)      # 同一個擾動, 兩層各自判
        d2 = ec.edge_d2(pts_old_b, u, v)
        o = (d2 == 1 or sp.simplify(d2 - 1) == 0)
        pn = list(pts_new)
        pn[u - 1] = pts_new[u - 1] + s3_660 * Fraction(1, 1000)
        nw = new_is_unit(pn, u, v)
        assert (not o) and (not nw), f"擾動後 ({u},{v}) 舊層 {o} 新層 {nw}"
    print(f"    10 條邊各自整壞一端 (x += √3/1000): 兩層都即刻話唔係 1 ✓")

    print("== E. 毒藥測試 (檢查器必須大聲拒絕) ==")
    good_cvtx = cv
    good_edge = old_edge
    check_files(good_cvtx, good_edge, selftest=True, quiet=True)
    print("    (對照: 正常 .cvtx + .edge 通過, selftest 有牙)")
    lines = open(good_cvtx).read().splitlines()

    def poison(label, new_lines=None, edge_text=None):
        cp = os.path.join(tmpd, "poison.cvtx")
        ep = os.path.join(tmpd, "poison.edge")
        open(cp, "w").write("\n".join(new_lines if new_lines is not None else lines) + "\n")
        if edge_text is None:
            ep = good_edge
        else:
            open(ep, "w").write(edge_text)
        _expect_reject(label, lambda: check_files(cp, ep, quiet=True))

    toks = lines[1].split()
    poison("浮點係數 1.5", [lines[0]] + [" ".join([toks[0], "1.5"] + toks[2:])] + lines[2:])
    poison("科學記數 1e3", [lines[0]] + [" ".join([toks[0], "1e3"] + toks[2:])] + lines[2:])
    poison("分數字面值 1/2", [lines[0]] + [" ".join([toks[0], "1/2"] + toks[2:])] + lines[2:])
    poison("符號 t", [lines[0]] + [" ".join([toks[0], "t"] + toks[2:])] + lines[2:])
    poison("分母 0", [lines[0]] + [" ".join(["0"] + toks[1:])] + lines[2:])
    poison("分母負數", [lines[0]] + [" ".join(["-" + toks[0]] + toks[1:])] + lines[2:])
    poison("向量短咗一格", [lines[0]] + [" ".join(toks[:-1])] + lines[2:])
    poison("向量長咗一格", [lines[0]] + [" ".join(toks + ["0"])] + lines[2:])
    poison("header dim 造假", [lines[0].replace("dim=160", "dim=161")] + lines[1:])
    poison("header N 同 dim 唔夾 (N=84,dim=160)", [lines[0].replace("N=660", "N=84")] + lines[1:])
    poison("header n 造假", [lines[0].replace(f"n={n}", f"n={n + 1}")] + lines[1:])
    poison("少咗一個頂點", lines[:-1])
    poison("重合點 (頂點 2 抄頂點 1 嘅坐標)", [lines[0], lines[1], lines[1]] + lines[3:])
    poison("NBSP 做分隔符", [lines[0]] + [lines[1].replace(" ", " ", 1)] + lines[2:])
    poison("header N=999999 (DoS)", [lines[0].replace("N=660", "N=999999").replace("dim=160", "dim=1")] + lines[1:])
    poison("整數 61 位 (OverflowError 陷阱)", [lines[0]] + [" ".join([toks[0], "1" + "0" * 60] + toks[2:])] + lines[2:])
    poison("前導零 007", [lines[0]] + [" ".join([toks[0], "007"] + toks[2:])] + lines[2:])
    poison(".cvtx 空行", [lines[0], ""] + lines[1:])
    poison(".edge 注釋行 (nonce 空間)", None, f"p edge {n} 1\nc nonce 12345\ne 1 2\n")
    poison("空邊表", None, f"p edge {n} 0\n")
    poison("self-loop", None, f"p edge {n} 1\ne 1 1\n")
    poison("重複邊", None, f"p edge {n} 2\ne 1 2\ne 2 1\n")
    poison("索引超界", None, f"p edge {n} 1\ne 1 {n + 1}\n")
    poison("p 行邊數造假", None, f"p edge {n} 2\ne 1 2\n")
    nu = next(p for p in non if not new_is_unit(pts_new, *p))
    poison(f"非單位距離邊 ({nu[0]},{nu[1]})", None, f"p edge {n} 1\ne {nu[0]} {nu[1]}\n")
    poison("頂點數對唔上 (.cvtx 552 vs .edge 553)",
           [lines[0].replace(f"n={n}", f"n={n - 1}")] + lines[1:-1])
    # 近乎單位: |1 + ε ζ| 距離 0, ε = 10^-20 —— 浮點見到嘅係 1.0 (分唔開), 精確層必須話唔係 1
    eps_pt = F.one() + F.zeta(1) * Fraction(1, 10 ** 20)
    near = [lines[0].replace(f"n={n}", "n=2"),
            "1 " + " ".join(["0"] * F.dim),
            str(eps_pt.den) + " " + " ".join(map(str, eps_pt.num))]
    dist_float = abs(eps_pt.to_float())
    poison(f"近乎單位距離 (浮點 |z| = {dist_float!r})", near, "p edge 2 1\ne 1 2\n")
    # 完整性檢查 + 佢嘅毒藥 (攻擊者: 邊表得 10/11 條 spindle 邊都可以出 spindle-free 證書)
    # 自建 4×4 三角格仔 (N=12, 點 = i + j·ζ_6), 完整 UDG = 6 個格仔方向
    F12 = CycField(12)
    tri_pts, tri_idx = [], {}
    for i in range(4):
        for j in range(4):
            tri_idx[(i, j)] = len(tri_pts) + 1
            tri_pts.append(F12.rational(i) + F12.zeta(2) * j)
    tri_edges = []
    for (i, j), u in tri_idx.items():
        for di, dj in ((1, 0), (0, 1), (-1, 1)):
            v = tri_idx.get((i + di, j + dj))
            if v:
                tri_edges.append((u, v))
    tc = os.path.join(tmpd, "tri.cvtx"); te = os.path.join(tmpd, "tri.edge")
    write_cvtx(tc, F12, tri_pts)
    open(te, "w").write(f"p edge 16 {len(tri_edges)}\n" + "".join(f"e {u} {v}\n" for u, v in tri_edges))
    cnt, near = check_complete(tc, te, quiet=True)
    assert cnt == len(tri_edges) == 33
    print(f"    完整性: 4×4 三角格仔 (N=12) 邊表 == 完整單位距離圖 ✓ ({cnt} 條)")
    open(te, "w").write(f"p edge 16 {len(tri_edges) - 1}\n" + "".join(f"e {u} {v}\n" for u, v in tri_edges[1:]))
    _expect_reject("邊表少咗 1 條單位邊 (完整性)", lambda: check_complete(tc, te, quiet=True))
    try:
        cnt, near = check_complete(good_cvtx, good_edge, quiet=True)
        print(f"    (資訊) {os.path.basename(good_edge)} 邊表 == 佢點集嘅完整單位距離圖 ✓ ({cnt} 條, 近似陷阱 {len(near)})")
    except AssertionError as e:
        print(f"    (資訊) {os.path.basename(good_edge)} 唔係完整 UDG (CNP-SAT 圖可以係子圖, 唔算錯): {str(e)[:100]}")
    # python -O
    import subprocess
    r = subprocess.run([sys.executable, "-O", os.path.abspath(__file__), "check", good_cvtx, good_edge],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "唔准用 python -O" in (r.stdout + r.stderr), "python -O 竟然可以跑"
    print("    毒藥「python -O」被拒 ✓")
    print(f"== selftest 全部通過 ✓  (臨時檔喺 {tmpd}) ==")


# ============================================================
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("cvtx"); c.add_argument("edge"); c.add_argument("--selftest", action="store_true")
    c.add_argument("--complete", action="store_true", help="另外認證: 邊表 == 點集嘅完整單位距離圖")
    v = sub.add_parser("convert"); v.add_argument("vtx"); v.add_argument("cvtx"); v.add_argument("--N", type=int, default=660)
    s = sub.add_parser("selftest")
    s.add_argument("--old-vtx", default=os.path.expanduser("~/hadwiger/CNP-SAT/vtx/553.vtx"))
    s.add_argument("--old-edge", default=os.path.expanduser("~/hadwiger/CNP-SAT/edge/553.edge"))
    a = ap.parse_args()
    if a.cmd == "check":
        check_files(a.cvtx, a.edge, selftest=a.selftest)
        if a.complete:
            check_complete(a.cvtx, a.edge)
    elif a.cmd == "convert":
        t0 = time.time()
        F, pts = convert_vtx(a.vtx, a.cvtx, a.N)
        print(f"轉換 {len(pts)} 點 -> {a.cvtx} (N={F.N}, dim {F.dim}, {time.time() - t0:.1f}s)")
    elif a.cmd == "selftest":
        selftest(a.old_vtx, a.old_edge)

if __name__ == "__main__":
    main()
