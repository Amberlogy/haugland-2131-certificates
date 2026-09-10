#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cnc2.py —— Step 4: cube-and-conquer 戰役 (march_cu cube 檔 + 逐 cube solver → 證明 → 檢查器 VERIFIED → 記 sha/用時 → 刪證明檔)  v2 (審核後)

證書結構 (bundle):
  (1) 每個 leaf cube c_i: base.cnf + c_i 嘅 unit 子句 → solver UNSAT → 檢查器 VERIFIED (drat-trim 對 DRAT; lrat-check 對 LRAT); 證明驗完即刪, 留 sha256/bytes/統計
  (2) cover 證書: ¬c_1 ∧ … ∧ ¬c_n (純 tautology 檢查, 冇 base) → kissat UNSAT → drat-trim VERIFIED.
      march_cu 會將 refuted leaves 照樣寫入 icnf (cube.c printDecisionNode), 所以正常情況純 cover 一定係 tautology;
      純 cover 判 SAT = 有未覆蓋區域 (bug 訊號), 會印出嚟, 然後先退到 base ∧ ⋀¬c_i (照樣健全) 再試.
  (1)+(2) ⇒ base UNSAT.  任何 cube 判 SAT ⇒ 記低 model (逐子句核對) ⇒ 即停.
  (3) 審計: 隨機抽 --audit-frac 嘅 leaf 由零重做 (kissat + DRAT + drat-trim), 全部要 VERIFIED.
timeout 政策: 第 1 次 T; timeout (rc 0 或者 backstop kill) → 第 2 次 2T; 再 timeout → march_cu 對該 cube 再拆 (-d --split-depth), 仔 cube 各自由 T 開始 (樹深記落 id: "123.5.2").
  march 喺 root 直接 refute (rc 20, 'a 0') 嘅 cube: 唔信 march, 父 cube 以 4T 再跑一次 (attempt 3); 再唔得先算 stuck.
  solver 非 0/10/20 退出 (例如 9p 寫證明失敗) / 檢查器 NOT VERIFIED: 同一時限重排, 錯夠 --max-errors 次算 stuck; NOT VERIFIED 嘅證明搬去 failed/ 留底.
  檢查器超時 (CHECK_TIMEOUT): 證明太大 → 直接拆 (同一 solver 重跑會出同一份證明).
磁碟紀律: 本 run 未驗證明總量 ≤ 200 GB; 證明碟係 /mnt/ 就要 ismount + 剩 ≥ 300 GB; 係 ext4 (vhdx 喺 C:) 就要 C: 剩 ≥ 20 GB; 唔夠即暫停 (status.json paused).
checkpoint: state.json 最多每 5 秒覆寫 (atomic); ledger.csv 逐 cube append; --resume 續跑 (拒絕已 SAT 嘅 run; 有 lock 檔防雙開).

用法:
  python3 cnc2.py --cnf base.cnf --icnf cubes.icnf --out DIR [--workers 14] [--timeout 600] [--solver kissat|cadical|cadical-lrat]
                  [--proof-dir DIR] [--binary] [--time-budget 259200] [--split-depth 3] [--max-split 4] [--max-errors 3] [--audit-frac 0.05] [--seed 1]
  python3 cnc2.py --resume --out DIR [--workers ..] [--time-budget ..] [--timeout ..] [--max-split ..] [--cover-timeout ..] [--requeue-stuck]
