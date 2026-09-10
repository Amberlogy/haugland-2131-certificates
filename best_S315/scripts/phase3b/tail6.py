#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tail6.py —— Phase 3b 第 6 步 (可選, 過夜 ≤ 8 h, run ID 獨一): G₃ 直接 4 色 CnC 嘅硬尾巴換招
  對 Part 3 嘅 13 個 root cube (tail_stats.md), 每個當獨立實例:
    base_root.cnf = G₃ 4 色 CNF (part3 base.cnf, sha ca34880f…) + root cube 嘅單位子句
    → march_cu 由零重新拆件 (-d D, 預設 12; 唔用 cnc2 嘅靜態 max-split 再拆: --max-split 0, timeout 2 次即記 stuck)
    → 每個葉 kissat T=900 s → drat-trim (cnc2 引擎, 14 workers, ext4 binary DRAT 驗完即刪, 全部完成即出 cover + 5% 審計)
  每個 root 記: 仔 cube 數、完成、timeout/stuck、solve 分佈、wall; 完成晒嘅 root 記低 cover.
  全部 13 個 root 清晒 → 組裝直接證書清單 (原始 32768 cube 嘅 cover [重新計 + drat-trim] + 32755 個 depth-0 leaf (part3 state.json) + 13 個 root 各自 cover + 全部 leaf) → direct_certificate.json
  唔清晒 → 報告邊幾個 root 死硬. 8 h 硬上限, 唔准延長.
