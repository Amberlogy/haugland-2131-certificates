#!/bin/bash
# Windows phase3d 源碼 → WSL ~/hadwiger/phase3d (源頭喺 Windows); 只同步 .py / .sh (json 結果由 WSL 生成, 用 syncback3d.sh 抄返)
mkdir -p /home/user/hadwiger/phase3d/runs
cp /mnt/c/Users/user/Desktop/spindle/phase3d/*.py /home/user/hadwiger/phase3d/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3d/*.sh /home/user/hadwiger/phase3d/ 2>/dev/null
sed -i 's/\r$//' /home/user/hadwiger/phase3d/*.py /home/user/hadwiger/phase3d/*.sh 2>/dev/null
chmod +x /home/user/hadwiger/phase3d/*.py /home/user/hadwiger/phase3d/*.sh 2>/dev/null
ls /home/user/hadwiger/phase3d/
