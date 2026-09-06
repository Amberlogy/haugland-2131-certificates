#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_bundle.py —— 一鍵重驗 Haugland 定理 (G₃ 係 5-chromatic) 嘅完整機器證明鏈 L1 + L2 + L3 (bundle/ 入面自給自足)
  0. SHA256SUMS 全部對數
  1. 精確坐標 + 完整性: exactfield.py check --complete (G1, G3)
  2. L1_a.cnf 由 G1.edge + G1.cvtx 重建 (l1enc build a) sha 必須一致 (= Phase 2 G1-4-sameAB.cnf)
  3. L1: (a) cover: drat-trim cover_pure.cnf cover_pure.drat → s VERIFIED (¬cube 合取係 tautology)
         (b) 每個 leaf: 重建 L1_a + cube CNF (sha 對 lifted.jsonl), drat-trim 對 lifted DRAT → s VERIFIED   [--sample N 抽 N 個; 預設全部]
         (c) leaf 集合 = cubes.icnf 嘅 cube 集合 (split 過嘅以仔 cube 代父; 由 bundle.json 讀) —— 呢步只係對數, 證明力來自 (a)+(b)
  4. L2: chain.py 嘅精確映射核對重跑 (φ_k(V(G1)) ⊂ V(G3), E(G1) ↦ E(G3)) — 由 chain.py --skip-l3 重做
  5. L3: drat-trim L3.cnf L3.drat → s VERIFIED; 而且 L3.cnf 嘅 16 條引理子句同 pairs.json 對數