"""
import sys, os, time, json, csv, argparse, subprocess, hashlib, random, threading, statistics, re, shutil
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

if not __debug__:
    sys.exit("!! 唔准用 python -O")

KISSAT = "/home/user/hadwiger/kissat/build/kissat"
CADICAL = "/home/user/hadwiger/cadical/build/cadical"
DRATTRIM = "/home/user/hadwiger/drat-trim/drat-trim"
LRATCHECK = "/home/user/hadwiger/drat-trim/lrat-check"
CAKELPR = "/home/user/hadwiger/tools/cake_lpr/cake_lpr"
MARCH = "/home/user/hadwiger/tools/CnC/march_cu/march_cu"
PROOFS = "/mnt/d/hadwiger/phase2b/proofs"
CHECK_TIMEOUT = int(os.environ.get("CNC2_CHECK_TIMEOUT", 6 * 3600))
DISK_UNVERIFIED_GB_MAX = 200.0
DISK_D_MIN_GB = 300.0
DISK_C_MIN_GB = 20.0
TOOLS = {"kissat": KISSAT, "cadical": CADICAL, "drat-trim": DRATTRIM, "lrat-check": LRATCHECK, "march_cu": MARCH, "cake_lpr": CAKELPR}

# ---------------- 小工具 ----------------
def sha_and_lines(path):
    """一次過讀: sha256 + 換行數"""
    h = hashlib.sha256(); n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk); n += chunk.count(b"\n")
    return h.hexdigest(), n

def sha(path):
    return sha_and_lines(path)[0]

def free_gb(path):
    st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9

def du_prefix_gb(path, prefix):
    tot = 0
    try:
        for f in os.listdir(path):
            if f.startswith(prefix):
                try:
                    tot += os.path.getsize(os.path.join(path, f))
                except OSError:
                    pass
    except OSError:
        pass
    return tot / 1e9

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

def read_icnf(path, nvars, allow_empty=False):
    cubes = []
    for line in open(path):
        t = line.split()
        if not t or t[0] != "a":
            continue
        assert t[-1] == "0", "cube 行冇 0 結尾: " + line
        lits = [int(x) for x in t[1:-1]]
        if not lits:
            assert allow_empty, "icnf 有空 cube (a 0)"
        assert all(1 <= abs(l) <= nvars for l in lits), "cube literal 超出變量範圍: " + line
        assert len({abs(l) for l in lits}) == len(lits), "cube 有重複變量: " + line
        cubes.append(lits)
    assert cubes, "icnf 冇 cube"
    assert len({tuple(sorted(c)) for c in cubes}) == len(cubes), "icnf 有重複 cube"
    return cubes

MARCH_RE = re.compile(r"number of cubes (\d+), including (\d+) refuted lea(?:f|ves)")

def tool_info():
    info = {}
    for name, p in TOOLS.items():
        d = {"path": p, "sha256": sha(p) if os.path.exists(p) else None}
        try:
            if name in ("kissat", "cadical"):
                d["version"] = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            pass
        info[name] = d
    return info

def solver_argv(solver, cnf, proof, tlim, binary=False):
    # kissat: binary 係預設, 只有 --no-binary; cadical: --binary / --no-binary
    if solver == "kissat":
        return [KISSAT, "--time=%d" % int(tlim)] + ([] if binary else ["--no-binary"]) + [cnf, proof], "drat"
    if solver == "cadical":
        return [CADICAL, "-t", str(int(tlim))] + (["--binary"] if binary else ["--no-binary"]) + [cnf, proof], "drat"
    if solver == "cadical-lrat":
        return [CADICAL, "-t", str(int(tlim)), "--no-binary", "--lrat", cnf, proof], "lrat"   # lrat-check 淨識 ASCII
    raise ValueError(solver)

def check_proof(kind, cnf, proof):
    """回傳 dict: checker, checker_rc, verified, verify_s, timeout, tail. 字串整行精確匹配, 唔信退出碼."""
    t0 = time.time()
    if kind == "drat":
        argv, name, want = [DRATTRIM, cnf, proof, "-t", str(max(60, CHECK_TIMEOUT - 60))], "drat-trim", "s VERIFIED"
    else:
        argv, name, want = [LRATCHECK, cnf, proof], "lrat-check", "c VERIFIED"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"checker": name, "checker_rc": None, "verified": False, "verify_s": round(time.time() - t0, 1), "checker_timeout": True,
                "tail": "checker timeout after %ds" % CHECK_TIMEOUT}
    ok = any(l.strip() == want for l in r.stdout.splitlines())
    return {"checker": name, "checker_rc": r.returncode, "verified": ok, "verify_s": round(time.time() - t0, 1), "checker_timeout": False,
            "tail": "" if ok else (r.stdout + r.stderr)[-400:]}

def model_satisfies(model_pos, clauses):
    pos = set(model_pos)
    return all(any((l > 0 and l in pos) or (l < 0 and -l not in pos) for l in c) for c in clauses)

# ---------------- run 狀態 ----------------
class Run:
    def __init__(self, out):
        self.out = out
        self.cubedir = os.path.join(out, "cubes"); os.makedirs(self.cubedir, exist_ok=True)
        self.state_p = os.path.join(out, "state.json"); self.ledger_p = os.path.join(out, "ledger.csv")
        self.status_p = os.path.join(out, "status.json")
        self.last_error = None; self.paused = None; self.last_save = 0.0
        self.tag = os.path.basename(os.path.abspath(out))
    def save(self, st, force=False):
        if not force and time.time() - self.last_save < 5.0:
            return
        tmp = self.state_p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, self.state_p); self.last_save = time.time()
    def ledger(self, row):
        new = not os.path.exists(self.ledger_p)
        with open(self.ledger_p, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "depth", "nlits", "attempt", "timeout", "status", "solve_s", "conflicts", "proof_bytes",
                                              "proof_lines", "proof_sha", "checker", "verify_s", "verified", "elapsed_s", "when", "tail"])
            if new:
                w.writeheader()
            w.writerow(row)
    def status(self, st, running, extra=None):
        done = st["done"]; n_done = len(done)
        solve = [d["solve_s"] for d in done.values()]; ver = [d.get("verify_s", 0) for d in done.values()]
        mean_s = statistics.mean(solve) if solve else None
        remaining = len(st["pending"]) + len(running)
        wasted = st.get("wasted_s", 0.0)
        eta_h = None
        if mean_s is not None and n_done:
            per = (sum(solve) + sum(ver) + wasted) / n_done      # 每個完成 leaf 嘅實際成本 (連 timeout 浪費)
            eta_h = round(remaining * per / max(1, st["workers"]) / 3600, 2)
        pd = st["proof_dir"]
        d = {"updated_str": time.strftime("%Y-%m-%d %H:%M:%S"), "done": n_done, "total": n_done + remaining, "running": len(running),
             "pending": len(st["pending"]), "retry": sum(1 for p in st["pending"] if p.get("attempt", 1) > 1 or p.get("errors", 0)),
             "split_events": st["split_events"], "stuck": len(st["stuck"]), "eta": ("%s h" % eta_h) if eta_h is not None else None,
             "mean_cube_s": round(mean_s, 1) if mean_s is not None else None, "max_cube_s": max(solve) if solve else None,
             "last_cube_s": st.get("last_cube_s"), "last_error": self.last_error, "paused": self.paused, "solver_errors": st.get("solver_errors", 0),
             "wall_s": st["wall_s"], "solver": st["solver"], "timeout": st["timeout"], "workers": st["workers"], "proof_dir": pd,
             "disk_D_free_gb": round(free_gb("/mnt/d"), 1) if os.path.ismount("/mnt/d") else None,
             "disk_C_free_gb": round(free_gb("/mnt/c"), 1) if os.path.ismount("/mnt/c") else None,
             "proof_dir_free_gb": round(free_gb(pd), 1), "unverified_proof_gb": round(du_prefix_gb(pd, self.tag + "_"), 2),
             "proof_total_mb": round(sum(d["proof_bytes"] for d in done.values()) / 1e6, 1), "load": round(os.getloadavg()[0], 1)}
        if extra:
            d.update(extra)
        tmp = self.status_p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, self.status_p)

def cube_cnf_path(run, cid):
    return os.path.join(run.cubedir, "cube_%s.cnf" % cid)

def write_cube_cnf(path, nvars, nbase, base_text, cube):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("p cnf %d %d\n" % (nvars, nbase + len(cube)))
        f.write(base_text)
        for l in cube:
            f.write("%d 0\n" % l)
    os.replace(tmp, path)

def kind_of(solver):
    return "lrat" if solver == "cadical-lrat" else "drat"

def solve_cube(run, st, base_text, nvars, nbase, base_clauses, job):
    """喺 worker thread 跑: 永遠回傳 dict, 唔 raise; 證明檔喺 finally 清走 (除非搬咗去 failed/)."""
    cid, cube, attempt = job["id"], job["cube"], job.get("attempt", 1)
    tlim = st["timeout"] * (2 ** (attempt - 1))
    cnf = cube_cnf_path(run, cid)
    proof = os.path.join(st["proof_dir"], "%s_%s.%s" % (run.tag, cid, kind_of(st["solver"])))
    res = {"id": cid, "cube": cube, "attempt": attempt, "timeout": tlim, "solve_s": 0.0, "conflicts": None, "proof_bytes": 0}
    try:
        write_cube_cnf(cnf, nvars, nbase, base_text, cube)
        res["cnf_sha"] = sha(cnf)
        argv, kind = solver_argv(st["solver"], cnf, proof, tlim, st.get("binary", False))
        t0 = time.time()
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=tlim + 300)
            rc, text = r.returncode, r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr else "")
        except subprocess.TimeoutExpired:
            rc, text = -999, "backstop kill at tlim+300"
        res["solve_s"] = round(time.time() - t0, 1)
        m = re.search(r"^c conflicts:\s+(\d+)", text, re.M)
        res["conflicts"] = int(m.group(1)) if m else None
        res["proof_bytes"] = os.path.getsize(proof) if os.path.exists(proof) else 0
        if rc == 20:
            res["status"] = "UNSAT"
            res["proof_sha"], nl = sha_and_lines(proof)
            res["proof_lines"] = None if (st.get("binary", False) and kind == "drat") else nl
            res.update(check_proof(kind, cnf, proof))
            if res["verified"]:
                os.remove(cnf)      # cube CNF 可由 base + cube 重建 (writer deterministic), 留 sha; 審計會重建並核對 sha
            else:
                fdir = os.path.join(st["proof_dir"], "failed"); os.makedirs(fdir, exist_ok=True)
                kept = os.path.join(fdir, os.path.basename(proof) + ".attempt%d" % attempt)
                shutil.move(proof, kept); res["failed_proof"] = kept
        elif rc == 10:
            res["status"] = "SAT"
            res["model_pos"] = [int(t) for line in text.splitlines() if line.startswith("v") for t in line.split()[1:] if int(t) > 0]
            res["model_checked"] = model_satisfies(res["model_pos"], base_clauses + [[l] for l in cube])
        elif rc in (0, -999):
            res["status"] = "timeout"
        else:
            res["status"] = "rc=%d" % rc; res["tail"] = text[-400:]
    except Exception as e:
        res["status"] = "exception"; res["tail"] = repr(e)[-400:]
    finally:
        if os.path.exists(proof):
            os.remove(proof)
    return res

def split_cube(run, st, base_text, nvars, nbase, job):
    """用 march_cu 對 cube 再拆. 回傳 (仔 cube list, refuted, root_refuted)."""
    cid, cube = job["id"], job["cube"]
    cnf = cube_cnf_path(run, cid)
    write_cube_cnf(cnf, nvars, nbase, base_text, cube)
    icnf = os.path.join(run.cubedir, "split_%s.icnf" % cid)
    try:
        r = subprocess.run([MARCH, cnf, "-d", str(st["split_depth"]), "-o", icnf], capture_output=True, text=True, timeout=3600)
    finally:
        if os.path.exists(cnf):
            os.remove(cnf)
    assert r.returncode in (0, 20), "march_cu rc=%d: %s" % (r.returncode, (r.stdout + r.stderr)[-300:])
    m = MARCH_RE.search(r.stdout)
    assert m, "march 輸出冇 cube 數目行: " + r.stdout[-300:]
    kids = read_icnf(icnf, nvars, allow_empty=True)
    if r.returncode == 20 or any(len(k) == 0 for k in kids):
        return [], int(m.group(2)), True
    parent_vars = {abs(x) for x in cube}
    out = [list(cube) + [l for l in k if abs(l) not in parent_vars] for k in kids]
    assert len({tuple(sorted(c)) for c in out}) == len(out), "拆出嚟嘅仔 cube 有重複"
    return out, int(m.group(2)), False

def cover_certificate(run, st, nvars, base_clauses):
    leaves = [d["cube"] for d in st["done"].values()]
    neg = [[-l for l in c] for c in leaves]
    out = st.get("cover", {})
    for mode, extra in (("pure", []), ("with_base", base_clauses)):
        if mode in out and out[mode].get("verified"):
            return out, mode
        cnf = os.path.join(run.out, "cover_%s.cnf" % mode); proof = os.path.join(st["proof_dir"], "%s_cover_%s.drat" % (run.tag, mode))
        with open(cnf, "w") as f:
            f.write("p cnf %d %d\n" % (nvars, len(extra) + len(neg)))
            for c in extra:
                f.write(" ".join(map(str, c)) + " 0\n")
            for c in neg:
                f.write(" ".join(map(str, c)) + " 0\n")
        t0 = time.time()
        rec = {"mode": mode, "cnf": cnf, "cnf_sha": sha(cnf), "n_leaves": len(neg)}
        try:
            r = subprocess.run([KISSAT, "-q", "--no-binary", "--time=%d" % int(st["cover_timeout"]), cnf, proof], capture_output=True, text=True,
                               timeout=st["cover_timeout"] + 300)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -999; r = None
        rec["rc"] = rc; rec["solve_s"] = round(time.time() - t0, 1)
        if rc == 20:
            rec["proof_sha"], rec["proof_lines"] = sha_and_lines(proof); rec["proof_bytes"] = os.path.getsize(proof)
            rec.update(check_proof("drat", cnf, proof))
            keep = os.path.join(run.out, "cover_%s.drat" % mode)
            shutil.move(proof, keep); rec["proof_kept"] = keep
            out[mode] = rec; st["cover"] = out; run.save(st, force=True)
            print("[cover] %s: kissat UNSAT %.1fs, DRAT %d 行, drat-trim %s" % (mode, rec["solve_s"], rec["proof_lines"], "VERIFIED ✓" if rec["verified"] else "!! NOT VERIFIED"), flush=True)
            if rec["verified"]:
                return out, mode
        else:
            if rc == 10 and r is not None:
                model = [int(t) for line in r.stdout.splitlines() if line.startswith("v") for t in line.split()[1:] if int(t) > 0]
                rec["uncovered_model_pos"] = model
                print("!! [cover] %s: SAT —— 有未覆蓋區域 (bug 訊號), model 正 literal %d 個已記落 state.json" % (mode, len(model)), flush=True)
            else:
                print("[cover] %s: rc=%s (timeout/其他)" % (mode, rc), flush=True)
            if os.path.exists(proof):
                os.remove(proof)
            out[mode] = rec; st["cover"] = out; run.save(st, force=True)
    return out, None

def audit(run, st, base_text, nvars, nbase, frac, seed):
    ids = sorted(st["done"])
    k = max(1, int(round(frac * len(ids))))
    pick = random.Random(seed).sample(ids, k)
    done_aud = {r["id"]: r for r in st.get("audit", [])}
    todo = [i for i in pick if not done_aud.get(i, {}).get("ok")]
    print("[audit] 由零重做 %d/%d 個 leaf (kissat + DRAT + drat-trim, seed %d; 已做 %d)" % (k, len(ids), seed, k - len(todo)), flush=True)
    tl = max(4 * st["timeout"], 3600)
    def one(cid):
        d = st["done"][cid]
        cnf = os.path.join(run.cubedir, "audit_%s.cnf" % cid); proof = os.path.join(st["proof_dir"], "%s_audit_%s.drat" % (run.tag, cid))
        rec = {"id": cid, "ok": False}
        try:
            write_cube_cnf(cnf, nvars, nbase, base_text, d["cube"])
            rec["cnf_sha_match"] = (sha(cnf) == d["cnf_sha"])
            t0 = time.time()
            try:
                r = subprocess.run([KISSAT, "-q", "--no-binary", "--time=%d" % int(tl), cnf, proof], capture_output=True, text=True, timeout=tl + 300)
                rec["rc"] = r.returncode
            except subprocess.TimeoutExpired:
                rec["rc"] = -999
            rec["solve_s"] = round(time.time() - t0, 1)
            if rec["rc"] == 20:
                rec.update(check_proof("drat", cnf, proof)); rec["proof_bytes"] = os.path.getsize(proof)
            rec["ok"] = bool(rec["cnf_sha_match"] and rec["rc"] == 20 and rec.get("verified", False))
        except Exception as e:
            rec["tail"] = repr(e)[-300:]
        finally:
            for p in (proof, cnf):
                if os.path.exists(p):
                    os.remove(p)
        return rec
    with ThreadPoolExecutor(max_workers=st["workers"]) as ex:
        for rec in ex.map(one, todo):
            done_aud[rec["id"]] = rec; st["audit"] = list(done_aud.values()); run.save(st, force=True)
            print("  [audit %s] rc=%s %ss sha_match=%s %s" % (rec["id"], rec.get("rc"), rec.get("solve_s"), rec.get("cnf_sha_match"),
                  "drat-trim VERIFIED ✓" if rec["ok"] else "!! 唔 ok: " + str(rec.get("tail", rec.get("rc")))), flush=True)
    return [done_aud[i] for i in pick]

def disk_ok(run, st):
    pd = st["proof_dir"]
    if du_prefix_gb(pd, run.tag + "_") > DISK_UNVERIFIED_GB_MAX:
        return False
    if pd.startswith("/mnt/"):
        top = "/" + "/".join(pd.split("/")[1:3])
        return os.path.ismount(top) and free_gb(pd) >= DISK_D_MIN_GB
    # ext4 (vhdx 喺 C:): 睇 host C: 真剩餘
    c_free = free_gb("/mnt/c") if os.path.ismount("/mnt/c") else free_gb(pd)
    return c_free >= DISK_C_MIN_GB

def disk_msg(run, st):
    pd = st["proof_dir"]
    return "unverified %.1f GB (cap %.0f), proof-dir free %.0f GB, C: free %s GB" % (
        du_prefix_gb(pd, run.tag + "_"), DISK_UNVERIFIED_GB_MAX, free_gb(pd), round(free_gb("/mnt/c"), 1) if os.path.ismount("/mnt/c") else "?")

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnf"); ap.add_argument("--icnf"); ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=14); ap.add_argument("--timeout", type=float, default=None)
    ap.add_argument("--solver", default="kissat", choices=["kissat", "cadical", "cadical-lrat"])
    ap.add_argument("--time-budget", type=float, default=72 * 3600); ap.add_argument("--resume", action="store_true")
    ap.add_argument("--split-depth", type=int, default=3); ap.add_argument("--max-split", type=int, default=None)
    ap.add_argument("--audit-frac", type=float, default=0.05); ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--cover-timeout", type=float, default=None); ap.add_argument("--progress", type=float, default=120)
    ap.add_argument("--proof-dir", default=PROOFS); ap.add_argument("--binary", action="store_true")
    ap.add_argument("--max-errors", type=int, default=3); ap.add_argument("--requeue-stuck", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(os.path.expanduser(a.out)); os.makedirs(out, exist_ok=True)
    run = Run(out)
    # lock
    lock = os.path.join(out, "lock")
    if os.path.exists(lock):
        try:
            pid = int(open(lock).read().split()[0]); os.kill(pid, 0)
            sys.exit("!! %s 已經有另一個 cnc2 (pid %d) 跑緊, 唔准雙開" % (out, pid))
        except (ProcessLookupError, ValueError):
            pass
    open(lock, "w").write("%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S")))
    T0 = time.time()
    if a.resume:
        st = json.load(open(run.state_p))
        if st.get("sat"):
            sys.exit("!! 呢個 run 已經有 cube 判 SAT (id %s, model_checked=%s); 唔准 resume" % (st["sat"]["id"], st["sat"].get("model_checked")))
        st["workers"] = a.workers; st["max_errors"] = a.max_errors
        for k, v in (("timeout", a.timeout), ("max_split", a.max_split), ("cover_timeout", a.cover_timeout)):
            if v is not None:
                st[k] = v
        st["pending"] = st.get("running_at_save", []) + st["pending"]; st["running_at_save"] = []
        if a.requeue_stuck:
            for s in st["stuck"]:
                st["pending"].append({"id": s["id"], "cube": s["cube"], "attempt": s.get("attempt", 1)})
            st["stuck"] = []
        base_wall = st["wall_s"]
        os.makedirs(st["proof_dir"], exist_ok=True)
        left = [f for f in os.listdir(st["proof_dir"]) if f.startswith(run.tag + "_") and not f.endswith(".attempt")]
        if left:
            print("[resume] 注意: proof-dir 有 %d 個上次留低嘅本 run 證明檔 (可能有孤兒 solver), 先刪: %s" % (len(left), left[:5]), flush=True)
            for f in left:
                os.remove(os.path.join(st["proof_dir"], f))
        print("[resume] leaves 完成 %d, pending %d (含上次跑緊嘅), stuck %d, split_events %d, 之前 wall %.0fs" % (
            len(st["done"]), len(st["pending"]), len(st["stuck"]), st["split_events"], base_wall), flush=True)
    else:
        assert a.cnf and a.icnf and not os.path.exists(run.state_p), "首跑要 --cnf --icnf, 而且 --out 唔可以有 state.json"
        nvars, base = read_cnf(a.cnf)
        cubes = read_icnf(a.icnf, nvars)
        base_copy = os.path.join(out, "base.cnf"); shutil.copyfile(a.cnf, base_copy)
        icnf_copy = os.path.join(out, "cubes.icnf"); shutil.copyfile(a.icnf, icnf_copy)
        pd = os.path.abspath(os.path.expanduser(a.proof_dir)); os.makedirs(pd, exist_ok=True)
        st = {"base_cnf": base_copy, "base_sha": sha(base_copy), "icnf": icnf_copy, "icnf_sha": sha(icnf_copy), "nvars": nvars, "n_base": len(base),
              "n_cubes0": len(cubes), "solver": a.solver, "timeout": a.timeout or 600.0, "workers": a.workers, "split_depth": a.split_depth,
              "max_split": a.max_split if a.max_split is not None else 4, "cover_timeout": a.cover_timeout or 6 * 3600, "proof_dir": pd,
              "binary": a.binary, "max_errors": a.max_errors, "tools": tool_info(), "run_tag": run.tag,
              "pending": [{"id": str(i), "cube": c, "attempt": 1} for i, c in enumerate(cubes)],
              "done": {}, "running_at_save": [], "split_events": 0, "split_refuted": 0, "march_root_refuted": [], "stuck": [], "wall_s": 0.0,
              "wasted_s": 0.0, "solver_errors": 0, "sat": None, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        base_wall = 0.0
        run.save(st, force=True)
        print("[start] base %s (sha %s): %d 變量 %d 子句; %d 個 cube (sha %s); solver %s%s, timeout %.0fs, workers %d, split-depth %d, proof-dir %s" % (
            a.cnf, st["base_sha"][:16], nvars, len(base), len(cubes), st["icnf_sha"][:16], a.solver, " (binary)" if a.binary else "", st["timeout"],
            a.workers, a.split_depth, pd), flush=True)
    nvars, base = read_cnf(st["base_cnf"])
    assert sha(st["base_cnf"]) == st["base_sha"], "base.cnf sha 對唔上 state.json"
    base_text = "".join(" ".join(map(str, c)) + " 0\n" for c in base); nbase = len(base)
    pending = st["pending"]; running = {}; status = "running"; last_prog = 0
    error_ids = set()
    def elapsed():
        return base_wall + time.time() - T0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        while pending or running:
            if elapsed() > a.time_budget and not running:
                status = "budget-stop"; break
            while not disk_ok(run, st) and not running:
                run.paused = "disk: " + disk_msg(run, st)
                print("[pause] " + run.paused, flush=True); run.status(st, running); time.sleep(300)
            run.paused = None
            while pending and len(running) < a.workers and elapsed() <= a.time_budget and disk_ok(run, st):
                job = pending.pop(0)
                fut = ex.submit(solve_cube, run, st, base_text, nvars, nbase, base, job)
                running[fut] = job
            if not running:
                if elapsed() > a.time_budget:
                    status = "budget-stop"; break
                time.sleep(5); continue
            done_set, _ = wait(list(running), timeout=a.progress, return_when=FIRST_COMPLETED)
            for fut in done_set:
                job = running.pop(fut)
                res = fut.result()          # solve_cube 唔會 raise
                depth = job["id"].count(".")
                row = {"id": res["id"], "depth": depth, "nlits": len(res["cube"]), "attempt": res["attempt"], "timeout": res["timeout"], "status": res["status"],
                       "solve_s": res["solve_s"], "conflicts": res["conflicts"], "proof_bytes": res["proof_bytes"], "proof_lines": res.get("proof_lines"),
                       "proof_sha": res.get("proof_sha"), "checker": res.get("checker"), "verify_s": res.get("verify_s"), "verified": res.get("verified"),
                       "elapsed_s": round(elapsed(), 1), "when": time.strftime("%H:%M:%S"),
                       "tail": (res.get("tail", "") or "").replace("\n", " | ")[-300:] if res["status"] not in ("UNSAT", "timeout") or res.get("verified") is False else ""}
                run.ledger(row)
                st["last_cube_s"] = res["solve_s"]
                if res["status"] == "UNSAT" and res.get("verified"):
                    st["done"][res["id"]] = {k: res[k] for k in ("cube", "attempt", "timeout", "solve_s", "conflicts", "proof_bytes", "proof_lines",
                                                                 "proof_sha", "cnf_sha", "checker", "checker_rc", "verify_s")}
                    if res["id"] in error_ids:
                        error_ids.discard(res["id"])
                        if not error_ids:
                            run.last_error = None
                    print("  leaf %s d%d (%d lits, 第 %d 次, T=%.0f): UNSAT %.1fs, proof %.1f MB (%s 行), %s VERIFIED ✓ %.1fs  [完成 %d, pending %d, 跑緊 %d]" % (
                        res["id"], depth, len(res["cube"]), res["attempt"], res["timeout"], res["solve_s"], res["proof_bytes"] / 1e6, res.get("proof_lines"),
                        res["checker"], res["verify_s"], len(st["done"]), len(pending), len(running)), flush=True)
                elif res["status"] == "UNSAT":             # NOT VERIFIED
                    st["solver_errors"] += 1; st["wasted_s"] += res["solve_s"] + (res.get("verify_s") or 0)
                    if res.get("checker_timeout"):          # 檢查器超時: 證明太大, 即場拆 (同一 solver 重跑會出同一份證明, 冇意思)
                        run.last_error = "leaf %s 證明 %.1f MB 檢查器超時 (%ds) → 即場拆" % (res["id"], res["proof_bytes"] / 1e6, CHECK_TIMEOUT); error_ids.add(res["id"])
                        print("!! " + run.last_error, flush=True)
                        st["checker_timeouts"] = st.get("checker_timeouts", 0) + 1
                        if depth >= st["max_split"]:
                            st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "checker timeout at max-split"})
                        else:
                            try:
                                kids, refuted, root_ref = split_cube(run, st, base_text, nvars, nbase, job)
                            except Exception as e:
                                st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "split failed after checker timeout: %r" % e}); continue
                            if root_ref:
                                st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "checker timeout, march refuted root"})
                            else:
                                st["split_events"] += 1; st["split_refuted"] += refuted
                                pending = [{"id": "%s.%d" % (res["id"], k), "cube": c, "attempt": 1} for k, c in enumerate(kids)] + pending
                                print("  cube %s → march_cu 拆做 %d 個仔 cube (樹深 %d)" % (res["id"], len(kids), depth + 1), flush=True)
                    else:
                        errs = job.get("errors", 0) + 1
                        run.last_error = "leaf %s 證明 NOT VERIFIED (第 %d 次; 證明留喺 %s): %s" % (res["id"], errs, res.get("failed_proof"), res.get("tail", "")[-200:].replace("\n", " | "))
                        error_ids.add(res["id"]); print("!! " + run.last_error, flush=True)
                        if errs < st["max_errors"]:
                            pending.append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "errors": errs})
                        else:
                            st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "not verified ×%d" % errs,
                                                "failed_proof": res.get("failed_proof"), "tail": res.get("tail", "")[-400:]})
                elif res["status"] == "timeout" or job.get("force_split"):
                    st["wasted_s"] += res["solve_s"]
                    if res["attempt"] == 1 and not job.get("force_split"):
                        pending.append({"id": res["id"], "cube": res["cube"], "attempt": 2})
                        print("  cube %s: TIMEOUT %.0fs (第 1 次) → 重排, 時限加倍" % (res["id"], res["timeout"]), flush=True)
                    elif res["attempt"] == 3 and job.get("march_refuted"):
                        st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": 3, "why": "march refuted root but CDCL timeout at 4T"})
                        run.last_error = "cube %s: march 話 root refuted 但 4T 都解唔到, stuck" % res["id"]; print("!! " + run.last_error, flush=True)
                    elif depth < st["max_split"]:
                        try:
                            kids, refuted, root_ref = split_cube(run, st, base_text, nvars, nbase, job)
                        except Exception as e:
                            st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "split failed: %r" % e})
                            run.last_error = "cube %s: march_cu 拆件失敗 %r" % (res["id"], e); print("!! " + run.last_error, flush=True)
                            continue
                        if root_ref:
                            st["march_root_refuted"].append(res["id"])
                            pending.insert(0, {"id": res["id"], "cube": res["cube"], "attempt": 3, "march_refuted": True})
                            print("  cube %s: march_cu 話 root refuted (唔信佢) → 父 cube 以 4T 再跑 (attempt 3)" % res["id"], flush=True)
                        else:
                            st["split_events"] += 1; st["split_refuted"] += refuted
                            new = [{"id": "%s.%d" % (res["id"], k), "cube": c, "attempt": 1} for k, c in enumerate(kids)]
                            pending = new + pending
                            print("  cube %s: TIMEOUT %.0fs (第 %d 次) → march_cu 拆做 %d 個仔 cube (含 refuted leaves %d), 樹深 %d" % (
                                res["id"], res["timeout"], res["attempt"], len(kids), refuted, depth + 1), flush=True)
                    else:
                        st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": "max-split %d 仲 timeout" % st["max_split"]})
                        run.last_error = "cube %s 去到 max-split 仲 timeout" % res["id"]; print("!! " + run.last_error, flush=True)
                elif res["status"] == "SAT":
                    st["sat"] = res; st["running_at_save"] = [running[f] for f in running]; st["pending"] = pending; run.save(st, force=True)
                    run.status(st, running, {"status": "SAT!!"})
                    print("!! cube %s 判 SAT (model 逐子句核對: %s) —— 主張唔成立 (或者編碼有 bug); model 落咗 state.json, 停機" % (res["id"], res.get("model_checked")), flush=True)
                    for f in running:
                        f.cancel()
                    os.remove(lock); os._exit(10)
                else:                                       # rc 錯 / exception
                    errs = job.get("errors", 0) + 1
                    st["solver_errors"] += 1; st["wasted_s"] += res["solve_s"]
                    run.last_error = "cube %s: %s (第 %d 次錯) %s" % (res["id"], res["status"], errs, (res.get("tail", "") or "")[-200:].replace("\n", " | "))
                    error_ids.add(res["id"])
                    if errs < st["max_errors"]:
                        print("!! " + run.last_error + " → 同一時限重排", flush=True)
                        pending.append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "errors": errs})
                    else:
                        print("!! " + run.last_error + " → 錯夠 %d 次, 標 stuck" % errs, flush=True)
                        st["stuck"].append({"id": res["id"], "cube": res["cube"], "attempt": res["attempt"], "why": res["status"], "tail": (res.get("tail", "") or "")[-400:]})
            st["pending"] = pending; st["running_at_save"] = [running[f] for f in running]; st["wall_s"] = round(elapsed(), 1)
            run.save(st)
            if time.time() - last_prog >= a.progress:
                last_prog = time.time(); run.status(st, running)
                solve = [d["solve_s"] for d in st["done"].values()]
                print("[進度] %.0fs: 完成 %d, 跑緊 %d, pending %d (重排 %d), split %d, stuck %d, mean solve %.1fs, 浪費 %.0fs, %s, load %.1f" % (
                    elapsed(), len(st["done"]), len(running), len(pending), sum(1 for p in pending if p.get("attempt", 1) > 1 or p.get("errors")),
                    st["split_events"], len(st["stuck"]), statistics.mean(solve) if solve else 0, st["wasted_s"], disk_msg(run, st), os.getloadavg()[0]), flush=True)
    st["pending"] = pending; st["running_at_save"] = [running[f] for f in running]; st["wall_s"] = round(elapsed(), 1)
    run.save(st, force=True)
    if pending or running or st["stuck"]:
        if st["stuck"] and not pending and not running:
            status = "stuck"
        run.status(st, running, {"status": status})
        print("[stop] %s: 完成 %d, pending %d, stuck %d —— 用 --resume 續跑 (stuck 要人手睇: %s)" % (
            status, len(st["done"]), len(st["pending"]), len(st["stuck"]), [x["id"] for x in st["stuck"]][:10]), flush=True)
        os.remove(lock); return
    # cover
    print("[cover] 全部 %d 個 leaf UNSAT + VERIFIED; 出 cover 證書 (split %d 次, march refuted leaves 共 %d, root-refuted %d)" % (
        len(st["done"]), st["split_events"], st["split_refuted"], len(st["march_root_refuted"])), flush=True)
    cover, mode = cover_certificate(run, st, nvars, base)
    st["cover"] = cover; st["cover_mode"] = mode; run.save(st, force=True)
    assert mode is not None, "!! cover 證書出唔到 (兩個 mode 都唔係 UNSAT+VERIFIED)"
    aud = audit(run, st, base_text, nvars, nbase, a.audit_frac, a.seed)
    st["audit"] = aud; run.save(st, force=True)
    assert all(r["ok"] for r in aud), "!! 審計有 leaf 重做唔 VERIFIED: %s" % [r["id"] for r in aud if not r["ok"]]
    st["status"] = "certified"; st["wall_s"] = round(elapsed(), 1); run.save(st, force=True)
    bundle = {"claim": "base.cnf (sha %s) UNSAT" % st["base_sha"], "base_sha": st["base_sha"], "icnf_sha": st["icnf_sha"], "n_cubes0": st["n_cubes0"],
              "proof_dir": st["proof_dir"], "binary_proofs": st.get("binary", False), "solver_errors": st.get("solver_errors", 0), "stuck": st["stuck"],
              "tools": st.get("tools"), "leaves": len(st["done"]), "split_events": st["split_events"], "split_refuted": st["split_refuted"],
              "march_root_refuted": st["march_root_refuted"], "solver": st["solver"], "timeout": st["timeout"],
              "leaf_solve_cpu_s": round(sum(d["solve_s"] for d in st["done"].values()), 1), "leaf_verify_cpu_s": round(sum(d["verify_s"] for d in st["done"].values()), 1),
              "wasted_s": round(st["wasted_s"], 1), "leaf_proof_total_mb": round(sum(d["proof_bytes"] for d in st["done"].values()) / 1e6, 1),
              "max_leaf_solve_s": max(d["solve_s"] for d in st["done"].values()),
              "cover": cover, "cover_mode": mode, "audit": {"n": len(aud), "all_ok": all(r["ok"] for r in aud), "ids": [r["id"] for r in aud]},
              "wall_s": st["wall_s"], "leaf_list": [dict(id=k, **v) for k, v in sorted(st["done"].items())]}
    with open(os.path.join(out, "bundle.json"), "w") as f:
        json.dump(bundle, f, indent=1)
    run.status(st, {}, {"status": "certified"})
    print("[done] 證書 bundle: %d leaves (solver CPU %.0fs, 驗 CPU %.0fs, 浪費 %.0fs, 證明共 %.1f MB) + cover (%s) + 審計 %d/%d ok; wall %.0fs → %s/bundle.json" % (
        bundle["leaves"], bundle["leaf_solve_cpu_s"], bundle["leaf_verify_cpu_s"], bundle["wasted_s"], bundle["leaf_proof_total_mb"], mode, len(aud), len(aud), st["wall_s"], out), flush=True)
    os.remove(lock)

if __name__ == "__main__":
    main()
