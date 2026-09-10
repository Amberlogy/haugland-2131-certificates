#!/bin/bash
# 只重跑 selftest 第 3–4 部 (probe3c --dry-run + finalize3c --dry-run), 用嚟驗 finalize3c 修補
set -u
PY=/home/user/hadwiger/venv/bin/python
P=/home/user/hadwiger/phase3c; cd "$P"; ST=$P/selftest; mkdir -p "$ST" /dev/shm/selftest3c /mnt/d/hadwiger/phase3c/selftest_keep
rm -rf $ST/dryrun
$PY probe3c.py --dry-run --run-id p3c0_dryrun --seed-run /home/user/hadwiger/phase3b/runs/p3br1_shrink --batches /home/user/hadwiger/phase3b/batches_g2.json --out $ST/dryrun --rounds 30 --workers 14 --cap 12600 --total-cap 144000 --cpu-cap-h 400 --proof-dir /dev/shm/selftest3c/pd --keep-root /mnt/d/hadwiger/phase3c/selftest_keep > $ST/dryrun.log 2>&1; echo "probe3c dry-run rc=$?"
$PY finalize3c.py --run $ST/dryrun --workers 14 --dry-run > $ST/finalize_dryrun.log 2>&1; echo "finalize3c dry-run rc=$?"
cut -c1-300 $ST/finalize_dryrun.log | tail -16
echo "-- 報告 最終認證圖 段:"; sed -n '/## 最終認證圖/,/## 封存清單/p' $ST/phase3c_results_dryrun.md | cut -c1-500
echo "-- MEMORY index:"; grep "Hadwiger project" $P/mem_dryrun_MEMORY.md | cut -c1-600
echo "-- probe_unfinished flag (dry-run state 有 finished? $(python3 -c "import json;print(bool(json.load(open('$ST/dryrun/state.json')).get('finished')))")):"; grep -c "未正常結束" $ST/finalize_dryrun.log
rm -rf /dev/shm/selftest3c /mnt/d/hadwiger/phase3c/selftest_keep; rm -f $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_*
echo "SELFTEST3C_FIN DONE $(date)"
