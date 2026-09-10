#!/bin/bash
# Phase 3e 主流程 (由 launch3e.sh / resume3e.sh 用 setsid nohup 起, 幂等): probe3e → finalize3e (獨立重驗 + 封存 + 報告) → park
#   probe3e 停於操作員停機 (needs_operator) / PAUSE 就唔會自動重試; finalize3e rc≠0 (獨立重驗唔過) 就大聲講, 唔會扮完成
set -u
PY=/home/user/hadwiger/venv/bin/python
P3E=/home/user/hadwiger/phase3e; cd "$P3E"
RUN=p3e1_step; R=$P3E/runs/$RUN
SEED=/home/user/hadwiger/phase3c/runs/p3c1_shrink
BATCHES=/home/user/hadwiger/phase3b/batches_g2.json
KEEP=/mnt/d/hadwiger/phase3e/keep
PD=/dev/shm/$RUN
mkdir -p "$R" "$KEEP" "$PD"
echo "[run3e] start $(date)" >> "$R/run3e.log"
SKIP=0
if [ -f "$R/state.json" ]; then
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if (s.get('finished') and not s.get('paused')) else 1)" && SKIP=1
  $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('needs_operator') else 1)" && { echo "[run3e] state.needs_operator=True (上次係操作員停機), 唔自動 resume probe3e; 直接收爐" >> "$R/run3e.log"; SKIP=1; }
fi
if [ "$SKIP" = "1" ]; then
  echo "[run3e] probe3e 跳過 (finished / needs_operator) $(date)" >> "$R/run3e.log"
else
  if [ -f "$R/state.json" ]; then RES="--resume"; else RES=""; fi
  echo "[run3e] probe3e $RES $(date)" >> "$R/run3e.log"
  $PY probe3e.py $RES --run-id $RUN --seed-run $SEED --batches $BATCHES --out "$R" --rounds 6 --step 20 --min-step 5 --attempts-per-round 2 --workers 14 \
     --cap 21600 --extend 3600 --extend-eta-h 0.5 --total-cap 216000 --cpu-cap-h 500 --timeout 900 --depth 14 --proof-dir "$PD" --keep-root "$KEEP" >> "$R/probe3e.log" 2>&1
  echo "[run3e] probe3e rc=$? $(date)" >> "$R/run3e.log"
fi
if $PY -c "import json,sys; s=json.load(open('$R/state.json')); sys.exit(0 if s.get('paused') and not s.get('finished') else 1)" 2>/dev/null; then
  echo "[run3e] paused by operator, 唔收爐 $(date)" >> "$R/run3e.log"; exit 0
fi
# 收爐之前由 Windows 再抄一次收爐腳本 (probe3e 已經行完; 呢兩個檔要跑成日先用到, 容許中途修好)
cp /mnt/c/Users/user/Desktop/spindle/phase3e/finalize3e.py /mnt/c/Users/user/Desktop/spindle/phase3e/status3e.py "$P3E"/ 2>/dev/null
sed -i 's/\r$//' "$P3E/finalize3e.py" "$P3E/status3e.py" 2>/dev/null
echo "[run3e] finalize3e $(date)" >> "$R/run3e.log"
$PY finalize3e.py --run "$R" --workers 14 --frac 0.05 >> "$R/finalize3e.log" 2>&1; FRC=$?
echo "[run3e] finalize3e rc=$FRC $(date)" >> "$R/run3e.log"
bash /mnt/c/Users/user/Desktop/spindle/phase3e/syncback3e.sh >> "$R/run3e.log" 2>&1
if [ "$FRC" != "0" ]; then
  echo "!! finalize3e rc=$FRC ($(date)) —— 獨立重驗唔過或者 crash; 睇 runs/$RUN/finalize3e.log 同 VERIFY_FAILED.md. 要人手睇." > "$P3E/STEP.txt"
  echo "[run3e] !! FINALIZE3E rc=$FRC" >> "$R/run3e.log"
fi
pkill -f "status3e.py --interval" 2>/dev/null; sleep 1
$PY status3e.py --once > /dev/null 2>&1
bash /mnt/c/Users/user/Desktop/spindle/phase3e/syncback3e.sh >> "$R/run3e.log" 2>&1
echo "[run3e] ALL DONE (finalize rc=$FRC) $(date); procs: $(pgrep -fa 'kissat|cnc2|drat-trim|march_cu|probe3e|finalize3e|cake_lpr' | grep -v pgrep | wc -l)" >> "$R/run3e.log"
