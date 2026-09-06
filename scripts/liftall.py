#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liftall.py —— 將 cnc2 bundle 嘅每個 leaf 證明「提升」做 Phase 2 原版 CNF (variant a) 嘅證明, 並保留 (呢啲先係可以攞出街嘅 L1 證書):
  對每個 leaf cube c:
    cnf_b = L1_b + c 嘅 unit (同 cnc2 一樣, sha 要同 bundle 記錄一致)
    cnf_a = L1_a + c 嘅 unit                 (L1_a = Phase 2 G1-4-sameAB.cnf, byte 級一致)
    kissat cnf_b → DRAT (ASCII) ;  lifted = AMO RAT 引理 (pivot 避開正 unit: 釘色 + cube 正 literal) + DRAT
    drat-trim cnf_a lifted → 必須 's VERIFIED'  ;  保留 lifted (D: 碟), 記 sha256 / 行數 / bytes
  cover 證書 (純 tautology, 只涉及 cube) 直接沿用 bundle 嘅 cover_pure.{cnf,drat}, 重驗一次.
  (1) 每個 (L1_a ∧ c_i) UNSAT + (2) ⋀¬c_i tautology ⇒ L1_a UNSAT, 全部由 drat-trim 檢查, 冇紙上引理.
用法: python3 liftall.py --bundle cnc_b/bundle.json --cnf-a enc/L1_a.cnf --cnf-b enc/L1_b.cnf --edge G1.edge --cvtx G1.cvtx --out DIR --keep-dir /mnt/d/.../lifted [--workers 14] [--sample N]
"""
import sys, os, time, json, argparse, subprocess, hashlib, threading, random
from concurrent.futures import ThreadPoolExecutor, as_completed

if not __debug__:
    sys.exit("!! 唔准用 python -O")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.expanduser("~/hadwiger/phase2"))
import certify4
from l1enc import amo_lemmas, K, var
from exactfield import load_edges

KISSAT = "/home/user/hadwiger/kissat/build/kissat"
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"

def sha_lines(path):
    h = hashlib.sha256(); n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk); n += chunk.count(b"\n")
    return h.hexdigest(), n

def read_cnf(path):
    nvars = None; cl = []
    for line in open(path):
        t = line.split()
        if not t or t[0] == "c":
            continue
        if t[0] == "p":
            nvars = int(t[2]); continue
        cl.append([int(x) for x in t[:-1]])
    return nvars, cl

def write_cnf(path, nvars, nbase, base_text, cube):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("p cnf %d %d\n" % (nvars, nbase + len(cube)))
        f.write(base_text)
        for l in cube:
            f.write("%d 0\n" % l)
    os.replace(tmp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True); ap.add_argument("--cnf-a", required=True); ap.add_argument("--cnf-b", required=True)
    ap.add_argument("--edge", required=True); ap.add_argument("--cvtx", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--keep-dir", required=True); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260905); ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    out = os.path.abspath(a.out); os.makedirs(os.path.join(out, "tmp"), exist_ok=True); os.makedirs(a.keep_dir, exist_ok=True)
    b = json.load(open(a.bundle))
    sha_b = sha_lines(a.cnf_b)[0]; sha_a = sha_lines(a.cnf_a)[0]
    assert sha_b == b["base_sha"], "bundle 嘅 base sha 唔係 --cnf-b"
    n, edges = load_edges(a.edge); A, B = certify4.locate_AB(a.cvtx)
    nv_a, cl_a = read_cnf(a.cnf_a); nv_b, cl_b = read_cnf(a.cnf_b)
    assert nv_a == nv_b == n * K
    # 核對: cl_b = cl_a + AMO(除 A,B) (作為子句集合)
    set_a = {tuple(c) for c in cl_a}; set_b = {tuple(c) for c in cl_b}
    extra = set_b - set_a
    assert set_a <= set_b and all(len(c) == 2 and c[0] < 0 and c[1] < 0 and (abs(c[0]) - 1) // K == (abs(c[1]) - 1) // K for c in extra), "cnf_b 唔係 cnf_a + AMO"
    assert not any((abs(c[0]) - 1) // K + 1 in (A, B) for c in extra), "cnf_b 嘅 AMO 包含 A/B"
    pins = {c[0] for c in cl_a if len(c) == 1 and c[0] > 0}
    text_a = "".join(" ".join(map(str, c)) + " 0\n" for c in cl_a); text_b = "".join(" ".join(map(str, c)) + " 0\n" for c in cl_b)
    leaves = b["leaf_list"]
    if a.sample:
        leaves = random.Random(a.seed).sample(leaves, min(a.sample, len(leaves)))
    print("[liftall] %d 個 leaf (bundle 共 %d); L1_a sha %s…, L1_b sha %s… (= a + %d 條 AMO, A=%d B=%d 除外); 釘色 unit %s" % (
        len(leaves), len(b["leaf_list"]), sha_a[:12], sha_b[:12], len(extra), A, B, sorted(pins)), flush=True)
    results_p = os.path.join(out, "lifted.jsonl"); done = {}
    if os.path.exists(results_p):
        for line in open(results_p):
            r = json.loads(line); done[r["id"]] = r
    lock = threading.Lock()
    def one(leaf):
        cid, cube = leaf["id"], leaf["cube"]
        if cid in done and done[cid].get("verified"):
            return done[cid]
        pb = os.path.join(out, "tmp", "b_%s.cnf" % cid); pa = os.path.join(out, "tmp", "a_%s.cnf" % cid)
        drat = os.path.join(out, "tmp", "b_%s.drat" % cid); lifted = os.path.join(a.keep_dir, "L1a_cube_%s.drat" % cid)
        rec = {"id": cid, "cube": cube}
        try:
            write_cnf(pb, nv_b, len(cl_b), text_b, cube); write_cnf(pa, nv_a, len(cl_a), text_a, cube)
            rec["cnf_b_sha"] = sha_lines(pb)[0]; rec["cnf_a_sha"] = sha_lines(pa)[0]
            rec["cnf_b_sha_matches_bundle"] = (rec["cnf_b_sha"] == leaf["cnf_sha"])
            t0 = time.time()
            r = subprocess.run([KISSAT, "-q", "--no-binary", "--time=%d" % int(a.timeout), pb, drat], capture_output=True, text=True, timeout=a.timeout + 300)
            rec["solve_rc"] = r.returncode; rec["solve_s"] = round(time.time() - t0, 1)
            if r.returncode != 20:
                rec["verified"] = False; rec["why"] = "solver rc=%d" % r.returncode; return rec
            units = pins | {l for l in cube if l > 0}
            lem = amo_lemmas(n, A, B, units)
            with open(lifted, "w") as f:
                for c in lem:
                    f.write(" ".join(map(str, c)) + " 0\n")
                with open(drat) as g:
                    for line in g:
                        f.write(line)
            t1 = time.time()
            dr = subprocess.run([DRATTRIM, pa, lifted], capture_output=True, text=True, timeout=6 * 3600)
            rec["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); rec["verify_s"] = round(time.time() - t1, 1)
            rec["lifted_sha"], rec["lifted_lines"] = sha_lines(lifted); rec["lifted_bytes"] = os.path.getsize(lifted); rec["lifted_path"] = lifted
            rec["amo_lemmas"] = len(lem)
            if not rec["verified"]:
                rec["tail"] = dr.stdout[-300:]
        except Exception as e:
            rec["verified"] = False; rec["why"] = repr(e)[-300:]
        finally:
            for p in (pb, pa, drat):
                if os.path.exists(p):
                    os.remove(p)
        with lock:
            with open(results_p, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec
    t0 = time.time(); okc = 0; bad = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, lf) for lf in leaves]
        for i, fu in enumerate(as_completed(futs), 1):
            rec = fu.result()
            if rec.get("verified"):
                okc += 1
            else:
                bad.append(rec["id"])
            if i % 500 == 0 or i == len(leaves):
                print("  [%d/%d] verified %d, 唔 ok %d, %.0fs" % (i, len(leaves), okc, len(bad), time.time() - t0), flush=True)
    # cover 重驗
    cov = b["cover"][b["cover_mode"]]
    t1 = time.time()
    dr = subprocess.run([DRATTRIM, cov["cnf"], cov["proof_kept"]], capture_output=True, text=True, timeout=3600)
    cov_ok = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
    summ = {"bundle": a.bundle, "cnf_a": a.cnf_a, "cnf_a_sha": sha_a, "cnf_b_sha": sha_b, "A": A, "B": B, "pins": sorted(pins), "n_leaves": len(leaves),
            "n_verified": okc, "not_ok": bad, "cover_mode": b["cover_mode"], "cover_reverified": cov_ok, "cover_cnf_sha": sha_lines(cov["cnf"])[0],
            "cover_drat_sha": sha_lines(cov["proof_kept"])[0], "keep_dir": a.keep_dir, "wall_s": round(time.time() - t0, 1), "all_ok": okc == len(leaves) and cov_ok and not bad}
    json.dump(summ, open(os.path.join(out, "liftall.json"), "w"), indent=1)
    print("[liftall] %d/%d leaf 提升證明對 L1_a+cube drat-trim VERIFIED; cover (%s) 重驗 %s; 全部 ok: %s; %.0fs → %s/liftall.json" % (
        okc, len(leaves), b["cover_mode"], "VERIFIED" if cov_ok else "!! NOT VERIFIED", summ["all_ok"], summ["wall_s"], out), flush=True)
    sys.exit(0 if summ["all_ok"] else 1)

if __name__ == "__main__":
    main()
