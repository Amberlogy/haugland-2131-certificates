#!/bin/bash
# 第 4 步補強: L 細 n 高 α run (alpha 2000, nmax 40, 2 restarts, cap 25 min) — 測試 n=13..40 輸俾 Moser 係咪只係 beam 唔夠闊
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
mkdir -p beam/runC
setsid nohup nice -n 19 $PY beam_udg.py --lattice L --out /home/user/hadwiger/phase3b/beam/runC --alpha 2000 --m 24 --nmax 40 --restarts 2 --time-cap 1500 --seed 11 > beam/runC/run_L.out 2>&1 &
sleep 20; tail -2 beam/runC/beam_L.log | cut -c1-140; date
