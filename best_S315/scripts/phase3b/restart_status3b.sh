#!/bin/bash
# 重啟 status3b.py (每 10 分鐘覆寫 status.md); 唔掂 probe3b / cnc2
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null
cd /home/user/hadwiger/phase3b
pkill -f "status3b.py --interval" 2>/dev/null; sleep 1
setsid nohup /home/user/hadwiger/venv/bin/python status3b.py --interval 600 >> status3b.log 2>&1 &
sleep 3; pgrep -fa "status3b.py --interval" | grep -v pgrep | wc -l; head -25 status.md | tail -6
