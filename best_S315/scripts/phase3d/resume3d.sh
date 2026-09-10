#!/bin/bash
# Phase 3d 續跑 (跨晚 / 機器重啟 / PAUSE 之後): run3d.sh 見到 state.json 就 probe3d --resume; 已 finished 就直接收爐 (finalize3d 幂等)
# 上次係操作員停機 (needs_operator) 就要人手加 --ack-operator 跑 probe3d, 呢個腳本淨係會收爐
bash /mnt/c/Users/user/Desktop/spindle/phase3d/sync3d.sh > /dev/null
cd /home/user/hadwiger/phase3d
PY=/home/user/hadwiger/venv/bin/python
RUN=p3d1_final
STALE=$(pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|run3d|cake_lpr' | grep -v pgrep | wc -l)
if [ "$STALE" != "0" ]; then pgrep -fa 'kissat|drat-trim|cnc2|march_cu|probe3|finalize3|run3d|cake_lpr' | grep -v pgrep; echo "!! 有舊 process, 唔 resume"; exit 2; fi
if [ ! -f runs/$RUN/state.json ]; then echo "!! 冇 runs/$RUN/state.json —— 首跑用 launch3d.sh"; exit 3; fi
if ! mountpoint -q /mnt/d; then echo "!! /mnt/d 冇 mount"; exit 4; fi
mkdir -p /dev/shm/$RUN /mnt/d/hadwiger/phase3d/keep
rm -f runs/$RUN/PAUSE
echo "Phase 3d 續跑 (resume): $(python3 -c "import json;s=json.load(open('runs/$RUN/state.json'));print('已試', len([1]), '停:', (s.get('stop_reason') or '')[:120], '| S_acc', len(s['S_acc']), '| CPU', s.get('cpu_h_used'), '| best', (s.get('best') or {}).get('tag'))")" > STEP.txt
pkill -f "status3d.py --interval" 2>/dev/null
setsid nohup $PY status3d.py --interval 600 >> status3d.log 2>&1 &
setsid nohup bash /home/user/hadwiger/phase3d/run3d.sh >> runs/$RUN/run3d.nohup 2>&1 &
sleep 60
grep -E "resume|=====|march_cu|cnc2k 第|DONE|finalize|RECORD" runs/$RUN/probe3d.log | tail -5 | cut -c1-260; echo "kissat procs: $(pgrep -xc kissat)"; date
