#!/bin/bash
# Phase 3b 收爐: 停 status3b (每 10 分鐘覆寫), 最後一次 status.md, 抄返 Windows, 確認冇背景 process
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
pkill -f "status3b.py --interval" 2>/dev/null; sleep 1
/home/user/hadwiger/venv/bin/python status3b.py --once > /dev/null
sed -i '1s/.*/# Phase 3b status —— 完成 (2026-09-07 04:15; 冇背景任務; 等 Amber 決定: 放寬成本上限續 G₂ \/ 收成 v1.1 \/ 寄 dense_udg_L.md)/' status.md
for d in phase3b phase4 phase3 phase2b; do cp status.md /mnt/c/Users/user/Desktop/spindle/$d/status.md; done
echo "== procs =="; pgrep -fa "kissat|cnc2|drat-trim|march_cu|probe3b|tail6|beam_udg|status3b" | grep -v -E "pgrep|tail -n0" | wc -l
echo "== proofs_ext4 leftovers =="; du -sh /home/user/hadwiger/phase2b/proofs_ext4/p3br1_shrink /home/user/hadwiger/phase2b/proofs_ext4/p3bt6_tail /home/user/hadwiger/phase2b/proofs_ext4/p3b_price 2>/dev/null
echo "== disk =="; df -h /mnt/d /mnt/c / | tail -3
bash /mnt/c/Users/user/Desktop/spindle/phase3b/syncback3b.sh | tail -1
head -8 status.md
echo "PARK3B DONE $(date)"
