#!/bin/bash
# Phase 3e selftest (開跑前必過; 唔好喺真 run 跑緊嗰陣行 —— 會覆寫 phase3e/STEP.txt):
#  1. 全部 .py 編譯 + .sh 語法
#  2. 迷你戰役 (PHP(7,6) UNSAT, march d=3): cnc2k --keep-dir → --time-budget 0 budget-stop → --resume 續 → certified (無損續跑),
#     leaf 證明 sha **同 byte 大細**都要一致 → verify_final --skip-l3 → crosscheck3d (cake_lpr + lrat-check)
#     → 毒藥 A (斬爛證明) / 毒藥 B (改爛 state.json 嘅 proof_sha) 都要唔過 → 還原要過 → resume 換 keep-dir 要拒絕
#  3. extend_decision 純函數 (probe3e 直接繼承 probe3d 嗰個): Phase 3c r10a 真數 + 五個唔延長個案
#  4. probe3e --dry-run: seed = Phase 3c r09a (S_acc 270), 步幅 20 ⇒ |S| = 290 = 270 + ordering[270:290], |G₂′| 776, |G₃′| 1551;
#     輪上限 21600 s; state.json **唔准**有 excluded_next / perma_excluded / excluded 呢啲全域累積器
#  5. 排除集逐輪重置 + 步幅持久化: 假造 round 1 = blocked (步幅已減半做 10) → --resume --ack-operator --dry-run →
#     round 2 要用步幅 10, excluded_this_round 要係空, 上一輪擋路嘅點要**返返**候選池
#  6. 三個預算閘門 (CPU-h / wall / 輪數) 各自要企得住
#  7. --resume 冇 --ack-operator 要拒絕 needs_operator; 加咗就要行到
#  8. finalize3e --dry-run (冇 best) → 報告 / facts / DECISION / MEMORY 全部寫去 dryrun 檔, 真檔一個字都唔准郁
#  9. finalize3e 有 best 嘅**報告格式**路徑 (直接叫 report/facts/decision/memory, 唔跑重驗): 每輪帳表 + 雷區密度分析 + g2shrink3e.rounds/.B_analysis
# 10. status3e --once
# 11. 真實 smoke (可選, --smoke): 真 G2 剪 290 粒, cap 240 s → budget-stop → 唔延長 (eta 太大) → **keep 目錄要保留** (cnc2k --resume 嘅本錢) → needs_operator
set -u
PY=/home/user/hadwiger/venv/bin/python
P=/home/user/hadwiger/phase3e; cd "$P"
ST=$P/selftest; rm -rf "$ST"; mkdir -p "$ST/mini" /dev/shm/selftest3e /mnt/d/hadwiger/phase3e/selftest_keep
rm -rf /mnt/d/hadwiger/phase3e/selftest_keep/*
FAIL=0
fail() { echo "!! $1"; FAIL=1; }
rcis() { [ "$1" = "$2" ] || fail "$3 rc=$1 (要 $2)"; }
# 真檔守衛: 開頭影低 sha256, 之後逐次對數 (用 sha 唔用 grep "Phase 3e" —— 真檔遲早會有 Phase 3e 字樣, grep 會誤報)
REALFILES="/mnt/c/Users/user/Desktop/spindle/phase2b/DECISION.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/hadwiger-project.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/no-spindle-hardness.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/MEMORY.md"
sha256sum $REALFILES > $ST/realfiles.sha256
realguard() { sha256sum -c --quiet $ST/realfiles.sha256 && echo "  真檔一個 byte 都冇郁 ✓ ($1)" || fail "真檔被改咗 ($1)"; }

echo "== 1. syntax"
for f in *.py; do $PY -m py_compile "$f" || fail "py_compile $f"; done
for f in *.sh; do bash -n "$f" || fail "bash -n $f"; done
echo "syntax ok=$((1-FAIL))"

echo "== 2. 迷你戰役 (cnc2k --keep-dir, budget-stop → resume → certified)"
$PY - <<'EOF'
# PHP(7,6): 7 隻鴿 6 個窿 → UNSAT; march d=3 唔會 root-refute
import json, hashlib
P=7; H=6; cl=[]
var=lambda p,h:(p-1)*H+h
for p in range(1,P+1): cl.append([var(p,h) for h in range(1,H+1)])
for h in range(1,H+1):
    for p in range(1,P+1):
        for q in range(p+1,P+1): cl.append([-var(p,h),-var(q,h)])
f="/home/user/hadwiger/phase3e/selftest/mini/base.cnf"
open(f,"w").write("p cnf %d %d\n"%(P*H,len(cl))+"".join(" ".join(map(str,c))+" 0\n" for c in cl))
s=hashlib.sha256(open(f,"rb").read()).hexdigest()
json.dump({"removed":[],"n_removed":0,"n":7,"n_remaining":7,"n_edges":0,"clauses":len(cl),"cnf_sha256":s,"claim":"PHP(7,6) UNSAT (selftest)"},open(f[:-4]+".json","w"),indent=1)
print("mini base.cnf PHP(7,6)", len(cl), "clauses sha", s[:16])
EOF
M=$ST/mini; K=/mnt/d/hadwiger/phase3e/selftest_keep/mini
/home/user/hadwiger/tools/CnC/march_cu/march_cu $M/base.cnf -d 3 -o $M/cubes_d3.icnf | grep -E "number of cubes" || fail "march_cu"
echo "-- 2a. --time-budget 0 (即刻 budget-stop)"
$PY /home/user/hadwiger/phase3c/cnc2k.py --cnf $M/base.cnf --icnf $M/cubes_d3.icnf --out $M/cnc_mini --workers 4 --timeout 60 --solver kissat \
   --proof-dir /dev/shm/selftest3e --binary --time-budget 0 --split-depth 2 --max-split 2 --audit-frac 0.5 --progress 30 --keep-dir $K > $M/cnc0.log 2>&1; echo "cnc2k(budget 0) rc=$?"
$PY -c "
import json; s=json.load(open('$M/cnc_mini/state.json')); print('  done', len(s['done']), 'pending', len(s['pending']), 'status', s.get('status'), 'keep_dir', s.get('keep_dir'))"
echo "-- 2b. --resume --time-budget 600 (無損續跑 → certified)"
rm -f $M/cnc_mini/lock
$PY /home/user/hadwiger/phase3c/cnc2k.py --resume --out $M/cnc_mini --workers 4 --time-budget 600 --progress 30 --keep-dir $K > $M/cnc1.log 2>&1; echo "cnc2k(resume) rc=$?"
grep -E "^\[resume\]|^\[done\]|^\[cover\]" $M/cnc1.log | cut -c1-240
$PY - <<'EOF'
import json, os, hashlib
M="/home/user/hadwiger/phase3e/selftest/mini"; K="/mnt/d/hadwiger/phase3e/selftest_keep/mini"
b=json.load(open(M+"/cnc_mini/bundle.json")); st=json.load(open(M+"/cnc_mini/state.json"))
files=[f for f in os.listdir(K) if f.endswith(".drat")]; aud=[f for f in os.listdir(K+"/audit") if f.endswith(".drat")] if os.path.isdir(K+"/audit") else []
shaok=all(hashlib.sha256(open(d["kept"],"rb").read()).hexdigest()==d["proof_sha"] and os.path.getsize(d["kept"])==d["proof_bytes"] for d in st["done"].values())
ok = (st["status"]=="certified" and b["kept_leaves"]==b["leaves"]==len(files)>0 and b["keep_errors"]==0 and b["kept_audit"]==b["audit"]["n"]==len(aud)>0 and shaok)
print("bundle: leaves %d kept %d audit %d kept_audit %d; keep dir %d + %d audit; sha+bytes 全對 %s; shm 殘留 %d" % (
    b["leaves"], b["kept_leaves"], b["audit"]["n"], b["kept_audit"], len(files), len(aud), shaok, len([f for f in os.listdir('/dev/shm/selftest3e') if f.endswith('.drat')])))
print("RESUME_KEEP_TEST", "PASS" if ok else "FAIL")
EOF
echo "-- 2c. verify_final (--skip-l3) 應該 all_ok"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3e/vf --json-out $M/verify_final.json > $M/vf.log 2>&1; rcis "$?" "0" "verify_final"
echo "-- 2d. crosscheck3d (drat-trim -L → cake_lpr + lrat-check), 全部 leaf"
$PY /home/user/hadwiger/phase3d/crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3e/xc > $M/xc.log 2>&1; rcis "$?" "0" "crosscheck3d"
tail -2 $M/xc.log | cut -c1-260
$PY -c "
import json; j=json.load(open('$M/crosscheck.json')); r=j['records'][0]
print('  sampled', j['n_sampled'], 'ok', j['ok'], 'all_ok', j['all_ok'], '| 第一個 leaf:', {k:r.get(k) for k in ('drattrim_verified','cake_lpr_verified','lrat_check_verified','lrat_bytes')})
print('CAKE_LPR_TEST', 'PASS' if (j['all_ok'] and all(x['cake_lpr_verified'] and x['lrat_check_verified'] for x in j['records'])) else 'FAIL')"
echo "-- 2e. 毒藥 A: 斬爛一個 kept 證明 → crosscheck + verify_final 都要唔過"
F1=$(ls $K/*.drat | head -1); cp "$F1" /dev/shm/selftest3e/backup.drat; head -c 8 "$F1" > /dev/shm/selftest3e/t.drat; cp /dev/shm/selftest3e/t.drat "$F1"
$PY /home/user/hadwiger/phase3d/crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3e/xc > $M/xc2.log 2>&1; rcis "$?" "4" "poison-A crosscheck3d"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3e/vf --json-out $M/vf2.json > $M/vf2.log 2>&1; rcis "$?" "4" "poison-A verify_final"
cp /dev/shm/selftest3e/backup.drat "$F1"
$PY /home/user/hadwiger/phase3d/crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3e/xc > $M/xc3.log 2>&1; rcis "$?" "0" "restored crosscheck3d"
echo "-- 2f. 毒藥 B: 改爛 state.json 嘅 proof_sha (帳同證明唔一致) → verify_final 要唔過"
cp $M/cnc_mini/state.json /dev/shm/selftest3e/state.bak
$PY -c "
import json; p='$M/cnc_mini/state.json'; s=json.load(open(p)); k=sorted(s['done'])[0]; s['done'][k]['proof_sha']='0'*64; json.dump(s,open(p,'w'),indent=1); print('  poisoned leaf', k)"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3e/vf --json-out $M/vf3.json > $M/vf3.log 2>&1; rcis "$?" "4" "poison-B verify_final"
cp /dev/shm/selftest3e/state.bak $M/cnc_mini/state.json
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3e/vf --json-out $M/vf4.json > $M/vf4.log 2>&1; rcis "$?" "0" "restored verify_final"
echo "-- 2g. resume 中途換 keep-dir 要拒絕"
$PY /home/user/hadwiger/phase3c/cnc2k.py --resume --out $M/cnc_mini --workers 2 --time-budget 60 --keep-dir /mnt/d/hadwiger/phase3e/selftest_keep/other > $M/resume_bad.log 2>&1
if [ "$?" = "0" ]; then fail "換 keep-dir 竟然接受咗"; else echo "  換 keep-dir 被拒絕 ✓: $(grep -o '!!.*' $M/resume_bad.log | head -1 | cut -c1-160)"; fi

echo "== 3. extend_decision (純函數, probe3e 繼承 probe3d 嗰個; 用 Phase 3c r10a 真數)"
$PY - <<'EOF'
import sys
sys.path.insert(0, "/home/user/hadwiger/phase3d")
from probe3d import extend_decision
def stn(done_n, pend_n, per=10.94, stuck=0, wasted=0.0):
    return {"done": {str(i): {"solve_s": per*0.7, "verify_s": per*0.3} for i in range(done_n)},
            "pending": [{"id": str(i)} for i in range(pend_n)], "running_at_save": [], "stuck": [{"id":"x"}]*stuck, "wasted_s": wasted}
r10a  = extend_decision(stn(15698, 686), 14, 0.5, 0.0, 3600)
big   = extend_decision(stn(1000, 15384), 14, 0.5, 0.0, 3600)
stuck = extend_decision(stn(15698, 686, stuck=2), 14, 0.5, 0.0, 3600)
used  = extend_decision(stn(15698, 686), 14, 0.5, 3400.0, 3600)
none  = extend_decision(stn(16384, 0), 14, 0.5, 0.0, 3600)
nodone= extend_decision(stn(0, 16384), 14, 0.5, 0.0, 3600)
edge  = extend_decision(stn(1000, 2303), 14, 0.5, 0.0, 3600)      # eta 啱啱好 0.5 h 附近: 用 > 做界, ≤ 0.5 要延長
for n, r in (("r10a", r10a), ("eta 太大", big), ("stuck", stuck), ("額度用完", used), ("冇 pending", none), ("一個都未完", nodone), ("eta≈0.5", edge)):
    print("  %-10s extend=%-5s add=%-6.0f eta_h=%s — %s" % (n, r["extend"], r["add"], r["eta_h"], r["why"]))
ok = (r10a["extend"] and abs(r10a["eta_h"]-0.149) < 0.01 and r10a["add"] == 900
      and not big["extend"] and not stuck["extend"] and not used["extend"] and not none["extend"] and not nodone["extend"]
      and (edge["extend"] == (edge["eta_h"] <= 0.5)))
print("EXTEND_TEST", "PASS" if ok else "FAIL")
EOF

echo "== 4. probe3e --dry-run (round 1, 步幅 20)"
$PY probe3e.py --dry-run --run-id p3e0_dryrun --seed-run /home/user/hadwiger/phase3c/runs/p3c1_shrink \
   --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun --rounds 6 --step 20 --min-step 5 --attempts-per-round 2 \
   --workers 14 --cap 21600 --extend 3600 --extend-eta-h 0.5 --total-cap 86400 --cpu-cap-h 160 --timeout 900 --depth 14 \
   --proof-dir /dev/shm/selftest3e/pd --keep-root /mnt/d/hadwiger/phase3e/selftest_keep > $ST/dryrun.log 2>&1; rcis "$?" "0" "probe3e --dry-run"
tail -4 $ST/dryrun.log | cut -c1-260
$PY - <<'EOF'
import json
D="/home/user/hadwiger/phase3e/selftest/dryrun"
st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json")); a=json.load(open(D+"/attempts.json"))
o=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))["ordering"]
r1=r[0]; x=r1["attempts"][0]
checks = {
 "S_acc 270": len(st["S_acc"])==270,
 "step 20": st["step"]==20 and r1["step"]==20,
 "round_done 1": st["round_done"]==1,
 "target 290": r1["target_removed"]==290 and x["removed"]==290,
 "cap 21600": r1["cap_s"]==21600,
 "extend 3600": r1["extend_max_s"]==3600.0,
 "G2p 776": x["cnf"]["n_remaining"]==776 and r1["target_G2p"]==776 and r1["target_G3p"]==1551,
 "added = ordering[270:290]": x["added_candidates"]==o[270:290],
 "S = S_acc ∪ batch": sorted(x["S"])==sorted(set(st["S_acc"])|set(o[270:290])),
 "tag r01a": x["tag"]=="r01a",
 "status dry-run": x["status"]=="dry-run",
 "seed r09a/1591": st["seed"]["last_certified_tag"]=="r09a" and st["seed"]["G3p_n"]==1591 and bool(st["seed"]["leaf_proofs_dir"]),
 "cpu 0": st["cpu_h_used"]==0.0,
 "attempts.json 同步": len(a)==1 and a[0]["tag"]=="r01a" and a[0]["round"]==1,
 "冇全域排除累積器": not any(k in st for k in ("excluded_next","perma_excluded","excluded")),
 "本輪排除係空": r1["excluded_this_round"]==[],
 "冇 best": st.get("best") is None,
}
for k,v in checks.items():
    print("  %-28s %s" % (k, "ok" if v else "!! FAIL"))
print("DRYRUN_TEST", "PASS" if all(checks.values()) else "FAIL")
EOF

echo "== 5. 排除集逐輪重置 + 步幅持久化 (假造 round 1 = blocked, 步幅已減半做 10)"
rm -rf $ST/dryrun_reset; cp -r $ST/dryrun $ST/dryrun_reset
$PY - <<'EOF'
import json
D="/home/user/hadwiger/phase3e/selftest/dryrun_reset"
o=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))["ordering"]
st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json"))
B=[o[270], o[273], o[275]]                                     # 假設 round 1 (|S| = 290) 呢三粒擋路
r[0]["status"]="blocked"; r[0]["B_sets"]=[B]; r[0]["B_sizes"]=[len(B)]; r[0]["excluded_this_round"]=sorted(B)
r[0]["net_removed"]=0; r[0]["S_acc_after"]=st["S_acc"]; r[0]["G2p_n"]=796; r[0]["G3p_n"]=1591
r[0]["attempts"][0]["status"]="SAT"; r[0]["attempts"][0]["B_size"]=len(B); r[0]["attempts"][0]["wall_s"]=100.0
st["B_sets"]=[{"round":1,"tag":"r01a","step":20,"S_size":290,"B":B,"size":len(B),"B_in_S_acc":[],"B_in_batch":B,"col_file":"x","witness_col":"y"}]
st["step"]=10; st["step_history"]=[{"round":1,"step":20,"why":"兩張都 SAT","B_sizes":[len(B)]}]
st["stop_reason"]="test"; st["finished"]="x"
json.dump(st,open(D+"/state.json","w"),indent=1); json.dump(r,open(D+"/rounds.json","w"),indent=1)
print("  假造好: round 1 blocked, B =", B, "步幅 →", st["step"])
EOF
$PY probe3e.py --resume --dry-run --run-id p3e0_dryrun --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun_reset \
   --rounds 6 --step 20 --min-step 5 --attempts-per-round 2 --workers 14 --cap 21600 --extend 3600 --extend-eta-h 0.5 \
   --total-cap 86400 --cpu-cap-h 160 --timeout 900 --depth 14 --proof-dir /dev/shm/selftest3e/pd \
   --keep-root /mnt/d/hadwiger/phase3e/selftest_keep > $ST/dryrun_reset.log 2>&1; rcis "$?" "0" "probe3e --resume (reset)"
$PY - <<'EOF'
import json
D="/home/user/hadwiger/phase3e/selftest/dryrun_reset"
o=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))["ordering"]
st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json"))
r2=[x for x in r if x["round"]==2][0]; x=r2["attempts"][0]
B=[o[270], o[273], o[275]]
checks = {
 "round 2 用步幅 10 (冇 reset 返 20)": r2["step"]==10 and st["step"]==10,
 "target 280 / |G₂′| 786": r2["target_removed"]==280 and x["cnf"]["n_remaining"]==786,
 "本輪排除係空 (逐輪重置)": r2["excluded_this_round"]==[] and x["excluded_before"]==[],
 "上一輪擋路嘅點返返嚟": all(v in x["S"] for v in B),
 "added = ordering[270:280]": x["added_candidates"]==o[270:280],
 "冇全域排除累積器": not any(k in st for k in ("excluded_next","perma_excluded","excluded")),
 "tag r02a": x["tag"]=="r02a",
}
for k,v in checks.items():
    print("  %-34s %s" % (k, "ok" if v else "!! FAIL"))
print("RESET_STEP_TEST", "PASS" if all(checks.values()) else "FAIL")
EOF

echo "== 6. 三個預算閘門 (CPU-h / wall / 輪數)"
$PY - <<'EOF'
import json, os, shutil, subprocess, sys
BASE="/home/user/hadwiger/phase3e/selftest/dryrun_reset"; ST="/home/user/hadwiger/phase3e/selftest"
PY=sys.executable
def mk(name, patch):
    D=os.path.join(ST,name)
    shutil.rmtree(D, ignore_errors=True); shutil.copytree(BASE, D)
    st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json"))
    patch(st, r)
    st["stop_reason"]="test"; st["finished"]="x"
    json.dump(st,open(D+"/state.json","w"),indent=1); json.dump(r,open(D+"/rounds.json","w"),indent=1)
    return D
def run(D):
    p=subprocess.run([PY, "/home/user/hadwiger/phase3e/probe3e.py", "--resume", "--ack-operator", "--dry-run", "--run-id", "p3e0_dryrun",
                      "--batches", "/home/user/hadwiger/phase3b/batches_g2.json", "--out", D, "--rounds", "6", "--step", "20", "--min-step", "5",
                      "--attempts-per-round", "2", "--workers", "14", "--cap", "21600", "--extend", "3600", "--extend-eta-h", "0.5",
                      "--total-cap", "86400", "--cpu-cap-h", "160", "--timeout", "900", "--depth", "14",
                      "--proof-dir", "/dev/shm/selftest3e/pd", "--keep-root", "/mnt/d/hadwiger/phase3e/selftest_keep"], capture_output=True, text=True)
    return p.returncode, json.load(open(D+"/state.json")).get("stop_reason") or "", p.stdout[-300:]
def cpu(st, r):
    r[0]["attempts"][0]["wall_s"]=41000.0                       # 41000 s × 14 / 3600 = 159.4 CPU-h (剩 0.6)
def wall(st, r):
    st["elapsed_s"]=85000.0                                     # 24 h = 86400 s, 剩 1400 s = 0.39 h
def rounds(st, r):
    st["round_done"]=6
res={}
for n, patch, want in (("cpu", cpu, "CPU 預算"), ("wall", wall, "總 wall 上限"), ("rounds", rounds, "輪數上限")):
    D=mk("gate_"+n, patch); rc, sr, tail = run(D)
    ok = (rc==0 and want in sr)
    res[n]=ok
    print("  gate %-7s rc=%s ok=%s | %s" % (n, rc, ok, sr[:150]))
print("BUDGET_GATE_TEST", "PASS" if all(res.values()) else "FAIL")
EOF

echo "== 7. --resume 要拒絕 needs_operator (冇 --ack-operator)"
rm -rf $ST/dryrun_ack; cp -r $ST/dryrun $ST/dryrun_ack
$PY -c "
import json; p='$ST/dryrun_ack/state.json'; s=json.load(open(p)); s['needs_operator']=True; s['finished']='x'; s['stop_reason']='!! test needs_operator'; json.dump(s,open(p,'w'),indent=1)"
$PY probe3e.py --resume --dry-run --run-id p3e0_dryrun --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun_ack \
   --proof-dir /dev/shm/selftest3e/pd --keep-root /mnt/d/hadwiger/phase3e/selftest_keep > $ST/dryrun_ack.log 2>&1
if [ "$?" = "0" ]; then fail "冇 --ack-operator 竟然行到"; else echo "  拒絕 ✓: $(head -1 $ST/dryrun_ack.log | cut -c1-160)"; fi
$PY probe3e.py --resume --ack-operator --dry-run --run-id p3e0_dryrun --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun_ack \
   --rounds 6 --step 20 --min-step 5 --attempts-per-round 2 --workers 14 --cap 21600 --total-cap 86400 --cpu-cap-h 160 \
   --proof-dir /dev/shm/selftest3e/pd --keep-root /mnt/d/hadwiger/phase3e/selftest_keep > $ST/dryrun_ack2.log 2>&1; rcis "$?" "0" "--resume --ack-operator"

echo "== 8. finalize3e --dry-run (冇 best)"
$PY finalize3e.py --run $ST/dryrun --workers 14 --dry-run > $ST/finalize_dryrun.log 2>&1; rcis "$?" "0" "finalize3e --dry-run"
tail -5 $ST/finalize_dryrun.log | cut -c1-220
echo "-- dryrun 產物:"; ls $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_* 2>/dev/null
realguard "冇 best 收爐之後"

echo "== 9. finalize3e 有 best 嘅報告格式路徑 (唔跑重驗)"
$PY - <<'EOF'
import json, os, shutil, sys, types
ST="/home/user/hadwiger/phase3e/selftest"; D=os.path.join(ST,"dryrun_best")
shutil.rmtree(D, ignore_errors=True); shutil.copytree(os.path.join(ST,"dryrun_reset"), D)
o=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))["ordering"]
st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json")); at=json.load(open(D+"/attempts.json"))
S=sorted(set(st["S_acc"]) | set(o[270:290]))
rec={"tag":"r01a","round":1,"step":20,"attempt":1,"kind":"第一刀","dir":os.path.join(D,"r01a"),"removed":290,"S":S,"status":"certified",
     "l3_ok":True,"col5_ok":True,"engine_b_run":True,"leaves":16384,"n_cubes":16384,"wall_s":13000.0,"extended_s":0.0,
     "mean_solve_s":6.1,"median_solve_s":5.0,"mean_sv_s":11.2,"max_solve_s":40.0,"cpu_solve_s":1.0,"cpu_verify_s":1.0,
     "proof_total_mb":1.0,"split_events":0,"solver_errors":0,"wasted_s":0.0,"cnc_launches":1,
     "cnf":{"cnf_sha256":"deadbeef"*8,"n_remaining":776,"n_edges":4200},
     "G2p_n":776,"G2p_m":4200,"G3p_n":1551,"G3p_m":8500,"col5":{"edges_checked":8500},"settled":True,
     "keep":{"dir":"/x","on_disk":True,"kept_leaves":16384,"gb":80.0}}
r[0]["status"]="certified"; r[0]["net_removed"]=20; r[0]["S_acc_after"]=S; r[0]["G2p_n"]=776; r[0]["G3p_n"]=1551
r[0]["certified_tag"]="r01a"; r[0]["attempts"]=[rec]; r[0]["wall_s"]=13000.0
st["S_acc"]=S; st["round_done"]=1; st["step"]=20; st["step_history"]=[]
st["best"]={"tag":"r01a","dir":rec["dir"],"round":1,"removed":290,"G2p_n":776,"G2p_m":4200,"G3p_n":1551,"G3p_m":8500,
            "keep_dir":"/x","leaves":16384,"base_sha256":rec["cnf"]["cnf_sha256"],"engine_b_run":True,"col5_ok":True,"when":"x"}
json.dump(st,open(D+"/state.json","w"),indent=1); json.dump(r,open(D+"/rounds.json","w"),indent=1); json.dump([rec],open(D+"/attempts.json","w"),indent=1)
os.makedirs(os.path.join(rec["dir"],"cnc_r01a"), exist_ok=True)
json.dump({"cover_mode":"pure","base_sha":rec["cnf"]["cnf_sha256"],"leaves":16384},open(os.path.join(rec["dir"],"cnc_r01a","bundle.json"),"w"))
sys.path.insert(0,"/home/user/hadwiger/phase3e")
import finalize3e
a=types.SimpleNamespace(run=D, workers=14, dry_run=True, force_verify=False, frac=0.05)
f=finalize3e.Fin(a); f.vok=True; f.rec_ok=True; f.improved=True; f.rb={"ok":True}
fa={"tag":"r01a","dir":rec["dir"],"vdir":rec["dir"],"keep_dir":"/x","has_keep":True,"S":S,"rec":rec,"arch":"/x/record",
    "n_disk_leaf":16384,"n_disk_audit":819,"G2p_n":776,"G2p_m":4200,"G3p_n":1551,"G3p_m":8500,"leaves":16384}
vres={"all_ok":True,"leaf_reverify":{"n":16384,"ok":16384,"wall_s":3000.0,"proof_total_gb":80.0,"proof_sha_sum_sha256":"z"*64},
      "cover_reverify":{"verified":True},"audit_reverify":{"complete":True},"l3_final":{"all_ok":True,"same_files_as_campaign_l3":{"a":True}},
      "exactfield_complete_G3p_again":{"rc":0}}
xres={"all_ok":True,"ok":819,"n_sampled":819}; c5={"all_ok":True}
arch={"dir":"/x/record","n_files":17000,"bytes":8.0e10,"sha256sums_sha256":"a"*64,"check_rc":0,"n_leaf_proofs":16384,"n_audit_proofs":819,"windows_mirror":"/w"}
stg={"reduction_files":100,"check_rc":0}
f.report(fa,vres,xres,c5,arch,stg); f.facts(fa,vres,xres,c5,arch,stg); f.decision(fa,vres,xres,arch); f.memory(fa,vres,xres,arch)
rep=open("/home/user/hadwiger/phase3e/selftest/phase3e_results_dryrun.md",encoding="utf-8").read()
fj=json.load(open("/home/user/hadwiger/phase3e/facts_dryrun.json",encoding="utf-8"))["facts"]
dec=open("/home/user/hadwiger/phase3e/DECISION_dryrun.md",encoding="utf-8").read()
mem=open("/home/user/hadwiger/phase3e/mem_dryrun_hadwiger-project.md",encoding="utf-8").read()
checks={
 "報告有每輪帳": "## 每輪帳" in rep,
 "報告有雷區密度": "雷區密度" in rep,
 "報告有 round 1 行": "| 1 | 20 | 290 | certified | 20 |" in rep,
 "報告標題係小步慢行": "小步慢行" in rep and "每輪剪" in rep,
 "報告有 RECORD 觸發線解釋": "716" in rep and "720" in rep,
 "facts 有 rounds": "g2shrink3e.rounds" in fj and len(fj["g2shrink3e.rounds"]["value"])==1,
 "facts 有 B_analysis": "g2shrink3e.B_analysis" in fj and fj["g2shrink3e.B_analysis"]["value"]["n"]==1,
 "facts 有 step_history": "g2shrink3e.step_history" in fj,
 "facts 有 vs_heule": "g2shrink3e.vs_heule_1441" in fj,
 "facts 冇 3d 殘留": not any(k.startswith("g2shrink3d.") and fj[k].get("source","").startswith("phase3e") for k in fj),
 "DECISION 有 Phase 3e 小步慢行": "**Phase 3e 小步慢行" in dec,
 "MEMORY 有 Phase 3e(": "**Phase 3e(" in mem,
 "facts 對照 Phase 3d B": fj["g2shrink3e.B_analysis"]["value"]["phase3d_n"] in (0,3),
}
for k,v in checks.items():
    print("  %-30s %s" % (k, "ok" if v else "!! FAIL"))
print("FINALIZE_BEST_TEST", "PASS" if all(checks.values()) else "FAIL")
EOF
realguard "有 best 報告路徑之後"

echo "== 10. status3e --once"
$PY status3e.py --once > $ST/status_once.md 2>&1; rcis "$?" "0" "status3e --once"; head -8 $ST/status_once.md

if [ "${1:-}" = "--smoke" ]; then
  echo "== 11. 真實 smoke (真 G2 剪 290 粒, cap 240 s → budget-stop → keep **保留** → needs_operator)"
  rm -rf $ST/smoke
  $PY probe3e.py --run-id p3e0_smoke --seed-run /home/user/hadwiger/phase3c/runs/p3c1_shrink \
     --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/smoke --rounds 1 --step 20 --attempts-per-round 2 --workers 14 \
     --cap 240 --extend 600 --extend-eta-h 0.5 --total-cap 3600 --cpu-cap-h 20 --timeout 900 --depth 14 \
     --proof-dir /dev/shm/selftest3e/smoke --keep-root /mnt/d/hadwiger/phase3e/selftest_keep > $ST/smoke.log 2>&1; echo "smoke rc=$?"
  grep -E "march_cu|cnc2k 第|budget-stop|唔延長|keep 目錄|PROBE3E|round 1" $ST/smoke.log | cut -c1-240 | tail -10
  $PY - <<'EOF'
import json, os
D="/home/user/hadwiger/phase3e/selftest/smoke"
st=json.load(open(D+"/state.json")); r=json.load(open(D+"/rounds.json")); x=r[0]["attempts"][0]
kd="/mnt/d/hadwiger/phase3e/selftest_keep/r01a"
ok=(x["status"] in ("budget-stop","hard-killed") and (x.get("keep") or {}).get("on_disk") and st.get("needs_operator") and os.path.isdir(kd))
print("  status", x["status"], "| keep on_disk", (x.get("keep") or {}).get("on_disk"), "| 碟上", os.path.isdir(kd), "| needs_operator", st.get("needs_operator"))
print("SMOKE_TEST", "PASS" if ok else "FAIL")
EOF
  rm -rf /mnt/d/hadwiger/phase3e/selftest_keep/r01a
fi

echo "== 清場"
rm -rf /dev/shm/selftest3e /mnt/d/hadwiger/phase3e/selftest_keep
rm -f $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_* /mnt/c/Users/user/Desktop/spindle/phase3e/status.md.tmp
BAD=$(grep -h "_TEST FAIL" $ST/*.log 2>/dev/null | wc -l)
echo "SELFTEST3E DONE $(date) FAIL=$FAIL (注意: *_TEST PASS/FAIL 行要自己睇返上面)"
