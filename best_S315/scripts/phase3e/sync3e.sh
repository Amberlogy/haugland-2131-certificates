#!/bin/bash
# Windows phase3e 源碼 → WSL ~/hadwiger/phase3e (源頭喺 Windows); 只同步 .py / .sh (json 結果由 WSL 生成, 用 syncback3e.sh 抄返)
mkdir -p /home/user/hadwiger/phase3e/runs
cp /mnt/c/Users/user/Desktop/spindle/phase3e/*.py /home/user/hadwiger/phase3e/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3e/*.sh /home/user/hadwiger/phase3e/ 2>/dev/null
sed -i 's/\r$//' /home/user/hadwiger/phase3e/*.py /home/user/hadwiger/phase3e/*.sh 2>/dev/null
chmod +x /home/user/hadwiger/phase3e/*.py /home/user/hadwiger/phase3e/*.sh 2>/dev/null
ls /home/user/hadwiger/phase3e/
