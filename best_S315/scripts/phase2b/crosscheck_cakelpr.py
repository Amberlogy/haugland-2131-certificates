#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crosscheck_cakelpr.py —— 用形式化驗證過嘅 cake_lpr 交叉覆核 lifted 證明 (抽樣): drat-trim -L 出 LRAT, 再 cake_lpr 檢查 → 's VERIFIED UNSAT'
  (drat-trim 出嘅 LRAT 由 cake_lpr 獨立檢查; 兩個檢查器都要過先算)
用法: python3 crosscheck_cakelpr.py --lift lift --cnf-a enc/L1_a.cnf --out crosscheck --sample 739 [--workers 14] [--all]
"""
import sys, os, json, argparse, subprocess, hashlib, random, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

if not __debug__:
    sys.exit("!! 唔准用 python -O")
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"; CAKELPR = "/home/user/hadwiger/tools/cake_lpr/cake_lpr"; LRATCHECK = "/home/user/hadwiger/drat-trim/lrat-check"

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lift", required=True); ap.add_argument("--cnf-a", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=739); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=20260905)
    a = ap.parse_args()
    out = os.path.abspath(a.out); os.makedirs(os.path.join(out, "tmp"), exist_ok=True)
    recs = [json.loads(l) for l in open(os.path.join(a.lift, "lifted.jsonl"))]
    recs = {r["id"]: r for r in recs if r.get("verified")}
    ids = sorted(recs)
    pick = ids if a.all else random.Random(a.seed).sample(ids, min(a.sample, len(ids)))
    nv, cl = None, []
    for line in open(a.cnf_a):
        t = line.split()
        if t[0] == "p":
            nv = int(t[2]); continue
        cl.append(line)
    text = "".join(cl)
    lock = threading.Lock(); res_p = os.path.join(out, "results.jsonl")
    print("[crosscheck] %d/%d 個 leaf: 重建 L1_a+cube CNF (sha 對 lifted.jsonl) → drat-trim -L LRAT → lrat-check + cake_lpr" % (len(pick), len(ids)), flush=True)
    def one(cid):
        r = recs[cid]; cube = r["cube"]
        cnf = os.path.join(out, "tmp", "a_%s.cnf" % cid); lrat = os.path.join(out, "tmp", "a_%s.lrat" % cid)
        rec = {"id": cid}
        try:
            with open(cnf, "w") as f:
                f.write("p cnf %d %d\n" % (nv, len(cl) + len(cube))); f.write(text)
                for l in cube:
                    f.write("%d 0\n" % l)
            rec["cnf_sha_match"] = sha(cnf) == r["cnf_a_sha"]
            rec["lifted_sha_match"] = sha(r["lifted_path"]) == r["lifted_sha"]
            t0 = time.time()
            d = subprocess.run([DRATTRIM, cnf, r["lifted_path"], "-L", lrat], capture_output=True, text=True, timeout=3600)
            rec["drattrim_verified"] = any(l.strip() == "s VERIFIED" for l in d.stdout.splitlines()); rec["drattrim_s"] = round(time.time() - t0, 1)
            t1 = time.time()
            c = subprocess.run([CAKELPR, cnf, lrat], capture_output=True, text=True, timeout=3600)
            rec["cake_lpr_verified"] = any(l.strip() == "s VERIFIED UNSAT" for l in c.stdout.splitlines()); rec["cake_lpr_s"] = round(time.time() - t1, 1)
            k = subprocess.run([LRATCHECK, cnf, lrat], capture_output=True, text=True, timeout=3600)
            rec["lrat_check_verified"] = any(l.strip() == "c VERIFIED" for l in k.stdout.splitlines())
            rec["lrat_bytes"] = os.path.getsize(lrat) if os.path.exists(lrat) else 0
            rec["ok"] = all(rec.get(x) for x in ("cnf_sha_match", "lifted_sha_match", "drattrim_verified", "cake_lpr_verified", "lrat_check_verified"))
            if not rec["ok"]:
                rec["tail"] = (d.stdout[-200:] + " | " + (c.stdout + c.stderr)[-200:])
        except Exception as e:
            rec["ok"] = False; rec["tail"] = repr(e)[-300:]
        finally:
            for p in (cnf, lrat):
                if os.path.exists(p):
                    os.remove(p)
        with lock:
            with open(res_p, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec
    t0 = time.time(); okc = 0; bad = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rec in (fu.result() for fu in as_completed([ex.submit(one, i) for i in pick])):
            okc += rec["ok"]
            if not rec["ok"]:
                bad.append(rec["id"])
    summ = {"n": len(pick), "ok": okc, "bad": bad, "wall_s": round(time.time() - t0, 1), "all_ok": okc == len(pick)}
    json.dump(summ, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print("[crosscheck] %d/%d 個 leaf: drat-trim VERIFIED + LRAT 經 cake_lpr 's VERIFIED UNSAT' + lrat-check 'c VERIFIED' 全過; 失敗 %s; %.0fs" % (okc, len(pick), bad[:5], summ["wall_s"]), flush=True)
    sys.exit(0 if summ["all_ok"] else 1)

if __name__ == "__main__":
    main()
