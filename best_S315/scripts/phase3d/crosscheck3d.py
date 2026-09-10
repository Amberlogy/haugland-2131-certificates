#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crosscheck3d.py —— Phase 3d: 用形式化驗證過嘅 cake_lpr 交叉覆核抽樣 leaf 證明 (方法同 phase2b/crosscheck_cakelpr.py 一模一樣, 只係改成讀 cnc2k 嘅 keep 目錄佈局)
  每個抽中嘅 leaf: 由 base.cnf + cube 重建 cube CNF (sha 要同 state.json 一致) → 讀 keep 目錄嘅 binary DRAT (sha 要一致)
    → drat-trim cnf proof -L lrat   (drat-trim 自己都要 "s VERIFIED")
    → cake_lpr cnf lrat             (要 "s VERIFIED UNSAT"; cake_lpr 係 CakeML 形式化驗證過嘅檢查器, 失敗都會 rc=0, 只認字串)
    → lrat-check cnf lrat           (要 "c VERIFIED"; 第三個獨立檢查器)
  三個檢查器全部要過先算 ok. LRAT 寫喺 --tmp (預設 /dev/shm), 檢查完即刪.
用法: python3 crosscheck3d.py --attempt-dir DIR --tag TAG --keep-dir DIR --out DIR [--frac 0.05] [--workers 14] [--seed 20260908] [--tmp /dev/shm/xc3d]
輸出: <out>/crosscheck.json (逐個 leaf 嘅結果 + 摘要); rc 0 = 全部過, 4 = 有唔過
"""
import sys, os, json, time, argparse, subprocess, hashlib, random, statistics
from concurrent.futures import ThreadPoolExecutor
if not __debug__:
    sys.exit("!! 唔准用 python -O")
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"
CAKELPR = "/home/user/hadwiger/tools/cake_lpr/cake_lpr"
LRATCHECK = "/home/user/hadwiger/drat-trim/lrat-check"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def free_gb(p):
    try:
        st = os.statvfs(p); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

def wait_space(tmp, min_gb, timeout_s=1800):
    """審查: LRAT 寫落 /dev/shm (16 GB, 同戰役共用) —— 開工前等到有位先做, 免得塞爆 tmpfs 連累其他嘢."""
    t0 = time.time()
    while True:
        f = free_gb(tmp)
        if f is None or f >= min_gb:
            return True
        if time.time() - t0 > timeout_s:
            return False
        time.sleep(10)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt-dir", required=True); ap.add_argument("--tag", required=True); ap.add_argument("--keep-dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--frac", type=float, default=0.05); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument("--tmp", default=None); ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--min-free-gb", type=float, default=4.0); ap.add_argument("--max-workers", type=int, default=8)
    a = ap.parse_args()
    a.workers = max(1, min(a.workers, a.max_workers))          # 審查: LRAT 可以好大, 唔好 14 條線一齊寫 tmpfs
    d = os.path.abspath(os.path.expanduser(a.attempt_dir)); tag = a.tag; keep = os.path.abspath(os.path.expanduser(a.keep_dir))
    out = os.path.abspath(os.path.expanduser(a.out)); os.makedirs(out, exist_ok=True)
    tmp = os.path.abspath(os.path.expanduser(a.tmp or os.path.join("/dev/shm", "xc3d_" + tag))); os.makedirs(tmp, exist_ok=True)
    cdir = os.path.join(d, "cnc_" + tag)
    st = json.load(open(os.path.join(cdir, "state.json"))); cb = json.load(open(os.path.join(cdir, "bundle.json")))
    base_p = os.path.join(cdir, "base.cnf")
    lines = [l for l in open(base_p) if not l.startswith(("p", "c"))]
    nvars = int(open(base_p).readline().split()[2]); base_text = "".join(lines); nbase = len(lines)
    done = st["done"]; ids = sorted(done)
    k = max(1, int(round(a.frac * len(ids))))
    pick = sorted(random.Random(a.seed).sample(ids, min(k, len(ids))))
    T0 = time.time()
    log("crosscheck (cake_lpr): 抽 %d/%d 個 leaf (frac %.3f, seed %d); base.cnf sha %s; keep %s" % (len(pick), len(ids), a.frac, a.seed, sha(base_p)[:16], keep))
    def one(cid):
        dd = done[cid]; r = {"id": cid}
        cnf = os.path.join(tmp, "cube_%s.cnf" % cid); lrat = os.path.join(tmp, "cube_%s.lrat" % cid)
        try:
            with open(cnf, "w") as f:
                f.write("p cnf %d %d\n" % (nvars, nbase + len(dd["cube"]))); f.write(base_text)
                for l in dd["cube"]:
                    f.write("%d 0\n" % l)
            r["cnf_sha_match"] = (sha(cnf) == dd["cnf_sha"])
            proof = dd.get("kept") or os.path.join(keep, "cnc_%s_%s.drat" % (tag, cid))
            if not os.path.exists(proof):
                p2 = os.path.join(keep, os.path.basename(proof))
                proof = p2 if os.path.exists(p2) else proof
            r["proof"] = proof; r["proof_exists"] = os.path.exists(proof)
            if not r["proof_exists"]:
                r["ok"] = False; return r
            r["proof_sha_match"] = (sha(proof) == (dd.get("repaired_proof_sha") or dd["proof_sha"]))
            if not wait_space(tmp, a.min_free_gb):
                r["ok"] = False; r["error"] = "tmp %s 空間唔夠 (%.1f GB < %.1f GB) 等咗 30 分鐘" % (tmp, free_gb(tmp) or -1, a.min_free_gb); return r
            t0 = time.time()
            dr = subprocess.run([DRATTRIM, cnf, proof, "-L", lrat], capture_output=True, text=True, timeout=a.timeout)
            r["drattrim_verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines()); r["drattrim_s"] = round(time.time() - t0, 1)
            r["lrat_bytes"] = os.path.getsize(lrat) if os.path.exists(lrat) else 0
            if r["lrat_bytes"]:
                t1 = time.time()
                c = subprocess.run([CAKELPR, cnf, lrat], capture_output=True, text=True, timeout=a.timeout)
                r["cake_lpr_verified"] = any(l.strip() == "s VERIFIED UNSAT" for l in c.stdout.splitlines()); r["cake_lpr_s"] = round(time.time() - t1, 1)
                if not r["cake_lpr_verified"]:
                    r["cake_tail"] = (c.stdout + c.stderr)[-300:]
                t2 = time.time()
                kk = subprocess.run([LRATCHECK, cnf, lrat], capture_output=True, text=True, timeout=a.timeout)
                r["lrat_check_verified"] = any(l.strip() == "c VERIFIED" for l in kk.stdout.splitlines()); r["lrat_check_s"] = round(time.time() - t2, 1)
                if not r["lrat_check_verified"]:
                    r["lrat_tail"] = (kk.stdout + kk.stderr)[-300:]
            r["ok"] = bool(r.get("cnf_sha_match") and r.get("proof_sha_match") and r.get("drattrim_verified") and r.get("cake_lpr_verified") and r.get("lrat_check_verified"))
        except Exception as e:
            r["ok"] = False; r["error"] = repr(e)[-300:]
        finally:
            for p in (cnf, lrat):
                if os.path.exists(p):
                    os.remove(p)
        return r
    recs = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(one, pick), 1):
            recs.append(r)
            if i % 100 == 0 or i == len(pick):
                log("  %d/%d, ok %d, %.0f s" % (i, len(pick), sum(1 for x in recs if x["ok"]), time.time() - T0))
    bad = [r for r in recs if not r["ok"]]
    summ = {"attempt_dir": d, "tag": tag, "keep_dir": keep, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "frac": a.frac, "seed": a.seed,
            "n_leaves": len(ids), "n_sampled": len(pick), "ok": len(recs) - len(bad), "n_bad": len(bad), "bad": bad[:30],
            "sampled_ids": pick, "base_sha256": sha(base_p), "bundle_base_sha": cb["base_sha"],
            "lrat_total_gb": round(sum(r.get("lrat_bytes") or 0 for r in recs) / 1e9, 3),
            "mean_drattrim_s": round(statistics.mean([r.get("drattrim_s") or 0 for r in recs]), 2) if recs else None,
            "mean_cake_lpr_s": round(statistics.mean([r.get("cake_lpr_s") or 0 for r in recs]), 2) if recs else None,
            "checkers": {"drat-trim": DRATTRIM, "cake_lpr": CAKELPR, "lrat-check": LRATCHECK,
                         "sha256": {n: sha(p) for n, p in (("drat-trim", DRATTRIM), ("cake_lpr", CAKELPR), ("lrat-check", LRATCHECK)) if os.path.exists(p)}},
            "wall_s": round(time.time() - T0, 1), "all_ok": not bad, "records": recs}
    tmpf = os.path.join(out, "crosscheck.json") + ".tmp"
    json.dump(summ, open(tmpf, "w"), indent=1, ensure_ascii=False); os.replace(tmpf, os.path.join(out, "crosscheck.json"))
    log("crosscheck: %d/%d 個 leaf 三個檢查器 (drat-trim VERIFIED + cake_lpr 's VERIFIED UNSAT' + lrat-check 'c VERIFIED') 全過%s; LRAT 共 %.1f GB; %.0f s → %s" % (
        summ["ok"], len(pick), "" if not bad else " !! 唔過: %s" % [b["id"] for b in bad[:10]], summ["lrat_total_gb"], summ["wall_s"], os.path.join(out, "crosscheck.json")))
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    sys.exit(0 if not bad else 4)

if __name__ == "__main__":
    main()
