#!/bin/bash
# Windows phase3c 源碼 → WSL ~/hadwiger/phase3c (源頭喺 Windows); 只同步 .py / .sh / .diff (json 結果由 WSL 生成, 用 syncback3c.sh 抄返)
mkdir -p /home/user/hadwiger/phase3c/runs
cp /mnt/c/Users/user/Desktop/spindle/phase3c/*.py /home/user/hadwiger/phase3c/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3c/*.sh /home/user/hadwiger/phase3c/ 2>/dev/null
cp /mnt/c/Users/user/Desktop/spindle/phase3c/*.diff /home/user/hadwiger/phase3c/ 2>/dev/null
sed -i 's/\r$//' /home/user/hadwiger/phase3c/*.py /home/user/hadwiger/phase3c/*.sh /home/user/hadwiger/phase3c/*.diff 2>/dev/null
chmod +x /home/user/hadwiger/phase3c/*.py /home/user/hadwiger/phase3c/*.sh 2>/dev/null
ls /home/user/hadwiger/phase3c/
