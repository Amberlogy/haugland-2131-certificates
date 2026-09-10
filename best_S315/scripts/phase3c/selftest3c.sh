#!/bin/bash
# Phase 3c selftest (開跑前必過):
#  1. 全部 .py 編譙 + .sh 語法
#  2. cnc2k --keep-dir 迷你戰役 (K5 3 色 UNSAT, march_cu d=2) → certified, leaf 證明全部保留 (sha 一致), 審計證明保留; verify_final --skip-l3 all_ok;
#     毒藥: 斬爛一個 kept 證明 → verify_final 必須唔過 (rc 4); 毒藥: 改 state.json 一個 proof_sha → 必須唔過
#  3. probe3c --dry-run (seed p3br1_shrink): round 4 batch == batches_g2 批次 4, buildg2 S=120 → G₂′ 946 點, DRY RUN 停
#  4. finalize3c --dry-run (seed r03a 做最終圖: cover 重驗 + l3g2 --engine-b 真跑, 唔郁 final/, 報告/facts/DECISION/MEMORY 全部寫去 dryrun 檔)
#  5. status3c --once
set -u
PY=/home/user/hadwiger/venv/bin/python
P=/home/user/hadwiger/phase3c; cd "$P"
ST=$P/selftest; rm -rf "$ST"; mkdir -p "$ST/mini" /dev/shm/selftest3c /mnt/d/hadwiger/phase3c/selftest_keep
rm -rf /mnt/d/hadwiger/phase3c/selftest_keep/*
FAIL=0
echo "== 1. syntax"
for f in *.py; do $PY -m py_compile "$f" || { echo "!! py_compile $f"; FAIL=1; }; done
for f in *.sh; do bash -n "$f" || { echo "!! bash -n $f"; FAIL=1; }; done
echo "syntax ok=$((1-FAIL))"
echo "== 2. cnc2k keep-dir 迷你戰役"
$PY - <<'EOF'
# PHP(7,6): 7 pigeons, 6 holes; x[p][h] = (p-1)*6+h → 42 vars; each pigeon in a hole + no two pigeons share a hole → UNSAT (march d=3 唔會 root-refute)
import json, hashlib
P=7; H=6; cl=[]
var=lambda p,h:(p-1)*H+h
for p in range(1,P+1): cl.append([var(p,h) for h in range(1,H+1)])
for h in range(1,H+1):
    for p in range(1,P+1):
        for q in range(p+1,P+1): cl.append([-var(p,h),-var(q,h)])
f="/home/user/hadwiger/phase3c/selftest/mini/base.cnf"
open(f,"w").write("p cnf %d %d\n"%(P*H,len(cl))+"".join(" ".join(map(str,c))+" 0\n" for c in cl))
s=hashlib.sha256(open(f,"rb").read()).hexdigest()
json.dump({"removed":[],"n_removed":0,"n":7,"n_remaining":7,"n_edges":0,"clauses":len(cl),"cnf_sha256":s,"claim":"PHP(7,6) UNSAT (selftest)"},open(f[:-4]+".json","w"),indent=1)
print("mini base.cnf PHP(7,6)", len(cl), "clauses sha", s[:16])
EOF
M=$ST/mini
/home/user/hadwiger/tools/CnC/march_cu/march_cu $M/base.cnf -d 3 -o $M/cubes_d3.icnf | grep -E "number of cubes" || echo "!! march_cu"
$PY cnc2k.py --cnf $M/base.cnf --icnf $M/cubes_d3.icnf --out $M/cnc_mini --workers 4 --timeout 60 --solver kissat --proof-dir /dev/shm/selftest3c --binary --time-budget 600 --split-depth 2 --max-split 2 --audit-frac 0.5 --progress 30 --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/mini > $M/cnc.log 2>&1; echo "cnc2k rc=$?"
grep -E "^\[start\]|^\[done\]|^\[cover\]|keep" $M/cnc.log | cut -c1-260
$PY - <<'EOF'
import json, os, hashlib
M="/home/user/hadwiger/phase3c/selftest/mini"; K="/mnt/d/hadwiger/phase3c/selftest_keep/mini"
b=json.load(open(M+"/cnc_mini/bundle.json")); st=json.load(open(M+"/cnc_mini/state.json"))
ok = b["kept_leaves"]==b["leaves"]>0 and b["keep_errors"]==0 and b["kept_audit"]==b["audit"]["n"]>0 and st["status"]=="certified"
files=[f for f in os.listdir(K) if f.endswith(".drat")]; afiles=[f for f in os.listdir(K+"/audit") if f.endswith(".drat")]
shaok = all(hashlib.sha256(open(d["kept"],"rb").read()).hexdigest()==d["proof_sha"] and os.path.getsize(d["kept"])==d["proof_bytes"] for d in st["done"].values())
print("bundle: leaves %d kept %d keep_errors %d audit %d kept_audit %d; keep dir %d .drat + %d audit; sha 全對 %s; shm 殘留 %d" % (b["leaves"], b["kept_leaves"], b["keep_errors"], b["audit"]["n"], b["kept_audit"], len(files), len(afiles), shaok, len([f for f in os.listdir('/dev/shm/selftest3c') if f.endswith('.drat')])))
print("KEEP_TEST", "PASS" if (ok and shaok and len(files)==b["leaves"]) else "FAIL")
EOF
echo "-- verify_final (應該 all_ok)"
$PY verify_final.py --attempt-dir $M --tag mini --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/mini --workers 4 --skip-l3 --tmp /dev/shm/selftest3c/vf > $M/vf1.log 2>&1; echo "verify_final rc=$? (要 0)"; tail -2 $M/vf1.log | cut -c1-200
echo "-- 毒藥 A: 斬爛一個 kept 證明"
F1=$(ls /mnt/d/hadwiger/phase3c/selftest_keep/mini/*.drat | head -1); cp "$F1" /dev/shm/selftest3c/backup.drat; head -c 8 "$F1" > /dev/shm/selftest3c/trunc.drat; cp /dev/shm/selftest3c/trunc.drat "$F1"
$PY verify_final.py --attempt-dir $M --tag mini --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/mini --workers 4 --skip-l3 --tmp /dev/shm/selftest3c/vf > $M/vf2.log 2>&1; echo "poison A verify_final rc=$? (要 4)"; grep -E "唔過|bad|ok" $M/vf2.log | tail -2 | cut -c1-200
cp /dev/shm/selftest3c/backup.drat "$F1"
echo "-- 毒藥 B: 改 state.json 一個 proof_sha"
cp $M/cnc_mini/state.json /dev/shm/selftest3c/state.bak
$PY -c "
import json; p='$M/cnc_mini/state.json'; s=json.load(open(p)); k=sorted(s['done'])[0]; s['done'][k]['proof_sha']='0'*64; json.dump(s,open(p,'w'))"
$PY verify_final.py --attempt-dir $M --tag mini --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/mini --workers 4 --skip-l3 --tmp /dev/shm/selftest3c/vf > $M/vf3.log 2>&1; echo "poison B verify_final rc=$? (要 4)"
cp /dev/shm/selftest3c/state.bak $M/cnc_mini/state.json
$PY verify_final.py --attempt-dir $M --tag mini --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/mini --workers 4 --skip-l3 --tmp /dev/shm/selftest3c/vf > $M/vf4.log 2>&1; echo "restored verify_final rc=$? (要 0)"
echo "-- cnc2k resume 唔准換 keep-dir"
rm -f $M/cnc_mini/lock; $PY cnc2k.py --resume --out $M/cnc_mini --workers 2 --keep-dir /mnt/d/hadwiger/phase3c/selftest_keep/other > $M/resume_bad.log 2>&1; echo "resume with other keep-dir rc=$? (要非 0): $(tail -1 $M/resume_bad.log | cut -c1-150)"
echo "== 3. probe3c --dry-run (seed)"
rm -rf $ST/dryrun
$PY probe3c.py --dry-run --run-id p3c0_dryrun --seed-run /home/user/hadwiger/phase3b/runs/p3br1_shrink --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun --rounds 30 --workers 14 --cap 12600 --total-cap 144000 --cpu-cap-h 400 --proof-dir /dev/shm/selftest3c/pd --keep-root /mnt/d/hadwiger/phase3c/selftest_keep > $ST/dryrun.log 2>&1; echo "probe3c dry-run rc=$?"
cut -c1-330 $ST/dryrun.log
$PY - <<'EOF'
import json
ST="/home/user/hadwiger/phase3c/selftest/dryrun"
st=json.load(open(ST+"/state.json")); r=json.load(open(ST+"/rounds.json")); bj=json.load(open("/home/user/hadwiger/phase3b/batches_g2.json"))
r4=[x for x in r if x["round"]==4][0]
ok = (len(st["S_acc"])==90 and r4["batch"]==bj["batches"][3] and r4["attempts"][0]["removed"]==120 and r4["attempts"][0]["cnf"]["n_remaining"]==946 and r4["attempts"][0]["status"]=="dry-run"
      and sorted(set(st["S_acc"])|set(r4["batch"]))==r4["attempts"][0]["S"] and st["seed"]["last_certified_tag"]=="r03a" and st["seed"]["G3p_n"]==1951 and [x["from_run"] for x in r[:3]]==["p3br1_shrink"]*3
      and st["cpu_h_used"]==0.0 and r4["budget_before"]["proj_wall_h"]==round(1.15*8134.1/3600,3) and r4["cap_s"]==12600)
print("seed S_acc", len(st["S_acc"]), "| round4 batch == batches[3]:", r4["batch"]==bj["batches"][3], "| S=120 G2'=946:", r4["attempts"][0]["removed"], r4["attempts"][0]["cnf"]["n_remaining"], "| proj_wall_h", r4["budget_before"]["proj_wall_h"], "| cap_s", r4["cap_s"], "| stop:", st["stop_reason"][:60])
print("DRYRUN_TEST", "PASS" if ok else "FAIL")
EOF
ls $ST/dryrun/ | head; ls $ST/dryrun/r04a/
echo "== 4. finalize3c --dry-run (seed r03a 做最終圖; l3g2 --engine-b 真跑, 幾分鐘)"
$PY finalize3c.py --run $ST/dryrun --workers 14 --dry-run > $ST/finalize_dryrun.log 2>&1; echo "finalize3c dry-run rc=$?"
cut -c1-300 $ST/finalize_dryrun.log | tail -25
echo "-- dryrun 輸出檔:"; ls -la $ST/ $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_* 2>&1 | grep -v "^total"
echo "-- 報告頭 40 行:"; head -40 $ST/phase3c_results_dryrun.md | cut -c1-250
echo "-- DECISION 新段:"; grep -o "Phase 3c G₂ 續剪結果.\{0,400\}" $P/DECISION_dryrun.md | head -2
echo "-- MEMORY index:"; grep "Hadwiger project" $P/mem_dryrun_MEMORY.md | cut -c1-400
echo "-- hadwiger-project 新段:"; grep -o "\*\*Phase 3c(.\{0,300\}" $P/mem_dryrun_hadwiger-project.md | head -1
echo "-- facts 新 key:"; $PY -c "import json; f=json.load(open('$P/facts_dryrun.json'))['facts']; print(len(f), [k for k in f if k.startswith('g2shrink3c')])"
echo "-- seed 目錄冇被寫入 (審查 #24):"; ls /home/user/hadwiger/phase3b/runs/p3br1_shrink/r03a/ | grep -c "l3_final\|verify_final" ; ls $ST/final_verify_r03a/ 2>/dev/null | head -5
echo "== 4b. 再跑一次 finalize dry-run (幂等; 記憶/DECISION 已有 marker 嘅 re.sub lambda 分支; 審查 #21)"
$PY - <<'EOF'
import re, io
# 模擬第二次跑: 用第一次 dry-run 嘅輸出 (已有 marker) 做輸入, 走 lambda 分支, 唔可以 raise, marker 只出現一次
P = "/home/user/hadwiger/phase3c"
s = io.open(P + "/mem_dryrun_hadwiger-project.md", encoding="utf-8").read()
block = "**Phase 3c(TEST 起;源碼 `Desktop\\spindle\\phase3c\\`,run `x`):** 第二次."
s2 = re.sub(r"\*\*Phase 3c\(.*?(?=\n\n\*\*How to apply)", lambda m: block, s, count=1, flags=re.S)
assert s2.count("**Phase 3c(") == 1 and "第二次" in s2 and "\\spindle\\phase3c\\" in s2, "hadwiger-project 第二次替換失敗"
d = io.open(P + "/DECISION_dryrun.md", encoding="utf-8").read()
para = "**Phase 3c G₂ 續剪結果(第二次 C:\\path\\y \\s):** ok"
d2 = re.sub(r"\*\*Phase 3c G₂ 續剪結果.*?(?=\n\n)", lambda m: para, d, count=1, flags=re.S)
assert d2.count("**Phase 3c G₂ 續剪結果") == 1 and "第二次" in d2, "DECISION 第二次替換失敗"
print("RERUN_REGEX_TEST PASS")
EOF
echo "== 4c. final_attempt 揀 S == S_acc (審查 #3/#13/#18): 假造 round 5 certified-but-keep-incomplete"
rm -rf $ST/dryrun2; cp -r $ST/dryrun $ST/dryrun2
$PY - <<'EOF'
import json
R = "/home/user/hadwiger/phase3c/selftest/dryrun2"
st = json.load(open(R + "/state.json")); r = json.load(open(R + "/rounds.json"))
fake = {"round": 5, "batch": [1], "S_acc_before": st["S_acc"], "excluded_this_round": [], "B_sets": [], "status": "keep-incomplete", "wall_s": 100.0, "net_removed": 0, "S_acc_after": st["S_acc"], "G2p_n": 976, "G3p_n": 1951,
        "attempts": [{"tag": "r05a", "removed": 91, "S": sorted(st["S_acc"] + [1]), "status": "certified", "l3_ok": True, "keep_incomplete": True, "wall_s": 100.0, "cnf": {"n_remaining": 975, "n_edges": 5600, "cnf_sha256": "x"}, "keep": {"dir": "/nonexistent", "on_disk": True, "kept_leaves": 1}, "G3p_n": 1949}]}
r.append(fake); st["round_done"] = 5; st["stop_reason"] = "test keep-incomplete"
json.dump(r, open(R + "/rounds.json", "w"), indent=1); json.dump(st, open(R + "/state.json", "w"), indent=1)
EOF
$PY finalize3c.py --run $ST/dryrun2 --workers 14 --dry-run > $ST/finalize_dryrun2.log 2>&1; echo "finalize3c dry-run2 rc=$? (要 0)"; grep -E "跳過|最終認證圖:" $ST/finalize_dryrun2.log | cut -c1-300
grep -q "最終認證圖: round 3 r03a" $ST/finalize_dryrun2.log && echo "FINAL_ATTEMPT_TEST PASS" || echo "FINAL_ATTEMPT_TEST FAIL"
echo "== 4d. probe3c resume 拒絕 needs_operator (審查 #16)"
rm -rf $ST/dryrun3; cp -r $ST/dryrun $ST/dryrun3
$PY -c "
import json; p='$ST/dryrun3/state.json'; s=json.load(open(p)); s['needs_operator']=True; s['finished']='x'; s['stop_reason']='!! test'; json.dump(s,open(p,'w'))"
$PY probe3c.py --resume --dry-run --run-id p3c0_dryrun --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun3 --proof-dir /dev/shm/selftest3c/pd --keep-root /mnt/d/hadwiger/phase3c/selftest_keep > $ST/dryrun3.log 2>&1; echo "resume without ack rc=$? (要非 0): $(tail -1 $ST/dryrun3.log | cut -c1-120)"
$PY probe3c.py --resume --dry-run --ack-operator --run-id p3c0_dryrun --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun3 --proof-dir /dev/shm/selftest3c/pd --keep-root /mnt/d/hadwiger/phase3c/selftest_keep > $ST/dryrun3b.log 2>&1; echo "resume with ack rc=$? (要 0): $(grep -E 'resume #|round 5' $ST/dryrun3b.log | head -2 | cut -c1-200)"
echo "== 5. status3c --once"; $PY status3c.py --once > $ST/status_once.md 2>&1; echo "rc=$?"; head -12 $ST/status_once.md | cut -c1-250
echo "== cleanup"; rm -rf /dev/shm/selftest3c /mnt/d/hadwiger/phase3c/selftest_keep; rm -f $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_*
rm -f /mnt/c/Users/user/Desktop/spindle/phase3c/status.md.tmp
echo "SELFTEST3C DONE $(date) FAIL=$FAIL"
