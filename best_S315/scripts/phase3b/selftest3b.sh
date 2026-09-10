#!/bin/bash
# 修補版 (審查後) selftest: 先抄去臨時目錄 ~/hadwiger/phase3b_test 跑, 全過先同步到正式目錄 (probe3b 跑緊, 唔可以直接覆寫未測嘅版本)
set -u
PY=/home/user/hadwiger/venv/bin/python
T=/home/user/hadwiger/phase3b_test
rm -rf "$T"; mkdir -p "$T"
cp /mnt/c/Users/user/Desktop/spindle/phase3b/*.py "$T"/; sed -i 's/\r$//' "$T"/*.py
cd "$T"
echo "== 1. buildg2 selftest =="
$PY buildg2.py --selftest --out "$T/st_build" --protected /home/user/hadwiger/phase3b/batches_g2.json 2>&1 | tail -8 || { echo "!! buildg2 selftest FAIL"; exit 1; }
echo "== 2. l3g2 selftest =="
$PY l3g2.py --selftest --out "$T/st_l3" 2>&1 | tail -10 || { echo "!! l3g2 selftest FAIL"; exit 1; }
echo "== 3. l3g2 毒藥: S 越界 (1067) 必須被拒 =="
$PY l3g2.py --remove 1067 --out "$T/st_oob" > "$T/st_oob.log" 2>&1; rc=$?; grep -o "S 有越界/非整數索引: \[1067\]" "$T/st_oob.log" && echo "rc=$rc ✓ 被拒" || { echo "!! S=1067 冇被拒 (rc=$rc)"; tail -3 "$T/st_oob.log"; exit 1; }
echo "== 4. verify_colouring / read_col 色值毒藥 =="
$PY - <<'EOF'
import sys, os, tempfile
sys.path.insert(0, "/home/user/hadwiger/phase3b_test")
from g2common import G2, verify_colouring, read_col, write_col, K
g2 = G2()
# 合法基準: 每點色 = 1 除 u=2 (唔理邊, 只測值域邏輯) → bad_edges 會多, 但 bad_values 必須 0
col = {w: 1 for w in range(1, g2.n + 1)}; col[g2.u] = 2
v = verify_colouring(g2, [], col); assert v["bad_values"] == 0 and v["extra_vertices"] == 0, v
col[5] = 5; v = verify_colouring(g2, [], col); assert v["ok"] is False and v["bad_values"] == 1, v; print("  色值 5 → ok=False, bad_values=1 ✓")
col[5] = 0; v = verify_colouring(g2, [], col); assert v["ok"] is False and v["bad_values"] == 1, v; print("  色值 0 → ok=False ✓")
col[5] = 1; col[2000] = 1; v = verify_colouring(g2, [], col); assert v["ok"] is False and v["extra_vertices"] == 1, v; print("  越界頂點 2000 有色 → ok=False, extra_vertices=1 ✓")
del col[2000]; col[7] = 3; v = verify_colouring(g2, [7], col); assert v["extra_vertices"] == 1, v; print("  S 入面嘅頂點有色 → extra_vertices=1 ✓")
p = "/home/user/hadwiger/phase3b_test/poison.col"
open(p, "w").write("c 4-colouring of G2 minus [3] with col(-1,0) != col(1,0)\n172 5\n994 1\n")
try:
    read_col(p); raise SystemExit("!! read_col 收咗色值 5")
except AssertionError as e:
    print("  read_col 色值 5 被拒 ✓ (%s)" % str(e)[:50])
open(p, "w").write("c 4-colouring of G2 minus [3] with col(-1,0) != col(1,0)\n172 0\n994 1\n")
S, c = read_col(p); assert c[172] is None and c[994] == 1 and S == [3]; print("  read_col 色值 0 → None ✓")
print("[colour-value poison] 全部通過 ✓")
EOF
[ $? -eq 0 ] || { echo "!! 色值毒藥 FAIL"; exit 1; }
echo "== 5. probe3b / hardness_g2 / witness_g2 import + argparse smoke =="
$PY -c "import sys; sys.path.insert(0,'$T'); import probe3b, hardness_g2, witness_g2, stage_v11, tail6; print('imports OK')" || exit 1
$PY probe3b.py --help > /dev/null && $PY hardness_g2.py --help > /dev/null && echo "argparse OK"
echo "== ALL PASS → 同步到正式目錄 ~/hadwiger/phase3b =="
bash /mnt/c/Users/user/Desktop/spindle/phase3b/sync3b.sh > /dev/null && sha256sum /home/user/hadwiger/phase3b/l3g2.py /home/user/hadwiger/phase3b/g2common.py /home/user/hadwiger/phase3b/probe3b.py | cut -c1-16,65-
echo "SELFTEST3B DONE $(date)"
