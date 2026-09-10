#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s60_full.py —— 可選 (戰役完之後, ≤ 3 h): 補封存 Proposition 2 —— 對 G₁ − S₆₀ (Phase 3 round2, |G₃′| = 1891) 重新生成 L1′ 證書並保留全部 leaf proofs.
  用 Phase 3 round2 嘅 base.cnf (sha 92baa01e…) + cubes_d14.icnf (sha ee90368b…) 原檔 (唔重建), cnc2k --keep-dir → /mnt/d/hadwiger/phase3c/keep/S60_full;
  certified → verify_final.py --skip-l3 獨立重驗 → 封存: leaf 證明 rename → /mnt/d/hadwiger/release_v1_1_staging/reduction/S60_full/leaf_proofs/;
  細檔 (base/bundle/cover/ledger/state + Phase 3 round2 l3/ L2′/L3′ 檔 + S60_README.md) → ~/hadwiger/release_v1_1_staging/reduction/S60_full/; 重算 reduction/SHA256SUMS; 鏡像 Windows.
  超 --cap (預設 3 h) 未完 → 記 status budget-stop, 刪 keep 目錄, 唔封存 (Proposition 2 仍係「可重跑」).
用法: python3 s60_full.py [--cap 10800] [--workers 14] [--out ~/hadwiger/phase3c/s60_full]
輸出: <out>/s60_full.json (finalize3c.py --append-s60 讀)
"""
import sys, os, json, time, argparse, subprocess, shutil, hashlib, glob, signal
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH3 = os.path.expanduser("~/hadwiger/phase3"); PH3C = os.path.expanduser("~/hadwiger/phase3c"); PH2B = os.path.expanduser("~/hadwiger/phase2b")
sys.path.insert(0, PH3C)
from probe3c import repair_keep_dir      # 同 probe3c 一樣嘅搬失敗修補 (leaf + audit)

def write_json(p, obj):
    tmp = p + ".tmp"; open(tmp, "w", encoding="utf-8").write(json.dumps(obj, indent=1, ensure_ascii=False)); os.replace(tmp, p)
STAGE = os.path.expanduser("~/hadwiger/release_v1_1_staging/reduction"); STAGE_D = "/mnt/d/hadwiger/release_v1_1_staging/reduction/S60_full"
WIN_STAGE = "/mnt/c/Users/user/Desktop/spindle/release_v1_1_staging/reduction"
ROUND2 = os.path.join(PH3, "probe", "round2")
BASE_SHA = "92baa01e7232aecbeaaa92e7eb3464a563eadd4280b1b596eaf43ba7480585a9"; ICNF_SHA = "ee90368b61c4008d70638d5a116f11988ad189245e968bfede34af5dd7e9fce8"
PY = sys.executable

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def cp(src, dst_dir, name=None):
    if not os.path.isfile(src):
        return None
    os.makedirs(dst_dir, exist_ok=True); d = os.path.join(dst_dir, name or os.path.basename(src))
    if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(src) or sha(d) != sha(src):
        shutil.copyfile(src, d)
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=3 * 3600); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--out", default=os.path.join(PH3C, "s60_full"))
    ap.add_argument("--keep-dir", default="/mnt/d/hadwiger/phase3c/keep/S60_full"); ap.add_argument("--proof-dir", default="/dev/shm/s60_full")
    a = ap.parse_args()
    out = os.path.abspath(os.path.expanduser(a.out)); os.makedirs(out, exist_ok=True); os.makedirs(a.proof_dir, exist_ok=True)
    tag = "S60_full"; cdir = os.path.join(out, "cnc_" + tag); T0 = time.time()
    lp0 = os.path.join(STAGE_D, "leaf_proofs")
    if not os.path.isdir(a.keep_dir) and os.path.isdir(lp0):                       # 審查 #7: rename 之後再跑 → 用封存位置 (幂等)
        a.keep_dir = lp0; log("keep 目錄已 rename 入 %s, 用返佢" % lp0)
    res = {"tag": tag, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cap_s": a.cap, "source": ROUND2, "keep_dir": a.keep_dir}
    def step(m):
        try:
            open(os.path.join(PH3C, "STEP.txt"), "w").write("Phase 3c 可選補封存 Proposition 2 (s60_full): " + m)
        except Exception:
            pass
        log(m)
    # 原檔 + sha 對數
    base = cp(os.path.join(ROUND2, "base.cnf"), out); bjs = cp(os.path.join(ROUND2, "base.json"), out); icnf = cp(os.path.join(ROUND2, "cubes_d14.icnf"), out); cp(os.path.join(ROUND2, "march.log"), out)
    res["base_sha"] = sha(base); res["icnf_sha"] = sha(icnf); res["base_sha_matches_phase3"] = (res["base_sha"] == BASE_SHA and json.load(open(bjs))["cnf_sha256"] == BASE_SHA); res["icnf_sha_matches_phase3"] = (res["icnf_sha"] == ICNF_SHA)
    assert res["base_sha_matches_phase3"] and res["icnf_sha_matches_phase3"], "Phase 3 round2 base/icnf sha 對唔上 (%s / %s)" % (res["base_sha"][:16], res["icnf_sha"][:16])
    bj = json.load(open(bjs)); res["S60"] = bj["removed"]; res["G1p_n"] = bj["n_remaining"]; res["G1p_m"] = bj["n_edges"]
    # cnc2k (resume 如有 state)
    resumed = os.path.exists(os.path.join(cdir, "state.json"))
    if resumed:
        st_old = json.load(open(os.path.join(cdir, "state.json")))
        if st_old.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json")):
            log("cnc 已 certified, 唔重跑")
        else:
            if os.path.exists(os.path.join(cdir, "lock")):
                os.remove(os.path.join(cdir, "lock"))
            argv = [PY, os.path.join(PH3C, "cnc2k.py"), "--resume", "--out", cdir, "--workers", str(a.workers), "--time-budget", str(int(st_old["wall_s"] + a.cap)), "--progress", "120", "--keep-dir", a.keep_dir]
    else:
        argv = [PY, os.path.join(PH3C, "cnc2k.py"), "--cnf", base, "--icnf", icnf, "--out", cdir, "--workers", str(a.workers), "--timeout", "600", "--solver", "kissat", "--proof-dir", a.proof_dir, "--binary",
                "--time-budget", str(int(a.cap)), "--split-depth", "3", "--max-split", "4", "--audit-frac", "0.05", "--progress", "120", "--keep-dir", a.keep_dir]
    if not (resumed and st_old.get("status") == "certified"):
        step("cnc2k G₁−S₆₀ (16384 cube, 14 workers, keep-dir %s, cap %.1f h)" % (a.keep_dir, a.cap / 3600))
        t0 = time.time(); killed = False
        with open(os.path.join(out, "cnc.log"), "a") as lf:
            p = subprocess.Popen(argv, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
            while True:
                try:
                    rc = p.wait(timeout=30); break
                except subprocess.TimeoutExpired:
                    if time.time() - t0 > a.cap + 900:
                        killed = True; log("!! 超硬上限, 硬殺")
                        try:
                            os.killpg(p.pid, signal.SIGTERM); time.sleep(5); os.killpg(p.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        rc = p.wait(); break
        subprocess.run(["pkill", "-x", "kissat"], capture_output=True); subprocess.run(["pkill", "-x", "drat-trim"], capture_output=True)
        res["cnc_rc"] = rc; res["hard_killed"] = killed
        for f in os.listdir(a.proof_dir):
            fp = os.path.join(a.proof_dir, f)
            if os.path.isfile(fp):
                os.remove(fp)
    st = json.load(open(os.path.join(cdir, "state.json"))) if os.path.exists(os.path.join(cdir, "state.json")) else {}
    done = st.get("done", {}); solve = [x["solve_s"] for x in done.values()]; ver = [x.get("verify_s") or 0 for x in done.values()]
    res.update({"n_cubes": st.get("n_cubes0"), "leaves": len(done), "pending": len(st.get("pending", [])) + len(st.get("running_at_save", [])), "stuck": len(st.get("stuck", [])), "wall_s": round(time.time() - T0, 1),
                "mean_sv_s": round((sum(solve) + sum(ver)) / len(solve), 3) if solve else None, "keep_errors": st.get("keep_errors", 0), "kept_leaves": sum(1 for d in done.values() if d.get("kept"))})
    if st.get("status") == "certified" and os.path.exists(os.path.join(cdir, "bundle.json")):
        cb = json.load(open(os.path.join(cdir, "bundle.json")))
        res["status"] = "certified"; res["cover_verified"] = bool(cb["cover"][cb["cover_mode"]].get("verified")); res["audit"] = {"n": cb["audit"]["n"], "all_ok": cb["audit"]["all_ok"]}; res["proof_total_mb"] = cb["leaf_proof_total_mb"]
        assert cb["base_sha"] == BASE_SHA and cb["leaves"] == len(done)
        res["kept_leaves"] = sum(1 for d in done.values() if d.get("kept") and os.path.exists(d["kept"]))
        if res["kept_leaves"] != len(done) or cb.get("audit_keep_errors") or cb.get("kept_audit") != cb["audit"]["n"]:
            step("keep-repair (leaf %d/%d, audit %s/%s)" % (res["kept_leaves"], len(done), cb.get("kept_audit"), cb["audit"]["n"]))
            rep = repair_keep_dir(cdir, a.keep_dir, st, a.proof_dir, 600, log)
            res["keep_repair"] = {"repaired": len(rep["repaired"]), "failed": rep["failed"][:20], "kept_after": rep["kept_after"], "kept_audit_after": rep["kept_audit_after"]}
            res["kept_leaves"] = rep["kept_after"]
            if rep["failed"]:
                res["status"] = "certified-keep-incomplete"; log("!! %d 個證明修唔到 —— 唔封存做「全套」, keep 目錄保留, 人手睇" % len(rep["failed"]))
    elif st.get("sat"):
        res["status"] = "SAT?!"; log("!! G₁−S₆₀ 判 SAT —— 同 Phase 3 round2 certified 矛盾, 要人手睇 (cube %s)" % st["sat"]["id"])
    else:
        res["status"] = "budget-stop" if not res.get("hard_killed") else "hard-killed"
    log("cnc2k: %s —— leaf %s/%s, mean s+v %s, wall %.2f h, kept %s, keep_errors %s" % (res["status"], res["leaves"], res["n_cubes"], res["mean_sv_s"], res["wall_s"] / 3600, res["kept_leaves"], res["keep_errors"]))
    if res["status"] == "certified":
        step("verify_final (--skip-l3) 獨立重驗 %d 個 leaf 證明" % len(done))
        rc = subprocess.call([PY, os.path.join(PH3C, "verify_final.py"), "--attempt-dir", out, "--tag", tag, "--keep-dir", a.keep_dir, "--workers", str(a.workers), "--skip-l3"], stdout=open(os.path.join(out, "verify_final.log"), "a"), stderr=subprocess.STDOUT)
        vf = os.path.join(out, "verify_final.json"); v = json.load(open(vf)) if os.path.exists(vf) else {"all_ok": False}
        res["verify_final"] = {k: v.get(k) for k in ("all_ok", "base_sha_consistent", "leaf_count_consistent", "leaf_ids_are_all_root_cubes", "t_s")} | {"leaf_reverify": {k: x for k, x in (v.get("leaf_reverify") or {}).items() if k != "bad"}, "cover": (v.get("cover_reverify") or {}).get("ok"), "audit_ok": (v.get("audit_reverify") or {}).get("ok"), "rc": rc}
        if v.get("all_ok"):
            step("封存 → %s (leaf 證明) + %s/S60_full (細檔)" % (STAGE_D, STAGE))
            os.makedirs(STAGE_D, exist_ok=True); lp = os.path.join(STAGE_D, "leaf_proofs")
            if os.path.isdir(a.keep_dir) and not os.path.isdir(lp):
                os.rename(a.keep_dir, lp)
            SD = os.path.join(STAGE, "S60_full")
            for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "verify_final.json", "verify_final.log"):
                cp(os.path.join(out, f), SD)
            for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "ledger.csv", "state.json", "status.json", "keep_repair.json"):
                cp(os.path.join(cdir, f), os.path.join(SD, "cnc"))
            for f in glob.glob(os.path.join(ROUND2, "l3", "*")):
                cp(f, os.path.join(SD, "l3_phase3_round2"))
            cp(os.path.join(ROUND2, "l3prime.log"), SD)
            idx = {x["id"]: {"file": "leaf_proofs/cnc_%s_%s.drat" % (tag, x["id"]), "proof_sha256": x["proof_sha"], "proof_bytes": x["proof_bytes"], "cnf_sha256": x["cnf_sha"], "cube": x["cube"]} for x in cb["leaf_list"]}
            write_json(os.path.join(SD, "LEAF_INDEX.json"), {"tag": tag, "base_sha256": BASE_SHA, "n_leaves": len(idx), "leaf_proofs_dir": lp, "leaves": idx})
            # sha of leaf proofs (D:) → 獨立 SHA256SUMS 喺 D: 目錄
            from concurrent.futures import ThreadPoolExecutor
            files = sorted(os.path.relpath(os.path.join(r, f), STAGE_D) for r, _, fs in os.walk(STAGE_D) for f in fs if f != "SHA256SUMS")
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                hs = list(ex.map(lambda rel: sha(os.path.join(STAGE_D, rel)), files))
            open(os.path.join(STAGE_D, "SHA256SUMS"), "w").write("".join("%s  %s\n" % (h, r) for h, r in zip(hs, files)))
            chk = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=STAGE_D, capture_output=True, text=True); res["leaf_dir_check_rc"] = chk.returncode; res["leaf_files"] = len(files)
            cp(os.path.join(STAGE_D, "SHA256SUMS"), SD, "SHA256SUMS.leaf_proofs")
            R = ["# S60_full — Proposition 2 certificate with all leaf proofs archived (NOT released)", "",
                 "Regenerated %s by `scripts/phase3c/s60_full.py` from the Phase 3 round2 inputs (identical files: `base.cnf` sha `%s`, `cubes_d14.icnf` sha `%s`), using `cnc2k.py --keep-dir` (v1.0 `cnc2.py` + proof retention). Statement: `base.cnf` = 4-colouring CNF of G1 − S60 (680 vertices, %d edges) + 8 clauses col(A)=col(B) is UNSAT ⇔ G1 − S60 has the pair property (see `../REDUCTION_README.md` §A). With `l3_phase3_round2/` (L2′/L3′ from Phase 3, unchanged) this certifies that G3′ (1891 vertices) is not 4-colourable — Proposition 2 of the note." % (time.strftime("%Y-%m-%d %H:%M:%S"), BASE_SHA, ICNF_SHA, bj["n_edges"]), "",
                 "* leaves: %d, all kissat UNSAT + drat-trim VERIFIED; cover certificate `cnc/cover_pure.drat` VERIFIED; audit %d/%d re-solved from scratch." % (len(done), cb["audit"]["n"], cb["audit"]["n"]),
                 "* **Leaf proofs (binary DRAT, %.1f GB): `%s/leaf_proofs/` on D: (Windows `D:\\hadwiger\\release_v1_1_staging\\reduction\\S60_full\\leaf_proofs\\`), sha256 per file in `SHA256SUMS.leaf_proofs` (copy here) and `LEAF_INDEX.json`.**" % (cb["leaf_proof_total_mb"] / 1e3, STAGE_D),
                 "* Independent re-verification from disk (`verify_final.json`): all_ok = %s (%s/%s leaf proofs drat-trim VERIFIED with sha match, cover OK, audit proofs OK)." % (v.get("all_ok"), (v.get("leaf_reverify") or {}).get("ok"), (v.get("leaf_reverify") or {}).get("n")),
                 "* Re-check: `python3 ../scripts/phase3c/verify_final.py --attempt-dir <this dir with cnc renamed to cnc_S60_full> --tag S60_full --keep-dir %s/leaf_proofs --skip-l3`, or per leaf: rebuild base.cnf + cube unit clauses, `drat-trim cube.cnf leaf_proofs/cnc_S60_full_<id>.drat`." % STAGE_D]
            open(os.path.join(SD, "S60_README.md"), "w").write("\n".join(R) + "\n")
            # reduction/SHA256SUMS 重算 + 鏡像
            files = sorted(os.path.relpath(os.path.join(r, f), STAGE) for r, _, fs in os.walk(STAGE) for f in fs if f not in ("SHA256SUMS", "SHA256SUMS.small"))
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                hs = list(ex.map(lambda rel: sha(os.path.join(STAGE, rel)), files))
            open(os.path.join(STAGE, "SHA256SUMS"), "w").write("".join("%s  %s\n" % (h, r) for h, r in zip(hs, files)))
            chk = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=STAGE, capture_output=True, text=True)
            res["stage_dir"] = SD; res["final_dir"] = STAGE_D; res["stage_check_rc"] = chk.returncode
            for r_, _, fs in os.walk(SD):
                for f in fs:
                    rel = os.path.relpath(os.path.join(r_, f), STAGE); cp(os.path.join(r_, f), os.path.join(WIN_STAGE, os.path.dirname(rel)))
            cp(os.path.join(STAGE, "SHA256SUMS"), WIN_STAGE)
            log("封存完: %s (%d 檔, sha256sum -c rc=%d) + %s (reduction rc=%d)" % (STAGE_D, res["leaf_files"], res["leaf_dir_check_rc"], SD, chk.returncode))
        else:
            res["status"] = "certified-but-verify-failed"; log("!! verify_final 唔過, 唔封存")
    if res["status"] == "SAT?!" and os.path.isdir(a.keep_dir):                       # 審查 #7/#22: 只有 SAT?! (證明無意義) 先刪; budget-stop / verify-failed / keep-incomplete 全部保留 (可續跑 / 證據)
        ks = sum(1 for f in os.listdir(a.keep_dir) if f.endswith(".drat"))
        shutil.rmtree(a.keep_dir, ignore_errors=True); res["keep_deleted"] = ks; log("SAT?!, 刪 keep 目錄 (%d 檔)" % ks)
    res["keep_dir_retained"] = a.keep_dir if os.path.isdir(a.keep_dir) else None
    res["resumable"] = res["status"] in ("budget-stop", "hard-killed")
    if res["resumable"]:
        log("未完 (%s): cnc 狀態 + keep 目錄保留; 人手決定先續跑 (python3 s60_full.py 會 cnc2k --resume; Amber 上限 3 h 已用)" % res["status"])
    res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); res["t_s"] = round(time.time() - T0, 1)
    write_json(os.path.join(out, "s60_full.json"), res)
    step("完 (%s)" % res["status"]); log("S60_FULL DONE: %s" % res["status"])

if __name__ == "__main__":
    main()
