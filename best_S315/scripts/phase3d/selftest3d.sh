#!/bin/bash
# Phase 3d selftest (開跑前必過):
#  1. 全部 .py 編譯 + .sh 語法
#  2. 迷你戰役 (PHP(7,6) UNSAT, march d=3): cnc2k --keep-dir → **--time-budget 0 budget-stop → --resume 續 → certified** (測無損續跑), leaf 證明全部保留 sha 一致
#     → verify_final --skip-l3 all_ok → crosscheck3d (drat-trim -L → cake_lpr + lrat-check) all_ok → 毒藥 (斬爛一個證明) crosscheck 必須唔過
#  3. extend_decision 純函數測試 (用 Phase 3c r10a 真數: 剩 686/16384, 估計 0.15 h → 應該延長; 以及 eta 太大 / stuck / 額度用完 / 冇 pending 四個唔延長個案)
#  4. probe3d --dry-run: seed = Phase 3c r09a (S_acc 270), S = 350 = 270 + ordering[270:350], |G₂′| 716, |G₃′| 1431
#  5. finalize3d --dry-run (冇 best → 報告 / facts / DECISION / MEMORY 全部寫去 dryrun 檔, 唔郁真檔)
#  6. status3d --once
#  7. 真實 smoke (可選, --smoke): 真 G2 一刀 350 粒, cap 240 s → budget-stop → 唔延長 (eta 太大) → keep 目錄清走 → needs_operator
set -u
PY=/home/user/hadwiger/venv/bin/python
P=/home/user/hadwiger/phase3d; cd "$P"
ST=$P/selftest; rm -rf "$ST"; mkdir -p "$ST/mini" /dev/shm/selftest3d /mnt/d/hadwiger/phase3d/selftest_keep
rm -rf /mnt/d/hadwiger/phase3d/selftest_keep/*
FAIL=0
echo "== 1. syntax"
for f in *.py; do $PY -m py_compile "$f" || { echo "!! py_compile $f"; FAIL=1; }; done
for f in *.sh; do bash -n "$f" || { echo "!! bash -n $f"; FAIL=1; }; done
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
f="/home/user/hadwiger/phase3d/selftest/mini/base.cnf"
open(f,"w").write("p cnf %d %d\n"%(P*H,len(cl))+"".join(" ".join(map(str,c))+" 0\n" for c in cl))
s=hashlib.sha256(open(f,"rb").read()).hexdigest()
json.dump({"removed":[],"n_removed":0,"n":7,"n_remaining":7,"n_edges":0,"clauses":len(cl),"cnf_sha256":s,"claim":"PHP(7,6) UNSAT (selftest)"},open(f[:-4]+".json","w"),indent=1)
print("mini base.cnf PHP(7,6)", len(cl), "clauses sha", s[:16])
EOF
M=$ST/mini; K=/mnt/d/hadwiger/phase3d/selftest_keep/mini
/home/user/hadwiger/tools/CnC/march_cu/march_cu $M/base.cnf -d 3 -o $M/cubes_d3.icnf | grep -E "number of cubes" || echo "!! march_cu"
echo "-- 2a. --time-budget 0 (即刻 budget-stop, pending 全部剩返)"
$PY /home/user/hadwiger/phase3c/cnc2k.py --cnf $M/base.cnf --icnf $M/cubes_d3.icnf --out $M/cnc_mini --workers 4 --timeout 60 --solver kissat \
   --proof-dir /dev/shm/selftest3d --binary --time-budget 0 --split-depth 2 --max-split 2 --audit-frac 0.5 --progress 30 --keep-dir $K > $M/cnc0.log 2>&1; echo "cnc2k(budget 0) rc=$?"
$PY -c "
import json; s=json.load(open('$M/cnc_mini/state.json')); print('  done', len(s['done']), 'pending', len(s['pending']), 'status', s.get('status'), 'keep_dir', s.get('keep_dir'))"
echo "-- 2b. --resume --time-budget 600 (無損續跑 → certified)"
rm -f $M/cnc_mini/lock
$PY /home/user/hadwiger/phase3c/cnc2k.py --resume --out $M/cnc_mini --workers 4 --time-budget 600 --progress 30 --keep-dir $K > $M/cnc1.log 2>&1; echo "cnc2k(resume) rc=$?"
grep -E "^\[resume\]|^\[done\]|^\[cover\]" $M/cnc1.log | cut -c1-240
$PY - <<'EOF'
import json, os, hashlib
M="/home/user/hadwiger/phase3d/selftest/mini"; K="/mnt/d/hadwiger/phase3d/selftest_keep/mini"
b=json.load(open(M+"/cnc_mini/bundle.json")); st=json.load(open(M+"/cnc_mini/state.json"))
files=[f for f in os.listdir(K) if f.endswith(".drat")]; aud=[f for f in os.listdir(K+"/audit") if f.endswith(".drat")] if os.path.isdir(K+"/audit") else []
shaok=all(hashlib.sha256(open(d["kept"],"rb").read()).hexdigest()==d["proof_sha"] for d in st["done"].values())
ok = (st["status"]=="certified" and b["kept_leaves"]==b["leaves"]==len(files)>0 and b["keep_errors"]==0 and b["kept_audit"]==b["audit"]["n"]==len(aud)>0 and shaok)
print("bundle: leaves %d kept %d audit %d kept_audit %d; keep dir %d + %d audit; sha 全對 %s; shm 殘留 %d" % (
    b["leaves"], b["kept_leaves"], b["audit"]["n"], b["kept_audit"], len(files), len(aud), shaok, len([f for f in os.listdir('/dev/shm/selftest3d') if f.endswith('.drat')])))
print("RESUME_KEEP_TEST", "PASS" if ok else "FAIL")
EOF
echo "-- 2c. verify_final (--skip-l3) 應該 all_ok"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3d/vf --json-out $M/verify_final.json > $M/vf.log 2>&1; echo "verify_final rc=$? (要 0)"
echo "-- 2d. crosscheck3d (drat-trim -L → cake_lpr + lrat-check), 全部 leaf"
$PY crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3d/xc > $M/xc.log 2>&1; echo "crosscheck3d rc=$? (要 0)"; tail -2 $M/xc.log | cut -c1-260
$PY -c "
import json; j=json.load(open('$M/crosscheck.json')); r=j['records'][0]
print('  sampled', j['n_sampled'], 'ok', j['ok'], 'all_ok', j['all_ok'], '| 第一個 leaf:', {k:r.get(k) for k in ('drattrim_verified','cake_lpr_verified','lrat_check_verified','lrat_bytes')})
print('CAKE_LPR_TEST', 'PASS' if (j['all_ok'] and all(x['cake_lpr_verified'] and x['lrat_check_verified'] for x in j['records'])) else 'FAIL')"
echo "-- 2e. 毒藥: 斬爛一個 kept 證明 → crosscheck + verify_final 都要唔過"
F1=$(ls $K/*.drat | head -1); cp "$F1" /dev/shm/selftest3d/backup.drat; head -c 8 "$F1" > /dev/shm/selftest3d/t.drat; cp /dev/shm/selftest3d/t.drat "$F1"
$PY crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3d/xc > $M/xc2.log 2>&1; echo "poison crosscheck3d rc=$? (要 4)"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir $M --tag mini --keep-dir $K --workers 4 --skip-l3 --tmp /dev/shm/selftest3d/vf --json-out $M/vf2.json > $M/vf2.log 2>&1; echo "poison verify_final rc=$? (要 4)"
cp /dev/shm/selftest3d/backup.drat "$F1"
$PY crosscheck3d.py --attempt-dir $M --tag mini --keep-dir $K --out $M --frac 1.0 --workers 4 --tmp /dev/shm/selftest3d/xc > $M/xc3.log 2>&1; echo "restored crosscheck3d rc=$? (要 0)"

echo "== 3. extend_decision (純函數, 用 Phase 3c r10a 真數)"
$PY - <<'EOF'
import sys
sys.path.insert(0, "/home/user/hadwiger/phase3d")
from probe3d import extend_decision
def stn(done_n, pend_n, per=10.94, stuck=0, wasted=0.0):
    return {"done": {str(i): {"solve_s": per*0.7, "verify_s": per*0.3} for i in range(done_n)},
            "pending": [{"id": str(i)} for i in range(pend_n)], "running_at_save": [], "stuck": [{"id":"x"}]*stuck, "wasted_s": wasted}
r10a = extend_decision(stn(15698, 686), 14, 0.5, 0.0, 3600)          # Phase 3c round 10: 差 ~9 分鐘就完, 但被 3.5 h 上限殺死
big   = extend_decision(stn(1000, 15384), 14, 0.5, 0.0, 3600)
stuck = extend_decision(stn(15698, 686, stuck=2), 14, 0.5, 0.0, 3600)
used  = extend_decision(stn(15698, 686), 14, 0.5, 3400.0, 3600)
none  = extend_decision(stn(16384, 0), 14, 0.5, 0.0, 3600)
nodone= extend_decision(stn(0, 16384), 14, 0.5, 0.0, 3600)
for n, r in (("r10a", r10a), ("eta 太大", big), ("stuck", stuck), ("額度用完", used), ("冇 pending", none), ("一個都未完", nodone)):
    print("  %-10s extend=%-5s add=%-6.0f eta_h=%s — %s" % (n, r["extend"], r["add"], r["eta_h"], r["why"]))
ok = (r10a["extend"] and abs(r10a["eta_h"]-0.149) < 0.01 and r10a["add"] == 900
      and not big["extend"] and not stuck["extend"] and not used["extend"] and not none["extend"] and not nodone["extend"])
print("EXTEND_TEST", "PASS" if ok else "FAIL")
EOF

echo "== 4. probe3d --dry-run (seed = Phase 3c r09a)"
rm -rf $ST/dryrun
$PY probe3d.py --dry-run --run-id p3d0_dryrun --seed-run /home/user/hadwiger/phase3c/runs/p3c1_shrink --batches /home/user/hadwiger/phase3b/batches_g2.json \
   --out $ST/dryrun --attempts 3 --target-removed 350 --workers 14 --proof-dir /dev/shm/selftest3d/pd --keep-root /mnt/d/hadwiger/phase3d/selftest_keep > $ST/dryrun.log 2>&1; echo "probe3d dry-run rc=$?"
cut -c1-330 $ST/dryrun.log
$PY - <<'EOF'
import json
ST="/home/user/hadwiger/phase3d/selftest/dryrun"
st=json.load(open(ST+"/state.json")); at=json.load(open(ST+"/attempts.json")); bj=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))
x=at[0]; o=bj["ordering"]
ok = (len(st["S_acc"])==270 and x["removed"]==350 and x["cnf"]["n_remaining"]==716 and x["added_candidates"]==o[270:350]
      and sorted(x["S"])==sorted(set(st["S_acc"])|set(o[270:350])) and st["seed"]["last_certified_tag"]=="r09a" and st["seed"]["G3p_n"]==1591
      and x["tag"]=="p3da" and st["seed"]["leaf_proofs_dir"] and x["status"]=="dry-run")
print("seed S_acc %d (%s, |G₃′| %s, leaf 證明 %s)" % (len(st["S_acc"]), st["seed"]["last_certified_tag"], st["seed"]["G3p_n"], st["seed"]["leaf_proofs_dir"]))
print("attempt %s: |S| %d → |G₂′| %d, |G₃′| %d; 新加 %d 粒 == ordering[270:350]: %s" % (
    x["tag"], x["removed"], x["cnf"]["n_remaining"], 2*x["cnf"]["n_remaining"]-1, len(x["added_candidates"]), x["added_candidates"]==o[270:350]))
print("DRYRUN_TEST", "PASS" if ok else "FAIL")
EOF

echo "== 5. finalize3d --dry-run (冇 best 嘅路徑)"
$PY finalize3d.py --run $ST/dryrun --workers 14 --dry-run > $ST/finalize_dryrun.log 2>&1; echo "finalize3d dry-run rc=$? (要 0)"
tail -6 $ST/finalize_dryrun.log | cut -c1-250
echo "-- dryrun 產物:"; ls $ST/ $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_* 2>&1 | grep -v "^total" | head -20
echo "-- 報告頭:"; head -14 $ST/phase3d_results_dryrun.md | cut -c1-240
echo "-- DECISION 新段:"; grep -o "Phase 3d 最後一刀.\{0,300\}" $P/DECISION_dryrun.md | head -1
echo "-- MEMORY index:"; grep "Hadwiger project" $P/mem_dryrun_MEMORY.md | cut -c1-320
echo "-- facts 新 key:"; $PY -c "import json; f=json.load(open('$P/facts_dryrun.json'))['facts']; print(len(f), [k for k in f if k.startswith('g2shrink3d') or k.startswith('record.')])"
echo "-- 真檔冇被改:"; grep -c "Phase 3d" /mnt/c/Users/user/Desktop/spindle/phase2b/DECISION.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/hadwiger-project.md

echo "== 6. status3d --once"; $PY status3d.py --once > $ST/status_once.md 2>&1; echo "rc=$?"; head -10 $ST/status_once.md | cut -c1-240

if [ "${1:-}" = "--smoke" ]; then
  echo "== 7. 真實 smoke (真 G2, S=350, cap 240 s → budget-stop → 唔延長 → keep 清走)"
  rm -rf $ST/smoke
  $PY probe3d.py --run-id p3d0_smoke --seed-run /home/user/hadwiger/phase3c/runs/p3c1_shrink --batches /home/user/hadwiger/phase3b/batches_g2.json \
     --out $ST/smoke --attempts 1 --target-removed 350 --workers 14 --cap 240 --extend 600 --extend-eta-h 0.5 --total-cap 3600 --cpu-cap-h 20 \
     --timeout 900 --depth 14 --proof-dir /dev/shm/selftest3d/smoke --keep-root /mnt/d/hadwiger/phase3d/selftest_keep > $ST/smoke.log 2>&1; echo "smoke rc=$?"
  grep -E "march_cu|cnc2k 第|budget-stop|唔延長|刪 keep|PROBE3D" $ST/smoke.log | cut -c1-260
  $PY -c "
import json,os; st=json.load(open('$ST/smoke/state.json')); at=json.load(open('$ST/smoke/attempts.json')); x=at[0]
print('  status', x['status'], '| leaf', x.get('leaves'), '/', x.get('n_cubes'), '| mean s+v', x.get('mean_sv_s'), '| keep on_disk', (x.get('keep') or {}).get('on_disk'), '| needs_operator', st.get('needs_operator'))
print('SMOKE_TEST', 'PASS' if (x['status']=='budget-stop' and not (x.get('keep') or {}).get('on_disk') and st.get('needs_operator') and not os.path.isdir('/mnt/d/hadwiger/phase3d/selftest_keep/p3da')) else 'FAIL')"
fi

echo "== cleanup"; rm -rf /dev/shm/selftest3d /mnt/d/hadwiger/phase3d/selftest_keep; rm -f $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_*
echo "SELFTEST3D DONE $(date) FAIL=$FAIL"
