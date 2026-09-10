#!/bin/bash
# Phase 3b 第 1 步保險: round 1 CNF (S = batch 1, 30 粒) 抽樣定價 (cubes.py: march d=14 → 抽 30 cube kissat T=600, 14 workers) → E_floor 一張證書幾耐
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
PY=/home/user/hadwiger/venv/bin/python
mkdir -p price/r01 /home/user/hadwiger/phase2b/proofs_ext4/p3b_price
$PY buildg2.py --batches /home/user/hadwiger/phase3b/batches_g2.json --round 1 --out /home/user/hadwiger/phase3b/price/r01 --tag base
$PY /home/user/hadwiger/phase2b/cubes.py --cnf /home/user/hadwiger/phase3b/price/r01/base.cnf --out /home/user/hadwiger/phase3b/price/r01/sample --depths 14 --sample 30 --timeout 600 --workers 14 --solver kissat --proof-dir /home/user/hadwiger/phase2b/proofs_ext4/p3b_price --binary --campaign-workers 14 --seed 20260906 2>&1 | grep -v "^  \[d14_"
echo "=== summary.md ==="; cat /home/user/hadwiger/phase3b/price/r01/sample/summary.md
echo "PRICE DONE $(date)"
