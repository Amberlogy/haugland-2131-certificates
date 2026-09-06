#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cubes.py —— Step 2: march_cu 拆件 + 抽樣外推  v2 (審核後: 外推用政策一致嘅下界 + 區間, 唔再用 survivor mean 做 headline)
  對一個 L1 CNF 跑 march_cu (靜態深度 d → ≤ 2^d 個 cube; march 會將 refuted leaves 照寫入 icnf);
  每檔隨機抽 --sample 個 cube (seed = (seed, depth)), 各自 solver (內置時限 T), UNSAT 就 drat-trim 驗 (記 sha/bytes/用時) 然後刪證明;
  外推 (÷ --campaign-workers W):
    E_survivor = N × mean(完成者 solve) / W                  —— 偏低 (timeout 者計 0), 只做參考
    E_floor    = N × (Σ solve+verify + n_timeout × 3T) / n / W —— 政策一致下界: cnc2 對 timeout cube 收 T + 2T 先拆, 仔 cube 當 0
    E_floor 嘅 bootstrap 90% 區間 (每 cube 成本 censored 喺 3T)
    timeout 比例 k/n + Clopper–Pearson 95% 上界 p_up → 額外 N × p_up × 3T / W
  reliable ⇔ timeout == 0 且 max solve < T/3 且 全部 VERIFIED 且 n ≥ 30; 否則標「總量上不封頂」.
用法:
  python3 cubes.py --cnf enc/L1_b.cnf --out sample --depths 11,14 --sample 30 --timeout 600 --workers 12 --solver kissat
                   [--proof-dir DIR] [--binary] [--seed 1] [--campaign-workers 14] [--march-extra "..."]
