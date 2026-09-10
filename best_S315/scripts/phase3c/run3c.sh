#!/bin/bash
# Phase 3c 主流程 (由 launch3c.sh / resume3c.sh 用 setsid nohup 起, 幂等):
#   probe3c (首跑 seed / 之後 --resume) → finalize3c (獨立重驗 + 封存 + 報告 + facts/DECISION/MEMORY) → s60_full (可選 ≤ 3 h) → finalize3c --append-s60 → park (停 status3c, 最後 status.md, syncback)
#   probe3c 停於操作員停機 (needs_operator) / PAUSE 就唔會自動重試 (審查 #16/#17); finalize3c 失敗 (rc≠0) 就唔跑 s60_full, STEP.txt 大聲講 (審查 #18)
set -u
PY=/home/user/hadwiger/venv/bin/python
P3C=/home/user/hadwiger/phase3c; cd "$P3C"
RUN=p3c1_shrink; R=$P3C/runs/$RUN
SEED=/home/user/hadwiger/phase3b/runs/p3br1_shrink
BATCHES=/home/user/hadwiger/phase3b/batches_g2.json
KEEP=/mnt/d/hadwiger/phase3c/keep
PD=/dev/shm/$RUN
mkdir -p "$R" "$KEEP" "$PD"
echo "[run3c] start $(date)" >> "$R/run3c.log"
# 1. probe3c (跳過條件: 已 finished 而且唔係 paused; 或者 needs_operator 未 ack)
SKIP=0
if [ -f "$R/state.json" ]; then
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if (s.get('finished') and not s.get('paused')) else 1)" && SKIP=1
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('needs_operator') else 1)" && { echo "[run3c] state.needs_operator=True (上次係操作員停機), 唔自動 resume probe3c; 直接收爐 (要續剪要人手 --ack-operator)" >> "$R/run3c.log"; SKIP=1; }
fi
if [ "$SKIP" = "1" ]; then
  echo "[run3c] probe3c 跳過 (finished / needs_operator) $(date)" >> "$R/run3c.log"
else
  if [ -f "$R/state.json" ]; then RES="--resume"; else RES=""; fi
  echo "[run3c] probe3c $RES $(date)" >> "$R/run3c.log"
  $PY probe3c.py $RES --run-id $RUN --seed-run $SEED --batches $BATCHES --out "$R" --rounds 30 --workers 14 --cap 12600 --total-cap 144000 --cpu-cap-h 400 --timeout 600 --depth 14 --k 30 --proof-dir "$PD" --keep-root "$KEEP" --low-net 10 --low-net-rounds 3 >> "$R/probe3c.log" 2>&1
  echo "[run3c] probe3c rc=$? $(date)" >> "$R/run3c.log"
fi
# PAUSE 旗 (操作員暫停) → 唔收爐, 等 resume3c.sh
if $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('paused') and not s.get('finished') else 1)" 2>/dev/null; then
  echo "[run3c] paused by operator, 唔收爐 $(date)" >> "$R/run3c.log"; exit 0
fi
# 2. finalize3c (幂等; rc≠0 = 獨立重驗唔過 / crash → 唔跑 s60, 大聲講)
echo "[run3c] finalize3c $(date)" >> "$R/run3c.log"
$PY finalize3c.py --run "$R" --workers 14 --expect-s60 >> "$R/finalize3c.log" 2>&1; FRC=$?
echo "[run3c] finalize3c rc=$FRC $(date)" >> "$R/run3c.log"
bash /mnt/c/Users/user/Desktop/spindle/phase3c/syncback3c.sh >> "$R/run3c.log" 2>&1
if [ "$FRC" != "0" ]; then
  echo "!! finalize3c FAILED rc=$FRC ($(date)) —— 獨立重驗唔過或者 crash; 睇 runs/$RUN/finalize3c.log / VERIFY_FAILED.md; 唔跑 s60_full. 要人手睇." > "$P3C/STEP.txt"
  echo "[run3c] !! FINALIZE3C FAILED rc=$FRC, 跳過 s60_full" >> "$R/run3c.log"
else
  # 3. 可選: S60_full 補封存 (≤ 3 h; 只跑一次, 未完就保留 keep 目錄等人手決定)
  if [ ! -f "$P3C/s60_full/s60_full.json" ]; then
    echo "[run3c] s60_full $(date)" >> "$R/run3c.log"
    $PY s60_full.py --cap 10800 --workers 14 >> "$P3C/s60_full.log" 2>&1
    echo "[run3c] s60_full rc=$? $(date)" >> "$R/run3c.log"
  fi
  if [ -f "$P3C/s60_full/s60_full.json" ]; then
    $PY finalize3c.py --run "$R" --append-s60 "$P3C/s60_full/s60_full.json" >> "$R/finalize3c.log" 2>&1
    echo "[run3c] append-s60 rc=$? $(date)" >> "$R/run3c.log"
  fi
fi
# 4. park
pkill -f "status3c.py --interval" 2>/dev/null; sleep 1
$PY status3c.py --once > /dev/null 2>&1
bash /mnt/c/Users/user/Desktop/spindle/phase3c/syncback3c.sh >> "$R/run3c.log" 2>&1
echo "[run3c] ALL DONE (finalize rc=$FRC) $(date); procs: $(pgrep -fa 'kissat|cnc2|drat-trim|march_cu|probe3c|finalize3c|s60_full' | grep -v pgrep | wc -l)" >> "$R/run3c.log"
