#!/bin/bash
# 只重跑 selftest 第 5 部 (finalize3d --dry-run), 用嚟驗 finalize3d 修補
set -u
PY=/home/user/hadwiger/venv/bin/python
P=/home/user/hadwiger/phase3d; ST=$P/selftest; cd "$P"
$PY finalize3d.py --run $ST/dryrun --workers 14 --dry-run > $ST/finalize_dryrun2.log 2>&1; echo "finalize3d dry-run2 rc=$?"
tail -6 $ST/finalize_dryrun2.log | cut -c1-220
echo "-- MEMORY index:"; grep "Hadwiger project" $P/mem_dryrun_MEMORY.md | cut -c1-420
echo "-- hadwiger-project 新段:"; grep -o "\*\*Phase 3d(.\{0,220\}" $P/mem_dryrun_hadwiger-project.md | head -1
echo "-- no-spindle 新段:"; grep -o "\*\*Phase 3d(.\{0,200\}" $P/mem_dryrun_no-spindle-hardness.md | head -1
echo "-- facts:"; $PY -c "import json; f=json.load(open('$P/facts_dryrun.json'))['facts']; print(len(f), [k for k in f if k.startswith('g2shrink3d')])"
echo "-- 真檔冇被改 (要 0 0 0):"; grep -c "Phase 3d" /mnt/c/Users/user/Desktop/spindle/phase2b/DECISION.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/hadwiger-project.md /mnt/c/Users/user/.claude/projects/C--Users-user-Desktop-spindle/memory/MEMORY.md
rm -f $P/facts_dryrun.json $P/DECISION_dryrun.md $P/mem_dryrun_*
echo "SELFTEST3D_FIN DONE $(date)"