輸出: OUT/cubes_dD.icnf, OUT/march_dD.log, OUT/results.jsonl, OUT/summary.json, OUT/summary.md, OUT/status.json
"""
import sys, os, time, json, argparse, subprocess, hashlib, random, threading, statistics, re, math
from concurrent.futures import ThreadPoolExecutor, as_completed

if not __debug__:
    sys.exit("!! 唔准用 python -O")

KISSAT = "/home/user/hadwiger/kissat/build/kissat"
CADICAL = "/home/user/hadwiger/cadical/build/cadical"
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"
MARCH = "/home/user/hadwiger/tools/CnC/march_cu/march_cu"
PROOFS = "/mnt/d/hadwiger/phase2b/proofs"
CHECK_TIMEOUT = int(os.environ.get("CUBES_CHECK_TIMEOUT", 6 * 3600))
MARCH_RE = re.compile(r"number of cubes (\d+), including (\d+) refuted lea(?:f|ves)")

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def read_cnf(path):
    nvars = None; cl = []
    for line in open(path):
        t = line.split()
        if not t or t[0] == "c":
            continue
        if t[0] == "p":
            nvars = int(t[2]); continue
        assert t[-1] == "0", "子句冇 0 結尾: " + line
        cl.append([int(x) for x in t[:-1]])
    assert nvars is not None, "CNF 冇 p 行"
    return nvars, cl

def read_icnf(path):
    cubes = []
    for line in open(path):
        t = line.split()
        if not t or t[0] != "a":
            continue
        assert t[-1] == "0"
        cubes.append([int(x) for x in t[1:-1]])
    return cubes

def run_march(cnf, depth, out, extra):
    icnf = os.path.join(out, "cubes_d%d.icnf" % depth); log = os.path.join(out, "march_d%d.log" % depth)
    t0 = time.time()
    r = subprocess.run([MARCH, cnf, "-d", str(depth), "-o", icnf] + extra, capture_output=True, text=True, timeout=6 * 3600)
    dt = time.time() - t0
    open(log, "w").write(r.stdout + r.stderr)
    assert r.returncode in (0, 20), "march_cu rc=%d: %s" % (r.returncode, (r.stdout + r.stderr)[-500:])
    m = MARCH_RE.search(r.stdout)
    assert m, "march 輸出冇 cube 數目行"
    cubes = read_icnf(icnf)
    assert r.returncode == 0 and all(cubes), "march_cu 喺 root 直接 refute 咗 base (rc=%d, 'a 0') —— 唔信佢, 請直接用 solver + drat-trim" % r.returncode
    assert len(cubes) == int(m.group(1)), "icnf cube 數 %d != march 報 %s" % (len(cubes), m.group(1))
    lens = [len(c) for c in cubes]
    info = {"depth": depth, "n_cubes": len(cubes), "refuted_leaves": int(m.group(2)), "march_s": round(dt, 1), "icnf": icnf, "icnf_sha": sha(icnf),
            "cube_len_mean": round(statistics.mean(lens), 1), "cube_len_min": min(lens), "cube_len_max": max(lens),
            "short_cubes": sum(1 for l in lens if l < depth)}
    print("[march] d=%d: %d 個 cube (含 refuted leaves %d; 短過 depth 嘅 %d), %.1fs, literal 數 mean %.1f (min %d, max %d)" % (
        depth, info["n_cubes"], info["refuted_leaves"], info["short_cubes"], dt, info["cube_len_mean"], info["cube_len_min"], info["cube_len_max"]), flush=True)
    return info, cubes

class St:
    def __init__(self, path):
        self.path = path; self.lock = threading.Lock(); self.d = {"running": {}, "done": [], "tiers": {}}
    def write(self, **kw):
        with self.lock:
            self.d.update(kw); self.d["updated_str"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.d["load"] = round(os.getloadavg()[0], 1)
            tmp = self.path + ".tmp"; json.dump(self.d, open(tmp, "w"), indent=1); os.replace(tmp, self.path)

def model_satisfies(model_pos, clauses):
    pos = set(model_pos)
    return all(any((l > 0 and l in pos) or (l < 0 and -l not in pos) for l in c) for c in clauses)

def solve_cube(a, out, nvars, base, base_text, depth, idx, cube, st, results_path, sha8):
    tag = "d%d_i%05d" % (depth, idx)
    cnf = os.path.join(out, "cubes", tag + ".cnf"); proof = os.path.join(a.proof_dir, "sample_%s_%s_%s.drat" % (os.path.basename(out), sha8, tag))
    with open(cnf, "w") as f:
        f.write("p cnf %d %d\n" % (nvars, len(base) + len(cube)))
        f.write(base_text)
        for l in cube:
            f.write("%d 0\n" % l)
    if a.solver == "kissat":
        argv = [KISSAT, "--time=%d" % int(a.timeout)] + ([] if a.binary else ["--no-binary"]) + [cnf, proof]
    else:
        argv = [CADICAL, "-t", str(int(a.timeout))] + (["--binary"] if a.binary else ["--no-binary"]) + [cnf, proof]
    rec = {"tag": tag, "depth": depth, "idx": idx, "cube": cube, "nlits": len(cube), "cnf_sha": sha(cnf), "started": time.strftime("%H:%M:%S"),
           "load_at_start": round(os.getloadavg()[0], 1)}
    with st.lock:
        st.d["running"][tag] = rec["started"]
    st.write()
    errors = 0; rc = None; text = ""
    try:
        while True:
            t0 = time.time()
            try:
                r = subprocess.run(argv, capture_output=True, text=True, timeout=a.timeout + 300)
                rc = r.returncode; text = r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else "")
            except subprocess.TimeoutExpired:
                rc = -999; text = "backstop kill"
            if rc in (0, 10, 20, -999) or errors + 1 >= a.max_errors:
                break
            errors += 1                       # 例如 9p proof flush 失敗 (rc=-6): 同一 cube 重跑
            print("  [%s] solver rc=%d (%s) → 重跑 (第 %d 次錯)" % (tag, rc, text[-120:].replace("\n", " | "), errors), flush=True)
            if os.path.exists(proof):
                os.remove(proof)
        dt = time.time() - t0
        m = re.search(r"^c conflicts:\s+(\d+)\s+([\d.]+)", text, re.M)
        rec.update({"rc": rc, "solve_s": round(dt, 1), "solver_errors": errors, "conflicts": int(m.group(1)) if m else None,
                    "conflicts_per_s": float(m.group(2)) if m else None})
        rec["proof_bytes"] = os.path.getsize(proof) if os.path.exists(proof) else 0
        if rc == 20:
            rec["status"] = "UNSAT"; rec["proof_sha"] = sha(proof)
            t1 = time.time()
            try:
                dr = subprocess.run([DRATTRIM, cnf, proof, "-t", str(max(60, CHECK_TIMEOUT - 60))], capture_output=True, text=True, timeout=CHECK_TIMEOUT)
                rec["verified"] = any(l.strip() == "s VERIFIED" for l in dr.stdout.splitlines())
                if not rec["verified"]:
                    rec["drattrim_tail"] = dr.stdout[-400:]
            except subprocess.TimeoutExpired:
                rec["verified"] = False; rec["drattrim_tail"] = "checker timeout %ds" % CHECK_TIMEOUT
            rec["drattrim_s"] = round(time.time() - t1, 1)
            rec["proof_lines"] = None if a.binary else int(subprocess.run(["wc", "-l", proof], capture_output=True, text=True, timeout=600).stdout.split()[0])
            if not rec["verified"]:
                fdir = os.path.join(a.proof_dir, "failed"); os.makedirs(fdir, exist_ok=True)
                os.replace(proof, os.path.join(fdir, os.path.basename(proof))); rec["failed_proof"] = os.path.join(fdir, os.path.basename(proof))
        elif rc == 10:
            rec["status"] = "SAT!!"
            rec["model_pos"] = [int(t) for line in text.splitlines() if line.startswith("v") for t in line.split()[1:] if int(t) > 0]
            rec["model_checked"] = model_satisfies(rec["model_pos"], base + [[l] for l in cube])
        elif rc in (0, -999):
            rec["status"] = "timeout"
        else:
            rec["status"] = "rc=%d" % rc; rec["tail"] = text[-300:]
    except Exception as e:
        rec["status"] = "exception"; rec["tail"] = repr(e)[-300:]
    finally:
        if os.path.exists(proof):
            os.remove(proof)      # 驗完即刪 (留 sha + 統計)
    with st.lock:
        st.d["running"].pop(tag, None)
        st.d["done"].append({"tag": tag, "status": rec["status"], "solve_s": rec.get("solve_s"), "verified": rec.get("verified"),
                             "drattrim_s": rec.get("drattrim_s"), "proof_mb": round(rec["proof_bytes"] / 1e6, 1) if "proof_bytes" in rec else None})
        st.d["last_cube_s"] = rec.get("solve_s")
        with open(results_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    st.write()
    print("  [%s] %s solve %ss conflicts %s proof %.1f MB%s" % (tag, rec["status"], rec.get("solve_s"), rec.get("conflicts"), rec.get("proof_bytes", 0) / 1e6,
          (" drat-trim %s %.1fs (%s 行)" % ("VERIFIED ✓" if rec.get("verified") else "!! NOT VERIFIED", rec["drattrim_s"], rec["proof_lines"])) if rc == 20 else ""), flush=True)
    return rec

def clopper_pearson_upper(k, n, alpha=0.05):
    """binomial 比例嘅 95% 上界 (bisection on the beta CDF via regularised incomplete beta — 用 statistics 冇, 自己 bisect binomial tail)."""
    if n == 0:
        return 1.0
    if k == n:
        return 1.0
    def tail_le_k(p):   # P[X <= k] for Bin(n,p)
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))
    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if tail_le_k(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi

def summarize(tier_info, recs, W, T, seed):
    n = len(recs); done = [r for r in recs if r["status"] == "UNSAT"]; to = [r for r in recs if r["status"] == "timeout"]
    bad = [r for r in recs if r["status"] not in ("UNSAT", "timeout")]
    N = tier_info["n_cubes"]
    s = {"depth": tier_info["depth"], "n_cubes": N, "refuted_leaves": tier_info["refuted_leaves"], "march_s": tier_info["march_s"],
         "sampled": n, "done": len(done), "timeout": len(to), "other": len(bad), "other_status": [r["status"] for r in bad],
         "frac_timeout": round(len(to) / n, 3) if n else None, "timeout_upper95": round(clopper_pearson_upper(len(to), n), 3) if n else None,
         "all_verified": all(r.get("verified") for r in done) if done else None, "verified": sum(1 for r in done if r.get("verified")),
         "sample_short_cubes": sum(1 for r in recs if r["nlits"] < tier_info["depth"]),
         "largest_proof_mb_seen": round(max([r.get("proof_bytes", 0) for r in recs] + [0]) / 1e6, 1), "T": T, "W": W}
    if done:
        ts = sorted(r["solve_s"] for r in done); vs = [r["drattrim_s"] for r in done]; pm = [r["proof_bytes"] / 1e6 for r in done]
        s.update({"solve_mean_s": round(statistics.mean(ts), 1), "solve_median_s": round(statistics.median(ts), 1), "solve_p90_s": round(ts[int(0.9 * (len(ts) - 1))], 1),
                  "solve_max_s": round(ts[-1], 1), "solve_top3_s": [round(x, 1) for x in ts[-3:]], "max_share_of_sum": round(ts[-1] / sum(ts), 3) if sum(ts) else None,
                  "verify_mean_s": round(statistics.mean(vs), 1), "verify_max_s": round(max(vs), 1), "proof_mb_mean": round(statistics.mean(pm), 1), "proof_mb_max": round(max(pm), 1)})
        s["E_survivor_h"] = round(N * s["solve_mean_s"] / W / 3600, 2)
        s["E_survivor_verify_h"] = round(N * (s["solve_mean_s"] + s["verify_mean_s"]) / W / 3600, 2)
    # 政策一致下界: 每個 cube 成本 = solve + verify (完成者) 或 3T (timeout 者, 仔 cube 當 0); other 當 3T
    costs = [r["solve_s"] + (r.get("drattrim_s") or 0) for r in done] + [3 * T] * (len(to) + len(bad))
    if costs:
        mean_cost = statistics.mean(costs)
        s["E_floor_h"] = round(N * mean_cost / W / 3600, 2)
        rng = random.Random("%d-d%d-boot" % (seed, tier_info["depth"]))
        boots = []
        for _ in range(2000):
            sm = [costs[rng.randrange(len(costs))] for _ in costs]
            boots.append(statistics.mean(sm))
        boots.sort()
        s["E_floor_ci90_h"] = [round(N * boots[int(0.05 * len(boots))] / W / 3600, 2), round(N * boots[int(0.95 * len(boots)) - 1] / W / 3600, 2)]
        s["E_timeout_mass_upper_h"] = round(N * s["timeout_upper95"] * 3 * T / W / 3600, 2)   # timeout 比例 95% 上界 × 3T
        s["peak_unverified_gb_est"] = round(W * s["largest_proof_mb_seen"] / 1000, 1)
    s["reliable"] = bool(done) and len(to) == 0 and not bad and s["solve_max_s"] < T / 3 and s["all_verified"] and n >= 30
    s["note"] = ("外推可靠 (冇 timeout, max < T/3, 全部 VERIFIED, n ≥ 30)" if s["reliable"] else
                 "!! 總量上不封頂: E_floor 只係下界 (timeout cube 計 3T, 仔 cube 當 0); 見 timeout_upper95 同 E_timeout_mass_upper_h")
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnf", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--depths", default="11,14"); ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=600); ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--solver", default="kissat", choices=["kissat", "cadical"]); ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--march-extra", default=""); ap.add_argument("--campaign-workers", type=int, default=14)
    ap.add_argument("--proof-dir", default=PROOFS); ap.add_argument("--binary", action="store_true"); ap.add_argument("--max-errors", type=int, default=3)
    a = ap.parse_args()
    out = os.path.abspath(os.path.expanduser(a.out)); os.makedirs(os.path.join(out, "cubes"), exist_ok=True)
    a.proof_dir = os.path.abspath(os.path.expanduser(a.proof_dir)); os.makedirs(a.proof_dir, exist_ok=True)
    st = St(os.path.join(out, "status.json"))
    nvars, base = read_cnf(a.cnf)
    base_text = "".join(" ".join(map(str, c)) + " 0\n" for c in base)
    cnf_sha = sha(a.cnf); sha8 = cnf_sha[:8]
    st.write(cnf=a.cnf, cnf_sha=cnf_sha, solver=a.solver, timeout=a.timeout, sample=a.sample, proof_dir=a.proof_dir, binary=a.binary,
             workers=a.workers, cpu_count=os.cpu_count(), started=time.strftime("%Y-%m-%d %H:%M:%S"))
    print("[cubes] %s (sha %s): %d 變量 %d 子句; depths %s, 每檔抽 %d, %s 時限 %.0fs, workers %d (機器 %d vCPU, load %.1f), 證明 → %s%s" % (
        a.cnf, cnf_sha[:16], nvars, len(base), a.depths, a.sample, a.solver, a.timeout, a.workers, os.cpu_count(), os.getloadavg()[0], a.proof_dir,
        " binary" if a.binary else ""), flush=True)
    results_path = os.path.join(out, "results.jsonl")
    summary = {"cnf": a.cnf, "cnf_sha": cnf_sha, "solver": a.solver, "timeout": a.timeout, "sample": a.sample, "workers": a.workers,
               "campaign_workers": a.campaign_workers, "seed": a.seed, "proof_dir": a.proof_dir, "binary": a.binary, "cpu_count": os.cpu_count(),
               "load_start": round(os.getloadavg()[0], 1), "tiers": []}
    tiers = []
    for d in [int(x) for x in a.depths.split(",")]:
        info, cubes = run_march(a.cnf, d, out, a.march_extra.split())
        rng = random.Random("%d-d%d" % (a.seed, d))       # 每檔獨立 seed (Python 3.14 唔收 tuple seed)
        idxs = sorted(rng.sample(range(len(cubes)), min(a.sample, len(cubes))))
        tiers.append((info, cubes, idxs))
        st.d["tiers"][str(d)] = {"n_cubes": info["n_cubes"], "refuted": info["refuted_leaves"], "march_s": info["march_s"], "sampled": len(idxs)}
    st.write()
    for info, cubes, idxs in tiers:
        d = info["depth"]
        print("[sample] d=%d: 抽 %d 個 cube (seed (%d,%d)): %s..." % (d, len(idxs), a.seed, d, idxs[:8]), flush=True)
        recs = []
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(solve_cube, a, out, nvars, base, base_text, d, i, cubes[i], st, results_path, sha8) for i in idxs]
            for fu in as_completed(futs):
                recs.append(fu.result())
        sm = summarize(info, recs, a.campaign_workers, a.timeout, a.seed)
        sm["load_end"] = round(os.getloadavg()[0], 1)
        summary["tiers"].append(sm)
        st.d["tiers"][str(d)].update(sm); st.write()
        print("[tier d=%d] 完成 %d/%d (VERIFIED %d), timeout %d (%.0f%%, 95%% 上界 %.0f%%), other %d; solve mean/median/p90/max = %s/%s/%s/%s s, top3 %s, max 佔總和 %s; "
              "verify mean %s s; proof mean/max %s/%s MB (最大見過 %s MB)\n   外推 (÷%d): E_survivor %s h (偏低) | E_floor %s h [90%% CI %s] | timeout 上界額外 %s h | 峰值未驗證明 %s GB | %s" % (
              d, sm["done"], sm["sampled"], sm["verified"], sm["timeout"], 100 * (sm["frac_timeout"] or 0), 100 * (sm["timeout_upper95"] or 0), sm["other"],
              sm.get("solve_mean_s"), sm.get("solve_median_s"), sm.get("solve_p90_s"), sm.get("solve_max_s"), sm.get("solve_top3_s"), sm.get("max_share_of_sum"),
              sm.get("verify_mean_s"), sm.get("proof_mb_mean"), sm.get("proof_mb_max"), sm["largest_proof_mb_seen"], a.campaign_workers,
              sm.get("E_survivor_h"), sm.get("E_floor_h"), sm.get("E_floor_ci90_h"), sm.get("E_timeout_mass_upper_h"), sm.get("peak_unverified_gb_est"), sm["note"]), flush=True)
        if any(r["status"] == "SAT!!" for r in recs):
            print("!! 有 cube 判 SAT (model_checked=%s) —— 主張唔成立或者編碼有 bug, 停" % [r.get("model_checked") for r in recs if r["status"] == "SAT!!"], flush=True)
            json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1); sys.exit(10)
    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); summary["load_end"] = round(os.getloadavg()[0], 1)
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1)
    L = ["# Step 2 抽樣外推 (%s, sha %s…, solver %s, 每 cube 時限 T=%.0fs, 每檔抽 %d, seed %d, 抽樣時 %d workers 並行, 外推用 W=%d workers)" % (
        os.path.basename(a.cnf), cnf_sha[:12], a.solver, a.timeout, a.sample, a.seed, a.workers, a.campaign_workers), "",
         "| depth | cubes | refuted | march s | 完成/抽 (VERIFIED) | timeout k/n (95% 上界) | solve mean/median/p90/max s | top3 s | verify mean s | proof mean/max MB | E_survivor h (偏低) | **E_floor h** | E_floor 90% CI | timeout 上界額外 h | 峰值未驗 GB | 可靠? |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sm in summary["tiers"]:
        L.append("| %d | %d | %d | %s | %d/%d (%d) | %d/%d (%.0f%%) | %s/%s/%s/%s | %s | %s | %s/%s | %s | **%s** | %s | %s | %s | %s |" % (
            sm["depth"], sm["n_cubes"], sm["refuted_leaves"], sm["march_s"], sm["done"], sm["sampled"], sm["verified"], sm["timeout"], sm["sampled"],
            100 * (sm["timeout_upper95"] or 0), sm.get("solve_mean_s"), sm.get("solve_median_s"), sm.get("solve_p90_s"), sm.get("solve_max_s"), sm.get("solve_top3_s"),
            sm.get("verify_mean_s"), sm.get("proof_mb_mean"), sm.get("proof_mb_max"), sm.get("E_survivor_h"), sm.get("E_floor_h"), sm.get("E_floor_ci90_h"),
            sm.get("E_timeout_mass_upper_h"), sm.get("peak_unverified_gb_est"), "✓" if sm["reliable"] else "✗ 上不封頂"))
    L += ["", "E_floor = N × mean(完成者 solve+verify, timeout 者計 3T) ÷ W —— 政策一致下界 (cnc2: T → 2T → march 再拆, 仔 cube 當 0); "
          "E_survivor 只計完成者 (偏低, 參考); timeout 上界 = Clopper–Pearson 95%; 可靠 ⇔ 0 timeout ∧ max < T/3 ∧ 全 VERIFIED ∧ n ≥ 30.", ""]
    open(os.path.join(out, "summary.md"), "w").write("\n".join(L) + "\n")
    st.write(finished=True)
    print("[cubes] 完成 → %s/summary.md" % out, flush=True)

if __name__ == "__main__":
    main()
