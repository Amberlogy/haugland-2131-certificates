#!/bin/bash
# Phase 3d 主流程 (由 launch3d.sh / resume3d.sh 用 setsid nohup 起, 幂等): probe3d → finalize3d (獨立重驗 + 封存 + 報告) → park
#   probe3d 停於操作員停機 (needs_operator) / PAUSE 就唔會自動重試; finalize3d rc≠0 (獨立重驗唔過) 就大聲講, 唔會扮完成
set -u
PY=/home/user/hadwiger/venv/bin/python
P3D=/home/user/hadwiger/phase3d; cd "$P3D"
RUN=p3d1_final; R=$P3D/runs/$RUN
SEED=/home/user/hadwiger/phase3c/runs/p3c1_shrink
BATCHES=/home/user/hadwiger/phase3b/batches_g2.json
KEEP=/mnt/d/hadwiger/phase3d/keep
PD=/dev/shm/$RUN
mkdir -p "$R" "$KEEP" "$PD"
echo "[run3d] start $(date)" >> "$R/run3d.log"
SKIP=0
if [ -f "$R/state.json" ]; then
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if (s.get('finished') and not s.get('paused')) else 1)" && SKIP=1
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('needs_operator') else 1)" && { echo "[run3d] state.needs_operator=True (上次係操作員停機), 唔自動 resume probe3d; 直接收爐" >> "$R/run3d.log"; SKIP=1; }
fi
if [ "$SKIP" = "1" ]; then
  echo "[run3d] probe3d 跳過 (finished / needs_operator) $(date)" >> "$R/run3d.log"
else
  if [ -f "$R/state.json" ]; then RES="--resume"; else RES=""; fi
  echo "[run3d] probe3d $RES $(date)" >> "$R/run3d.log"
  $PY probe3d.py $RES --run-id $RUN --seed-run $SEED --batches $BATCHES --out "$R" --attempts 3 --target-removed 350 --workers 14 \
     --cap 28800 --extend 3600 --extend-eta-h 0.5 --total-cap 86400 --cpu-cap-h 160 --timeout 900 --depth 14 --proof-dir "$PD" --keep-root "$KEEP" >> "$R/probe3d.log" 2>&1
  echo "[run3d] probe3d rc=$? $(date)" >> "$R/run3d.log"
fi
if $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('paused') and not s.get('finished') else 1)" 2>/dev/null; then
  echo "[run3d] paused by operator, 唔收爐 $(date)" >> "$R/run3d.log"; exit 0
fi
echo "[run3d] finalize3d $(date)" >> "$R/run3d.log"
$PY finalize3d.py --run "$R" --workers 14 --frac 0.05 >> "$R/finalize3d.log" 2>&1; FRC=$?
echo "[run3d] finalize3d rc=$FRC $(date)" >> "$R/run3d.log"
bash /mnt/c/Users/user/Desktop/spindle/phase3d/syncback3d.sh >> "$R/run3d.log" 2>&1
if [ "$FRC" != "0" ]; then
  echo "!! finalize3d rc=$FRC ($(date)) —— 獨立重驗唔過或者 crash; 睇 runs/$RUN/finalize3d.log 同 VERIFY_FAILED.md. 要人手睇." > "$P3D/STEP.txt"
  echo "[run3d] !! FINALIZE3D rc=$FRC" >> "$R/run3d.log"
fi
pkill -f "status3d.py --interval" 2>/dev/null; sleep 1
$PY status3d.py --once > /dev/null 2>&1
bash /mnt/c/Users/user/Desktop/spindle/phase3d/syncback3d.sh >> "$R/run3d.log" 2>&1
echo "[run3d] ALL DONE (finalize rc=$FRC) $(date); procs: $(pgrep -fa 'kissat|cnc2|drat-trim|march_cu|probe3d|finalize3d|cake_lpr' | grep -v pgrep | wc -l)" >> "$R/run3d.log"