用法: python3 tail6.py --run-id p3bt6_tail --out DIR [--depth 12] [--timeout 900] [--workers 14] [--total-cap 28800] [--roots 29938,14578,...] [--proof-dir DIR]
"""
import sys, os, json, time, argparse, subprocess, signal, statistics, re, csv, hashlib
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2B = os.path.expanduser("~/hadwiger/phase2b"); PH3B = os.path.expanduser("~/hadwiger/phase3b")
PART3 = os.path.expanduser("~/hadwiger/phase3/part3/cnc")
MARCH = "/home/user/hadwiger/tools/CnC/march_cu/march_cu"
KISSAT = "/home/user/hadwiger/kissat/build/kissat"; DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"
PY = sys.executable
BASE_SHA = "ca34880f112ea898e6ccbec580068d36e96123d7efeb7134ceb03715f348961e"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def read_cnf_text(p):
    nvars = None; lines = []
    for line in open(p):
        t = line.split()
        if not t or t[0] == "c":
            continue
        if t[0] == "p":
            nvars = int(t[2]); continue
        lines.append(line if line.endswith("\n") else line + "\n")
    return nvars, lines

def read_icnf(p):
    return [[int(x) for x in line.split()[1:-1]] for line in open(p) if line.startswith("a ")]

def hard_roots(st, ledger):
    roots = set()
    for p in st["pending"] + st.get("running_at_save", []):
        roots.add(p["id"].split(".")[0])
    for r in csv.DictReader(open(ledger)):
        if r["status"] == "timeout" or "." in r["id"]:
            roots.add(r["id"].split(".")[0])
    return sorted(roots, key=int)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--out", required=True); ap.add_argument("--depth", type=int, default=12); ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--total-cap", type=float, default=8 * 3600); ap.add_argument("--roots", default=None); ap.add_argument("--proof-dir", default=None)
    ap.add_argument("--root-cap", type=float, default=None, help="每個 root 嘅時間上限 (預設 = 剩餘總時間)")
    a = ap.parse_args()
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True); T0 = time.time()
    pd = os.path.abspath(a.proof_dir or os.path.join(PH2B, "proofs_ext4", a.run_id)); os.makedirs(pd, exist_ok=True)
    st3 = json.load(open(os.path.join(PART3, "state.json"))); base = os.path.join(PART3, "base.cnf"); icnf0 = os.path.join(PART3, "cubes.icnf")
    assert sha(base) == BASE_SHA == st3["base_sha"], "part3 base.cnf sha 對唔上"
    cubes0 = read_icnf(icnf0); assert len(cubes0) == st3["n_cubes0"] == 32768
    roots = [x for x in a.roots.split(",") if x] if a.roots else hard_roots(st3, os.path.join(PART3, "ledger.csv"))
    nvars, base_lines = read_cnf_text(base)
    done0 = {k for k in st3["done"] if "." not in k}
    res = {"run_id": a.run_id, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "base_sha": BASE_SHA, "icnf0_sha": sha(icnf0), "n_cubes0": len(cubes0), "depth0_leaves_done_part3": len(done0),
           "roots": roots, "depth": a.depth, "timeout": a.timeout, "workers": a.workers, "total_cap_s": a.total_cap, "per_root": {}, "status": "running"}
    def save():
        res["elapsed_s"] = round(time.time() - T0, 1); res["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(res, open(os.path.join(out, "tail6.json.tmp"), "w"), indent=1, ensure_ascii=False); os.replace(os.path.join(out, "tail6.json.tmp"), os.path.join(out, "tail6.json"))
        L = ["# tail6 status (%s) — %s, elapsed %.2f h / %.1f h" % (a.run_id, res["status"], res["elapsed_s"] / 3600, a.total_cap / 3600),
             "| root | sub-cubes (march d=%d) | leaves verified | stuck (timeout ×2) | mean/median/max solve s | wall h | cover | status |" % a.depth, "|---|---|---|---|---|---|---|---|"]
        for rid, r in res["per_root"].items():
            L.append("| %s | %s | %s | %s | %s/%s/%s | %.2f | %s | %s |" % (rid, r.get("n_sub"), r.get("leaves"), r.get("stuck"), r.get("mean_solve_s"), r.get("median_solve_s"), r.get("max_solve_s"), (r.get("wall_s") or 0) / 3600, r.get("cover_verified"), r.get("status")))
        open(os.path.join(out, "status.md"), "w").write("\n".join(L) + "\n")
    save()
    log("13 root cubes: %s; depth-0 leaves already verified in part3: %d/%d" % (roots, len(done0), len(cubes0)))
    for rid in roots:
        rem = a.total_cap - (time.time() - T0)
        if rem < 1800:
            log("總上限剩 %.0f s < 1800, 唔開 root %s" % (rem, rid)); res["per_root"][rid] = {"status": "not-started (cap)"}; continue
        cap = min(rem, a.root_cap or rem)
        d = os.path.join(out, "root_%s" % rid); os.makedirs(d, exist_ok=True); t0 = time.time()
        cube = cubes0[int(rid)]
        bcnf = os.path.join(d, "base_root.cnf")
        with open(bcnf, "w") as f:
            f.write("p cnf %d %d\n" % (nvars, len(base_lines) + len(cube))); f.writelines(base_lines)
            for l in cube:
                f.write("%d 0\n" % l)
        r = {"root": rid, "cube": cube, "nlits": len(cube), "base_root_sha": sha(bcnf), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        icnf = os.path.join(d, "sub_d%d.icnf" % a.depth)
        m0 = time.time(); mr = subprocess.run([MARCH, bcnf, "-d", str(a.depth), "-o", icnf], capture_output=True, text=True, timeout=7200)
        open(os.path.join(d, "march.log"), "w").write(mr.stdout + mr.stderr)
        mm = re.search(r"number of cubes (\d+), including (\d+) refuted lea(?:f|ves)", mr.stdout)
        r["march_s"] = round(time.time() - m0, 1); r["march_rc"] = mr.returncode
        if not (mr.returncode in (0, 20) and mm):
            r["status"] = "march-failed"; r["tail"] = (mr.stdout + mr.stderr)[-300:]; res["per_root"][rid] = r; save(); log("root %s: march_cu 失敗 rc=%d" % (rid, mr.returncode)); continue
        r["n_sub"] = int(mm.group(1)); r["march_refuted"] = int(mm.group(2)); r["icnf_sha"] = sha(icnf)
        log("root %s (%d lits): march_cu -d %d → %d 個仔 cube (refuted %d), %.1f s; cnc2 T=%d, 上限 %.2f h" % (rid, len(cube), a.depth, r["n_sub"], r["march_refuted"], r["march_s"], a.timeout, cap / 3600))
        if mr.returncode == 20:
            r["status"] = "march-refuted-root (唔信, 當未證)"; res["per_root"][rid] = r; save(); continue
        cdir = os.path.join(d, "cnc_root%s" % rid)
        argv = [PY, os.path.join(PH2B, "cnc2.py"), "--cnf", bcnf, "--icnf", icnf, "--out", cdir, "--workers", str(a.workers), "--timeout", str(a.timeout), "--solver", "kissat",
                "--proof-dir", pd, "--binary", "--time-budget", str(int(max(600, cap - (time.time() - t0)))), "--split-depth", "3", "--max-split", "0", "--audit-frac", "0.05", "--progress", "300"]
        with open(os.path.join(d, "cnc.log"), "a") as lf:
            p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True); hard = t0 + cap + 600; killed = False
            while True:
                try:
                    rc = p.wait(timeout=30); break
                except subprocess.TimeoutExpired:
                    if time.time() > hard:
                        killed = True
                        try:
                            os.killpg(p.pid, signal.SIGTERM); time.sleep(5); os.killpg(p.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        rc = p.wait(); break
        subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
        for f in os.listdir(pd):
            if f.startswith("cnc_root%s_" % rid) and os.path.isfile(os.path.join(pd, f)):
                os.remove(os.path.join(pd, f))
        if os.path.exists(os.path.join(cdir, "lock")):
            os.remove(os.path.join(cdir, "lock"))
        stc = json.load(open(os.path.join(cdir, "state.json"))) if os.path.exists(os.path.join(cdir, "state.json")) else {}
        done = stc.get("done", {}); solve = [x["solve_s"] for x in done.values()]
        r.update({"cnc_rc": rc, "hard_killed": killed, "leaves": len(done), "pending": len(stc.get("pending", [])) + len(stc.get("running_at_save", [])), "stuck": len(stc.get("stuck", [])),
                  "stuck_ids": [x["id"] for x in stc.get("stuck", [])][:50], "wasted_s": stc.get("wasted_s"), "cnc_status": stc.get("status")})
        if solve:
            r.update({"mean_solve_s": round(statistics.mean(solve), 2), "median_solve_s": round(statistics.median(solve), 2), "max_solve_s": max(solve), "p90_solve_s": round(sorted(solve)[int(0.9 * (len(solve) - 1))], 1),
                      "cpu_solve_s": round(sum(solve), 1), "cpu_verify_s": round(sum(x.get("verify_s", 0) or 0 for x in done.values()), 1), "proof_total_mb": round(sum(x["proof_bytes"] for x in done.values()) / 1e6, 1)})
        if stc.get("sat"):
            r["status"] = "SAT!!"; res["status"] = "SAT!! (G₃ 4 色染色?! 要人手睇)"
        elif stc.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json")):
            cb = json.load(open(os.path.join(cdir, "bundle.json"))); r["status"] = "certified"; r["cover_verified"] = bool(cb.get("cover", {}).get(cb.get("cover_mode") or "", {}).get("verified")); r["audit"] = cb.get("audit"); r["bundle"] = os.path.join(cdir, "bundle.json")
        elif killed:
            r["status"] = "hard-killed"
        elif r["stuck"]:
            r["status"] = "stuck (%d 個仔 cube 2×T=%d s 都 timeout)" % (r["stuck"], 2 * a.timeout)
        else:
            r["status"] = "budget-stop"
        r["wall_s"] = round(time.time() - t0, 1); res["per_root"][rid] = r; save()
        log("root %s: %s — 仔 cube %d, leaf 完成 %d, stuck %d, solve mean/median/max %s/%s/%s s, wall %.2f h%s" % (
            rid, r["status"], r["n_sub"], r["leaves"], r["stuck"], r.get("mean_solve_s"), r.get("median_solve_s"), r.get("max_solve_s"), r["wall_s"] / 3600, (", cover %s" % r.get("cover_verified")) if r["status"] == "certified" else ""))
        if r["status"] == "SAT!!":
            break
    # 組裝
    allok = all(res["per_root"].get(x, {}).get("status") == "certified" and res["per_root"][x].get("cover_verified") for x in roots)
    res["all_roots_certified"] = allok
    if allok:
        log("13 個 root 全清 → 組裝直接證書: 原始 cover (32768 cube 負子句) kissat + drat-trim")
        neg = os.path.join(out, "cover0_pure.cnf"); dr = os.path.join(out, "cover0_pure.drat")
        with open(neg, "w") as f:
            f.write("p cnf %d %d\n" % (nvars, len(cubes0)))
            for c in cubes0:
                f.write(" ".join(str(-l) for l in c) + " 0\n")
        kr = subprocess.run([KISSAT, "-q", "--no-binary", "--time=3600", neg, dr], capture_output=True, text=True, timeout=4000)
        cov = {"rc": kr.returncode, "verified": False}
        if kr.returncode == 20:
            dd = subprocess.run([DRATTRIM, neg, dr], capture_output=True, text=True, timeout=3600); cov["verified"] = any(l.strip() == "s VERIFIED" for l in dd.stdout.splitlines())
            cov["cnf_sha"] = sha(neg); cov["drat_sha"] = sha(dr)
        res["cover0"] = cov
        missing_depth0 = [str(i) for i in range(len(cubes0)) if str(i) not in done0 and str(i) not in roots]
        res["direct_certificate"] = {"claim": "G3 4-colouring CNF base.cnf (sha %s) UNSAT" % BASE_SHA, "cover0": cov, "depth0_leaves_from_part3": len(done0), "depth0_missing_not_in_roots": missing_depth0,
                                     "roots": {x: {"bundle": res["per_root"][x]["bundle"], "n_sub": res["per_root"][x]["n_sub"], "leaves": res["per_root"][x]["leaves"]} for x in roots},
                                     "complete": cov["verified"] and not missing_depth0, "part3_state": os.path.join(PART3, "state.json")}
        json.dump(res["direct_certificate"], open(os.path.join(out, "direct_certificate.json"), "w"), indent=1)
        res["status"] = "ALL ROOTS CERTIFIED; direct certificate assembled (complete=%s)" % res["direct_certificate"]["complete"]
    else:
        bad = [x for x in roots if res["per_root"].get(x, {}).get("status") != "certified"]
        res["status"] = "NOT complete: %d/%d roots certified; 死硬 root: %s" % (len(roots) - len(bad), len(roots), bad)
    save(); log("TAIL6 DONE: %s (%.2f h)" % (res["status"], (time.time() - T0) / 3600))

if __name__ == "__main__":
    main()
