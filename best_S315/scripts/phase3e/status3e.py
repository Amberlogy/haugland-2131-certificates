#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status3e.py —— Phase 3e 每 10 分鐘覆寫 status.md (手機可讀)
讀: ~/hadwiger/phase3e/{START.txt, STEP.txt}, runs/*/status.json (probe3e), 當前 campaign 嘅 cnc status.json, keep 目錄, 磁碟, runs/*/finalize_status.json
寫: ~/hadwiger/phase3e/status.md + Windows Desktop\\spindle\\phase3e\\status.md
用法: python3 status3e.py [--interval 600] [--once]
"""
import os, sys, json, time, argparse, glob

PH = "/home/user/hadwiger/phase3e"
WIN = ["/mnt/c/Users/user/Desktop/spindle/phase3e/status.md"]
SHM = "/dev/shm"
RUN_ID = "p3e1_step"
RECORD_G3P = 1441
PREV_G3P = 1591
TARGET_G2P_AMBER = 716

def df(path):
    try:
        st = os.statvfs(path); return st.f_bavail * st.f_frsize / 1e9
    except Exception:
        return None

def du(path, prefix=None):
    tot = 0
    try:
        for f in os.listdir(path):
            if prefix and not f.startswith(prefix):
                continue
            try:
                tot += os.path.getsize(os.path.join(path, f))
            except OSError:
                pass
    except OSError:
        pass
    return tot / 1e9

def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None

def tail(p, n=3):
    try:
        return [l.rstrip() for l in open(p, errors="ignore").read().splitlines() if l.strip()][-n:]
    except Exception:
        return []

def render():
    now = time.time(); start = None
    try:
        start = float(open(os.path.join(PH, "START.txt")).read().split("\n")[1])
    except Exception:
        pass
    step = "?"
    try:
        step = open(os.path.join(PH, "STEP.txt")).read().strip()
    except Exception:
        pass
    runs = sorted(glob.glob(os.path.join(PH, "runs", "*")))
    sts = [(os.path.basename(d), load(os.path.join(d, "status.json")), d) for d in runs]
    fin = [load(os.path.join(d, "finalize_status.json")) for d in runs]; fin = [f for f in fin if f]
    rec = any((st or {}).get("record_candidate") for _, st, _ in sts)
    confirmed = any((st or {}).get("record_candidate_confirmed") for _, st, _ in sts)
    vfail = any((st or {}).get("finalize_verify_all_ok") is False for _, st, _ in sts)
    best = None
    for _, st, _ in sts:
        if st and st.get("best"):
            best = st["best"]
    title = "# Phase 3e status (小步慢行: 每輪剪 20 粒, 796 → 716; 目標 |G₃′| < %d)" % RECORD_G3P
    if rec and confirmed:
        title = "# **RECORD_CANDIDATE** —— |G₃′| = %s < %d 已認證 + 獨立重驗全部通過; 唔再剪, 等 Amber (未公開 / 未寄信 / 未 push / 未上 Zenodo)" % ((best or {}).get("G3p_n"), RECORD_G3P)
    elif rec and vfail:
        title = "# **!! RECORD CANDIDATE BLOCKED** —— 到咗 |G₃′| = %s < %d 但獨立重驗唔過 (VERIFY_FAILED.md), 唔算數, 要人手睇" % ((best or {}).get("G3p_n"), RECORD_G3P)
    elif rec:
        title = "# **RECORD_CANDIDATE (候選, finalize 獨立重驗中)** —— probe3e 到咗 |G₃′| = %s < %d; 等全部 leaf 證明重驗 + cake_lpr + 封存" % ((best or {}).get("G3p_n"), RECORD_G3P)
    elif vfail:
        title = "# **!! 獨立重驗唔過** —— finalize3e verify all_ok=False (VERIFY_FAILED.md), 要人手睇"
    elif best:
        title = "# Phase 3e: 有進步 (|G₃′| = %s, 未到 %d)" % (best.get("G3p_n"), RECORD_G3P)
    elif fin and fin[-1].get("done"):
        title = "# Phase 3e status —— 完成 (%s); 報告 phase3e/phase3e_results.md; 冇背景任務" % fin[-1].get("finished")
    L = [title, "", "更新: %s (每 10 分鐘覆寫)" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "Phase 3e 用時 (由 launch 起): %s" % ("%.1f h" % ((now - start) / 3600) if start else "?"), "", "## 當前步驟", step, ""]
    dD, dC, dR, dS = df("/mnt/d"), df("/mnt/c"), df("/"), df(SHM)
    L += ["## 磁碟", "- D: 剩 %.0f GB (keep + 封存所在, 要 ≥ 300) | C: 剩 %.0f GB (要 ≥ 25) | WSL ext4 剩 %.0f GB | /dev/shm (證明暫存) 剩 %.1f GB, 暫存中 %.2f GB" % (
        dD or -1, dC or -1, dR or -1, dS or -1, du(os.path.join(SHM, RUN_ID))), ""]
    warn = []
    if dD is not None and dD < 300:
        warn.append("!! D: 剩餘 < 300 GB → probe3e 唔會開新一輪")
    if dC is not None and dC < 25:
        warn.append("!! C: 剩餘 < 25 GB")
    if dS is not None and dS < 2:
        warn.append("!! /dev/shm 剩 < 2 GB (證明暫存盤)")
    if warn:
        L += ["## 警告"] + ["- " + w for w in warn] + [""]
    L.append("## 小步慢行 (run ID 獨一)")
    found = False
    for rid, st, d in sts:
        if not st:
            L.append("- %s: (冇 status.json) log 尾: %s" % (rid, " | ".join(tail(os.path.join(d, "probe3e.log"), 2))[:300])); found = True; continue
        found = True
        age = (now - os.path.getmtime(os.path.join(d, "status.json"))) / 60
        cs = (st.get("current") or {}).get("cnc_status")
        if cs and os.path.exists(cs):
            age = min(age, (now - os.path.getmtime(cs)) / 60)
        seed = st.get("seed") or {}
        L.append("- **%s** (接力 %s %s: S_acc %s 粒 → |G₃′| %s): round %s/%s | **步幅 %s** (歷史 %s) | 而今 S_acc %s 粒 ⇒ |G₂′| %s, |G₃′| %s | 目標 |G₂′| ≤ %d (觸發線 %s) | 用時 %.2f h / %.0f h | **CPU %.1f / %.0f CPU-h** (剩 %.1f)%s%s%s" % (
            rid, seed.get("run_id"), seed.get("last_certified_tag"), seed.get("G2p_n") and (1066 - seed.get("G2p_n")), seed.get("G3p_n"),
            st.get("round_done"), st.get("rounds_max"), st.get("step"), [x.get("step") for x in (st.get("step_history") or [])],
            st.get("S_acc_size"), st.get("G2p_n"), st.get("G3p_n"), TARGET_G2P_AMBER, st.get("record_G2p"),
            (st.get("elapsed_s") or 0) / 3600, (st.get("total_cap_s") or 0) / 3600,
            st.get("cpu_h_used") or 0, st.get("cpu_cap_h") or 0, st.get("cpu_h_remaining") or 0,
            (" | **停: %s**" % st["stop_reason"]) if st.get("stop_reason") else "", (" | !! STALE %.0f 分鐘" % age) if (age > 15 and not st.get("stop_reason")) else "",
            (" | resume ×%d" % st["resumes"]) if st.get("resumes") else ""))
        if st.get("best"):
            b = st["best"]
            L.append("  - **最佳認證圖: round %s %s — |G₂′| %s 點 %s 邊, |G₃′| %s 點 %s 邊 (%s); 認證 l3 A+B %s / 5 色 %s**" % (
                b.get("round"), b.get("tag"), b.get("G2p_n"), b.get("G2p_m"), b.get("G3p_n"), b.get("G3p_m"),
                ("**< %d**" % RECORD_G3P) if (b.get("G3p_n") or 10 ** 9) < RECORD_G3P else "未到 %d (Phase 3c 係 %d)" % (RECORD_G3P, PREV_G3P),
                b.get("engine_b_run"), b.get("col5_ok")))
        ks = st.get("keep_stats") or {}
        L.append("  - 封存 (leaf 證明喺 D: %s): %s" % (st.get("keep_root"), ", ".join("%s: %d 檔 %.1f GB" % (t, v.get("n_files", 0), v.get("gb", 0)) for t, v in ks.items()) or "(未有 certified 證書)"))
        cur = st.get("current") or {}
        if cur and not st.get("stop_reason"):
            L.append("  - 當前嘗試 %s: 階段 %s, 剪 %s 粒, 開始 %s, 上限 %.2f h, keep-dir %s (暫存 %.2f GB, 已搬 %.1f GB)" % (
                cur.get("tag"), cur.get("stage"), cur.get("S_size"), cur.get("started"), (cur.get("cap_s") or 0) / 3600, cur.get("keep_dir"),
                du(os.path.join(SHM, RUN_ID), "cnc_%s_" % cur.get("tag")), du(cur.get("keep_dir") or "/nonexistent")))
            c = load(cur.get("cnc_status") or "")
            if c:
                cage = (now - os.path.getmtime(cur["cnc_status"])) / 60
                L.append("  - cnc2k: %s | cube 完成 %s / %s, 跑緊 %s, 重排 %s, split %s, stuck %s | 平均 %s s, 最大 %s s | 已用 %.2f h | 剩餘估計 %s | 未驗證明 %s GB | 錯誤 %s%s" % (
                    c.get("status", "running"), c.get("done"), c.get("total"), c.get("running"), c.get("retry"), c.get("split_events"), c.get("stuck"),
                    c.get("mean_cube_s"), c.get("max_cube_s"), (c.get("wall_s") or 0) / 3600, c.get("eta"), c.get("unverified_proof_gb"), c.get("last_error"),
                    (" | !! cnc status STALE %.0f 分鐘" % cage) if cage > 10 and c.get("status") in (None, "running") else ""))
        for r in st.get("rounds", []):
            L.append("  - **round %s** (步幅 %s): %s | 淨剪 %s ⇒ |G₂′| %s |G₃′| %s | %.2f h | B 大小 %s" % (
                r.get("round"), r.get("step"), r.get("status") or "跑緊", r.get("net_removed"), r.get("G2p_n"), r.get("G3p_n"),
                (r.get("wall_s") or 0) / 3600, r.get("B_sizes")))
            for x in r.get("attempts", []):
                L.append("    - %s: %s | 剪 %s 粒 → |G₂′| %s |G₃′| %s | %s cube, leaf %s, mean s+v %s s, 最長 %s s | %.2f h%s%s%s" % (
                    x.get("tag"), x.get("status"), x.get("removed"), x.get("G2p_n"), x.get("G3p_n"), x.get("n_cubes"), x.get("leaves"),
                    x.get("mean_sv_s"), x.get("max_solve_s"), (x.get("wall_s") or 0) / 3600,
                    (" (+延長 %.2f h)" % ((x.get("extended_s") or 0) / 3600)) if x.get("extended_s") else "",
                    (" | |B| = %s" % x.get("B_size")) if x.get("B_size") else "",
                    (" | 認證 l3 %s / 5 色 %s" % (x.get("l3_ok"), x.get("col5_ok"))) if x.get("status") == "certified" else ""))
        for b in st.get("B_sets", []):
            L.append("  - 擋路集 round %s %s (步幅 %s, |S| %s): |B| = %s, B = %s" % (
                b.get("round"), b.get("tag"), b.get("step"), b.get("S_size"), b.get("size"), b.get("B")))
    if not found:
        L.append("- 無")
    L.append("")
    for f in fin:
        L += ["## 收爐 (finalize3e)", "- %s" % f.get("stage"), "- 開始 %s%s" % (f.get("started"), (", 完 %s" % f["finished"]) if f.get("finished") else "")]
        for k in ("final", "verify_final", "crosscheck", "col5", "verify_all_ok", "record_candidate_confirmed", "archive", "stage", "report", "facts", "decision", "memory"):
            if f.get(k) is not None:
                L.append("  - %s: %s" % (k, str(f[k])[:300]))
        L.append("")
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--interval", type=float, default=600); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    while True:
        try:
            txt = render()
        except Exception:
            import traceback
            txt = "# Phase 3e status —— status3e render 出錯 (%s)\n\n```\n%s\n```\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()[-3000:])
        for dst in [os.path.join(PH, "status.md")] + WIN:
            try:
                tmp = dst + ".tmp"; open(tmp, "w").write(txt); os.replace(tmp, dst)
            except Exception as e:
                sys.stderr.write("write %s: %s\n" % (dst, e))
        if a.once:
            print(txt); break
        time.sleep(a.interval)

if __name__ == "__main__":
    main()
