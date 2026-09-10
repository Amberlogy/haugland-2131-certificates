#!/bin/bash
# refinalize3e.sh 嘅背景部分: finalize3e → syncback → status 一次 (同 run3e.sh 收爐嗰半一樣)
set -u
PY=/home/user/hadwiger/venv/bin/python
P3E=/home/user/hadwiger/phase3e; cd "$P3E"
RUN=p3e1_step; R=$P3E/runs/$RUN
echo "[refinalize3e] start $(date)" >> "$R/run3e.log"
$PY finalize3e.py --run "$R" --workers 14 --frac 0.05 >> "$R/finalize3e.log" 2>&1; FRC=$?
echo "[refinalize3e] finalize3e rc=$FRC $(date)" >> "$R/run3e.log"
bash /mnt/c/Users/user/Desktop/spindle/phase3e/syncback3e.sh >> "$R/run3e.log" 2>&1
if [ "$FRC" != "0" ]; then
  echo "!! finalize3e rc=$FRC ($(date)) —— 獨立重驗唔過或者 crash; 睇 runs/$RUN/finalize3e.log 同 VERIFY_FAILED.md. 要人手睇." > "$P3E/STEP.txt"
  echo "[refinalize3e] !! FINALIZE3E rc=$FRC" >> "$R/run3e.log"
fi
pkill -f "status3e.py --interval" 2>/dev/null; sleep 1
$PY status3e.py --once > /dev/null 2>&1
bash /mnt/c/Users/user/Desktop/spindle/phase3e/syncback3e.sh >> "$R/run3e.log" 2>&1
echo "[refinalize3e] ALL DONE (finalize rc=$FRC) $(date)" >> "$R/run3e.log"
