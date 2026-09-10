#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_cnc2k.py —— 由 phase2b/cnc2.py (v1.0 發表版, sha abbda106…) 機械生成 phase3c/cnc2k.py: 只加 --keep-dir (leaf 證明 VERIFIED 後保留去 D:, sha 核對).
  每個 patch 都 assert 錨點唯一存在; 生成後 ast.parse. 記錄差異 → cnc2k.diff (供報告/審查).
用法: python make_cnc2k.py [--src ../phase2b/cnc2.py] [--dst cnc2k.py]
"""
import io, os, sys, ast, argparse, difflib, hashlib

CNC2_SHA = "abbda1068e43237a4347eac97a2ef597d20377149186f4b4111abac3061b1d9d"

def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--src", default=os.path.join(here, "..", "phase2b", "cnc2.py")); ap.add_argument("--dst", default=os.path.join(here, "cnc2k.py"))
    a = ap.parse_args()
    raw = io.open(a.src, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == CNC2_SHA, "cnc2.py sha 唔係 v1.0 版本"
    s = raw.decode("utf-8").replace("\r\n", "\n"); orig = s
    def rep(old, new):
        nonlocal s
        assert s.count(old) == 1, "錨點唔唯一/唔存在: %r" % old[:80]
        s = s.replace(old, new, 1)
    rep('cnc2.py —— Step 4: cube-and-conquer 戰役 (march_cu cube 檔 + 逐 cube solver → 證明 → 檢查器 VERIFIED → 記 sha/用時 → 刪證明檔)  v2 (審核後)',
        'cnc2k.py —— Phase 3c 變種 (k = keep): 由 phase2b/cnc2.py v2 (v1.0 發表版) 經 make_cnc2k.py 機械生成, 只加 --keep-dir DIR:\n'
        '  每個 leaf 證明經檢查器 VERIFIED 之後唔刪, 而係複製去 DIR (sha256 逐 byte 核對, 重試 3 次) 再刪源檔; 審計證明入 DIR/audit/.\n'
        '  差異: keep_proof() 助手, solve_cube()/audit() 嘅 verified 分支, st["done"][id]["kept"], bundle.json 多 keep_* 欄, --keep-dir 參數 (resume 唔准中途換目錄).\n'
        '  其餘 (cube 邏輯 / timeout 政策 / cover / 審計 / 磁碟紀律 / resume / SAT 處理) 一字不改. 差異檔: cnc2k.diff\n\n'
        '原 cnc2.py 說明:\ncnc2.py —— Step 4: cube-and-conquer 戰役 (march_cu cube 檔 + 逐 cube solver → 證明 → 檢查器 VERIFIED → 記 sha/用時 → 刪證明檔)  v2 (審核後)')
    anchor = 'def free_gb(path):\n    st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9\n'
    rep(anchor, anchor + '''
KEEP_RETRIES = 3

def keep_proof(proof, keep_dir, want_sha):
    """Phase 3c: 將已 VERIFIED 嘅證明檔複製去 keep_dir (通常係 /mnt/d, 9p), sha256 逐 byte 核對, 錯就重試; 成功先刪源檔 (由 caller 嘅 finally 刪).
    回傳 (kept_path 或 None, error 字串或 None). 唔 raise."""
    os.makedirs(keep_dir, exist_ok=True)
    dst = os.path.join(keep_dir, os.path.basename(proof)); err = None; tmp = dst + ".part"
    for i in range(KEEP_RETRIES):
        try:
            shutil.copyfile(proof, tmp)
            got = sha(tmp)
            if got != want_sha:
                err = "keep sha mismatch (try %d): %s != %s" % (i + 1, got[:16], want_sha[:16]); os.remove(tmp); time.sleep(2); continue
            os.replace(tmp, dst)
            return dst, None
        except Exception as e:
            err = "keep copy failed (try %d): %r" % (i + 1, e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            time.sleep(2)
    return None, err
''')
    rep('''            if res["verified"]:
                os.remove(cnf)      # cube CNF 可由 base + cube 重建 (writer deterministic), 留 sha; 審計會重建並核對 sha
            else:''',
        '''            if res["verified"]:
                os.remove(cnf)      # cube CNF 可由 base + cube 重建 (writer deterministic), 留 sha; 審計會重建並核對 sha
                if st.get("keep_dir"):                                   # Phase 3c: 保留 leaf 證明 (複製去 D:, sha 核對); 源檔由 finally 刪
                    kept, kerr = keep_proof(proof, st["keep_dir"], res["proof_sha"])
                    if kept:
                        res["kept"] = kept
                    else:
                        res["keep_error"] = kerr
            else:''')
    rep('''                    st["done"][res["id"]] = {k: res[k] for k in ("cube", "attempt", "timeout", "solve_s", "conflicts", "proof_bytes", "proof_lines",
                                                                 "proof_sha", "cnf_sha", "checker", "checker_rc", "verify_s")}''',
        '''                    st["done"][res["id"]] = {k: res[k] for k in ("cube", "attempt", "timeout", "solve_s", "conflicts", "proof_bytes", "proof_lines",
                                                                 "proof_sha", "cnf_sha", "checker", "checker_rc", "verify_s")}
                    if st.get("keep_dir"):                               # Phase 3c: 記低證明檔搬去邊 / 搬失敗 (唔影響 leaf 嘅 VERIFIED 狀態, 只影響封存完整性)
                        st["done"][res["id"]]["kept"] = res.get("kept")
                        if res.get("keep_error"):
                            st["done"][res["id"]]["keep_error"] = res["keep_error"]; st["keep_errors"] = st.get("keep_errors", 0) + 1
                            run.last_error = "leaf %s VERIFIED 但證明搬去 keep-dir 失敗: %s" % (res["id"], res["keep_error"]); print("!! " + run.last_error, flush=True)''')
    rep('''            if rec["rc"] == 20:
                rec.update(check_proof("drat", cnf, proof)); rec["proof_bytes"] = os.path.getsize(proof)
            rec["ok"] = bool(rec["cnf_sha_match"] and rec["rc"] == 20 and rec.get("verified", False))''',
        '''            if rec["rc"] == 20:
                rec.update(check_proof("drat", cnf, proof)); rec["proof_bytes"] = os.path.getsize(proof)
            rec["ok"] = bool(rec["cnf_sha_match"] and rec["rc"] == 20 and rec.get("verified", False))
            if rec["ok"] and st.get("keep_dir"):                          # Phase 3c: 審計證明亦保留 (DIR/audit/), 令 5% 審計可以獨立重驗
                rec["proof_sha"] = sha(proof)
                kept, kerr = keep_proof(proof, os.path.join(st["keep_dir"], "audit"), rec["proof_sha"])
                if kept:
                    rec["kept"] = kept
                else:
                    rec["keep_error"] = kerr''')
    rep('''def disk_ok(run, st):
    pd = st["proof_dir"]
    if du_prefix_gb(pd, run.tag + "_") > DISK_UNVERIFIED_GB_MAX:
        return False
''',
        '''DISK_PD_MIN_GB = 4.0     # Phase 3c: 證明暫存目錄 (/dev/shm 16 GB RAM 盤) 剩餘 < 4 GB 就唔派新 cube (審查 #9; 磁碟紀律, 唔郁 cube/驗證邏輯)

def disk_ok(run, st):
    pd = st["proof_dir"]
    if du_prefix_gb(pd, run.tag + "_") > DISK_UNVERIFIED_GB_MAX:
        return False
    try:
        if free_gb(pd) < DISK_PD_MIN_GB:
            return False
    except OSError:
        return False
''')
    rep('''    ap.add_argument("--max-errors", type=int, default=3); ap.add_argument("--requeue-stuck", action="store_true")
    a = ap.parse_args()''',
        '''    ap.add_argument("--max-errors", type=int, default=3); ap.add_argument("--requeue-stuck", action="store_true")
    ap.add_argument("--keep-dir", default=None, help="Phase 3c: 保留每個 VERIFIED leaf 證明 (複製去呢個目錄, sha 核對); 審計證明入 DIR/audit/")
    a = ap.parse_args()''')
    rep('''              "binary": a.binary, "max_errors": a.max_errors, "tools": tool_info(), "run_tag": run.tag,''',
        '''              "binary": a.binary, "max_errors": a.max_errors, "tools": tool_info(), "run_tag": run.tag,
              "keep_dir": (os.path.abspath(os.path.expanduser(a.keep_dir)) if a.keep_dir else None), "keep_errors": 0,''')
    rep('''        st["workers"] = a.workers; st["max_errors"] = a.max_errors
        for k, v in (("timeout", a.timeout), ("max_split", a.max_split), ("cover_timeout", a.cover_timeout)):
            if v is not None:
                st[k] = v''',
        '''        st["workers"] = a.workers; st["max_errors"] = a.max_errors
        for k, v in (("timeout", a.timeout), ("max_split", a.max_split), ("cover_timeout", a.cover_timeout)):
            if v is not None:
                st[k] = v
        if a.keep_dir and st.get("keep_dir") and os.path.abspath(os.path.expanduser(a.keep_dir)) != st["keep_dir"]:
            sys.exit("!! resume: --keep-dir %s != state.json keep_dir %s (唔准中途換目錄)" % (a.keep_dir, st["keep_dir"]))
        if a.keep_dir and not st.get("keep_dir"):
            st["keep_dir"] = os.path.abspath(os.path.expanduser(a.keep_dir)); st.setdefault("keep_errors", 0)''')
    rep('''        print("[start] base %s (sha %s): %d 變量 %d 子句; %d 個 cube (sha %s); solver %s%s, timeout %.0fs, workers %d, split-depth %d, proof-dir %s" % (
            a.cnf, st["base_sha"][:16], nvars, len(base), len(cubes), st["icnf_sha"][:16], a.solver, " (binary)" if a.binary else "", st["timeout"],
            a.workers, a.split_depth, pd), flush=True)''',
        '''        print("[start] base %s (sha %s): %d 變量 %d 子句; %d 個 cube (sha %s); solver %s%s, timeout %.0fs, workers %d, split-depth %d, proof-dir %s%s" % (
            a.cnf, st["base_sha"][:16], nvars, len(base), len(cubes), st["icnf_sha"][:16], a.solver, " (binary)" if a.binary else "", st["timeout"],
            a.workers, a.split_depth, pd, (", keep-dir %s (leaf 證明 VERIFIED 後保留)" % st["keep_dir"]) if st.get("keep_dir") else ""), flush=True)''')
    rep('''              "wall_s": st["wall_s"], "leaf_list": [dict(id=k, **v) for k, v in sorted(st["done"].items())]}''',
        '''              "wall_s": st["wall_s"], "leaf_list": [dict(id=k, **v) for k, v in sorted(st["done"].items())],
              "keep_dir": st.get("keep_dir"), "kept_leaves": sum(1 for d in st["done"].values() if d.get("kept")), "keep_errors": st.get("keep_errors", 0),
              "keep_error_ids": [k for k, d in st["done"].items() if d.get("keep_error")],
              "kept_audit": sum(1 for r in aud if r.get("kept")), "audit_keep_errors": [r["id"] for r in aud if r.get("keep_error")]}''')
    rep('''    print("[done] 證書 bundle: %d leaves (solver CPU %.0fs, 驗 CPU %.0fs, 浪費 %.0fs, 證明共 %.1f MB) + cover (%s) + 審計 %d/%d ok; wall %.0fs → %s/bundle.json" % (
        bundle["leaves"], bundle["leaf_solve_cpu_s"], bundle["leaf_verify_cpu_s"], bundle["wasted_s"], bundle["leaf_proof_total_mb"], mode, len(aud), len(aud), st["wall_s"], out), flush=True)''',
        '''    print("[done] 證書 bundle: %d leaves (solver CPU %.0fs, 驗 CPU %.0fs, 浪費 %.0fs, 證明共 %.1f MB) + cover (%s) + 審計 %d/%d ok; wall %.0fs → %s/bundle.json%s" % (
        bundle["leaves"], bundle["leaf_solve_cpu_s"], bundle["leaf_verify_cpu_s"], bundle["wasted_s"], bundle["leaf_proof_total_mb"], mode, len(aud), len(aud), st["wall_s"], out,
        ("; keep-dir %s: leaf 證明保留 %d/%d (搬失敗 %d), 審計證明保留 %d/%d" % (bundle["keep_dir"], bundle["kept_leaves"], bundle["leaves"], bundle["keep_errors"], bundle["kept_audit"], len(aud))) if bundle["keep_dir"] else ""), flush=True)''')
    ast.parse(s)
    io.open(a.dst, "w", encoding="utf-8", newline="\n").write(s)
    diff = "".join(difflib.unified_diff(orig.splitlines(True), s.splitlines(True), "phase2b/cnc2.py", "phase3c/cnc2k.py", n=2))
    io.open(os.path.join(os.path.dirname(a.dst), "cnc2k.diff"), "w", encoding="utf-8", newline="\n").write(diff)
    print("[make_cnc2k] %s → %s: %d → %d bytes, diff %d 行, sha %s" % (a.src, a.dst, len(orig), len(s), diff.count("\n"), hashlib.sha256(s.encode()).hexdigest()[:16]))

if __name__ == "__main__":
    main()