用法: python3 verify_bundle.py --bundle DIR [--sample N] [--workers 14]
"""
import sys, os, json, argparse, subprocess, hashlib, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed

if not __debug__:
    sys.exit("!! 唔准用 python -O")

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def run(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True, **kw)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True); ap.add_argument("--sample", type=int, default=0); ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    Bd = os.path.abspath(a.bundle); m = json.load(open(os.path.join(Bd, "manifest.json")))
    tools = m["tools"]; DRATTRIM = tools["drat-trim"]["path"]; PY = a.python
    sc = os.path.join(Bd, "scripts")
    ok_all = True; T0 = time.time()
    def report(step, ok, msg):
        nonlocal ok_all
        ok_all &= ok
        print("[%s] %s %s" % (step, "✓" if ok else "!! FAIL", msg), flush=True)
    # 0
    bad = []
    for line in open(os.path.join(Bd, "SHA256SUMS")):
        h, _, rel = line.strip().partition("  ")
        p = os.path.join(Bd, rel)
        if not os.path.exists(p) or sha(p) != h:
            bad.append(rel)
    report("0 SHA256SUMS", not bad, "%d 個檔案對數%s" % (sum(1 for _ in open(os.path.join(Bd, "SHA256SUMS"))), "" if not bad else ", 錯: %s" % bad[:5]))
    # 1
    for g in ("G1", "G3"):
        r = run([PY, os.path.join(sc, "exactfield.py"), "check", os.path.join(Bd, "inputs", g + ".cvtx"), os.path.join(Bd, "inputs", g + ".edge"), "--complete"], timeout=3600)
        ok = r.returncode == 0 and ("完整" in r.stdout or "complete" in r.stdout.lower() or "PASS" in r.stdout or "全部" in r.stdout)
        report("1 exact " + g, r.returncode == 0, r.stdout.strip().split("\n")[-1][:160])
    # 2
    tmp = os.path.join(Bd, "tmp_verify"); os.makedirs(tmp, exist_ok=True)
    r = run([PY, os.path.join(sc, "l1enc.py"), "build", "--edge", os.path.join(Bd, "inputs", "G1.edge"), "--cvtx", os.path.join(Bd, "inputs", "G1.cvtx"),
             "--variant", "a", "--out", tmp, "--tag", "rebuild_a"], timeout=600)
    ok = r.returncode == 0 and sha(os.path.join(tmp, "rebuild_a.cnf")) == m["L1"]["cnf_a_sha"]
    report("2 L1_a 重建", ok, "sha %s… == manifest %s" % (sha(os.path.join(tmp, "rebuild_a.cnf"))[:16] if r.returncode == 0 else "?", ok))
    # 3a cover
    cov_cnf = os.path.join(Bd, "L1", "cover_pure.cnf"); cov_drat = os.path.join(Bd, "L1", "cover_pure.drat")
    r = run([DRATTRIM, cov_cnf, cov_drat], timeout=3600)
    ok = any(l.strip() == "s VERIFIED" for l in r.stdout.splitlines())
    report("3a cover", ok, "drat-trim cover_pure: %s (%d 條 ¬cube 子句)" % ("s VERIFIED" if ok else "NOT VERIFIED", m["L1"]["n_leaves"]))
    # 3c leaf set vs cubes.icnf
    leaves = [json.loads(l) for l in open(os.path.join(Bd, "L1", "lifted.jsonl"))]
    leaf_cubes = {tuple(sorted(r["cube"])) for r in leaves}
    cov_neg = set()
    for line in open(cov_cnf):
        t = line.split()
        if t and t[0] not in ("p", "c"):
            cov_neg.add(tuple(sorted(-int(x) for x in t[:-1])))
    report("3c leaf 集合", leaf_cubes == cov_neg and len(leaves) == m["L1"]["n_leaves"], "lifted.jsonl %d 個 leaf == cover 子句集 %d 個: %s" % (len(leaf_cubes), len(cov_neg), leaf_cubes == cov_neg))
    # 3b leaves
    nv, cl_a = None, []
    for line in open(os.path.join(Bd, "L1", "L1_a.cnf")):
        t = line.split()
        if t[0] == "p":
            nv = int(t[2]); continue
        cl_a.append(line)
    text_a = "".join(cl_a)
    pick = leaves if not a.sample else random.Random(20260905).sample(leaves, min(a.sample, len(leaves)))
    lifted_dir = m["L1"]["lifted_dir"]
    def one(rec):
        cid = rec["id"]; cube = rec["cube"]
        cnf = os.path.join(tmp, "a_%s.cnf" % cid)
        with open(cnf, "w") as f:
            f.write("p cnf %d %d\n" % (nv, len(cl_a) + len(cube))); f.write(text_a)
            for l in cube:
                f.write("%d 0\n" % l)
        okc = sha(cnf) == rec["cnf_a_sha"]
        lp = os.path.join(lifted_dir, os.path.basename(rec["lifted_path"]))
        okp = os.path.exists(lp) and sha(lp) == rec["lifted_sha"]
        r = run([DRATTRIM, cnf, lp], timeout=6 * 3600) if okp else None
        okv = r is not None and any(l.strip() == "s VERIFIED" for l in r.stdout.splitlines())
        os.remove(cnf)
        return cid, okc, okp, okv
    n_ok = 0; fails = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for cid, okc, okp, okv in (fu.result() for fu in as_completed([ex.submit(one, rec) for rec in pick])):
            if okc and okp and okv:
                n_ok += 1
            else:
                fails.append((cid, okc, okp, okv))
    report("3b leaves", not fails, "%d/%d 個 leaf: 重建 CNF sha ✓, lifted DRAT sha ✓, drat-trim s VERIFIED ✓%s" % (n_ok, len(pick), "" if not fails else "; 失敗 %s" % fails[:5]))
    # 4 L2
    # chain.py 重做 L2 (精確映射) + L3 (kissat + drat-trim, 0.1s) 落 tmp; 對 pairs.json
    r = run([PY, os.path.join(sc, "chain.py"), "--haugland", os.path.join(Bd, "inputs"), "--out", tmp], timeout=3600)
    l2lines = [l for l in r.stdout.splitlines() if l.startswith("[L2]")]
    report("4 L2 映射 (chain.py 重跑)", r.returncode == 0 and len(l2lines) >= 5, (l2lines[-1][:200] if l2lines else "") if r.returncode == 0 else (r.stdout[-300:] + r.stderr[-300:]))
    if r.returncode == 0:
        p_new = json.load(open(os.path.join(tmp, "pairs.json")))["pairs"]; p_old = json.load(open(os.path.join(Bd, "L2", "pairs.json")))["pairs"]
        report("4 L2 pairs", p_new == p_old, "A_k/B_k 索引同 bundle 一致: %s" % (p_new == p_old))
        l3 = [l for l in r.stdout.splitlines() if l.startswith("[L3]")]
        report("4 L3 重做", any("VERIFIED ✓" in l for l in l3), (l3[-1][:160] if l3 else ""))
    # 5 L3
    r = run([DRATTRIM, os.path.join(Bd, "L3", "L3.cnf"), os.path.join(Bd, "L3", "L3.drat")], timeout=3600)
    ok = any(l.strip() == "s VERIFIED" for l in r.stdout.splitlines())
    pairs = json.load(open(os.path.join(Bd, "L2", "pairs.json")))["pairs"]
    lem = {tuple(sorted((-((pairs[k]["A"] - 1) * 4 + c), -((pairs[k]["B"] - 1) * 4 + c)))) for k in pairs for c in range(1, 5)}
    have = set()
    for line in open(os.path.join(Bd, "L3", "L3.cnf")):
        t = line.split()
        if t and t[0] != "p" and len(t) == 3:
            have.add(tuple(sorted((int(t[0]), int(t[1])))))
    report("5 L3", ok and lem <= have, "drat-trim L3: %s; 16 條引理子句喺 L3.cnf: %s" % ("s VERIFIED" if ok else "NOT VERIFIED", lem <= have))
    print("\n[verify_bundle] %s (%.0fs)" % ("全部通過 —— G₃ 5-chromatic 嘅機器證明鏈 L1+L2+L3 重驗成功" if ok_all else "!! 有步驟失敗", time.time() - T0), flush=True)
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    main()
