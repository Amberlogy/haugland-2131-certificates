#!/bin/bash
# Re-verification driver for the release.
#   bash rerun.sh                 quick layer: this directory only (seconds to a few minutes)
#   bash rerun.sh --full BUNDLE   full layer: BUNDLE = extracted Zenodo archive (bundle/); runs its verify_bundle.py on all 14786 leaves (~12 min on 14 cores)
# Tools: set KISSAT / DRATTRIM / PY in the environment if they are not at the default paths below.
set -u
cd "$(dirname "$0")"
PY=${PY:-python3}
DRATTRIM=${DRATTRIM:-$HOME/hadwiger/drat-trim/drat-trim}
KISSAT=${KISSAT:-$HOME/hadwiger/kissat/build/kissat}
WORKERS=${WORKERS:-14}
if [ "${1:-}" = "--full" ]; then
  B="${2:?usage: bash rerun.sh --full /path/to/bundle}"
  echo "== full layer: $B =="
  (cd "$B" && sha256sum -c SHA256SUMS --quiet && echo "[sha256] all files of the archive match") || { echo "!! SHA256SUMS mismatch in $B"; exit 1; }
  $PY "$B/scripts/verify_bundle.py" --bundle "$B" --workers "$WORKERS" --python "$PY"
  exit $?
fi
fail=0
ok() { echo "[$1] OK  $2"; }
bad() { echo "[$1] !! FAIL  $2"; fail=1; }
T0=$(date +%s)
echo "== quick layer (GitHub layer only) == $(date)"
echo "python: $($PY --version 2>&1); drat-trim: $DRATTRIM; kissat: $KISSAT"
# Dependency check before anything else.  Steps 1 and 2 import numpy, and
# without it they fail with a bare ModuleNotFoundError buried in the output --
# which reads like a broken certificate rather than a missing package.
missing=""
for m in numpy; do
  $PY -c "import $m" >/dev/null 2>&1 || missing="$missing $m"
done
if [ -n "$missing" ]; then
  echo "!! $PY is missing:$missing"
  echo "   Steps 1 and 2 (rebuild from the paper; exact-field completeness) need them."
  echo "   Install with:   $PY -m pip install$missing"
  echo "   Or point PY at an interpreter that has them:   PY=/path/to/python bash rerun.sh"
  echo "   Everything else below still runs."
fi
# 0. sha256
if sha256sum -c SHA256SUMS --quiet; then ok 0 "SHA256SUMS: $(wc -l < SHA256SUMS) files match"; else bad 0 "SHA256SUMS"; fi
# 1. rebuild from the paper
rm -rf rebuild; mkdir -p rebuild
t=$(date +%s)
if $PY scripts/haugland.py --out rebuild --paths scripts/refs/appendixA_paths.json > rebuild/haugland.log 2>&1; then
  tail -1 rebuild/haugland.log
  same=1
  for f in G1.cvtx G1.edge G3.cvtx G3.edge; do
    a=$(sha256sum rebuild/$f | cut -c1-64); b=$(sha256sum inputs/$f | cut -c1-64)
    [ "$a" = "$b" ] || { same=0; echo "   rebuild/$f sha $a != inputs/$f sha $b"; }
  done
  [ $same = 1 ] && ok 1 "haugland.py rebuilt G1/G3 from the paper in $(( $(date +%s) - t )) s; G1.cvtx G1.edge G3.cvtx G3.edge byte-identical to inputs/" || bad 1 "rebuilt graph files differ from inputs/"
else
  bad 1 "haugland.py failed: $(tail -3 rebuild/haugland.log)"
fi
# 2. exact + complete
for g in G1 G3; do
  t=$(date +%s)
  if out=$($PY scripts/exactfield.py check inputs/$g.cvtx inputs/$g.edge --complete 2>&1); then ok 2 "$g: $(echo "$out" | tail -1) [$(( $(date +%s) - t )) s]"; else bad 2 "$g: $(echo "$out" | tail -2)"; fi
done
# 3. spindle-free (engine A)
t=$(date +%s)
out=$($PY scripts/spindlefind.py enumerate inputs/G3.edge 2>&1)
if echo "$out" | grep -q "Moser spindle copies = 0"; then ok 3 "$out [$(( $(date +%s) - t )) s]"; else bad 3 "$out"; fi
# 4. L1_a rebuild
if $PY scripts/l1enc.py build --edge inputs/G1.edge --cvtx inputs/G1.cvtx --variant a --out rebuild --tag rebuild_a > rebuild/l1enc.log 2>&1; then
  a=$(sha256sum rebuild/rebuild_a.cnf | cut -c1-64); b=$(sha256sum L1/L1_a.cnf | cut -c1-64)
  [ "$a" = "$b" ] && ok 4 "L1_a.cnf rebuilt from inputs/G1.*: sha256 ${a:0:16}… == L1/L1_a.cnf" || bad 4 "L1_a.cnf sha $a != $b"
else bad 4 "l1enc.py failed: $(tail -2 rebuild/l1enc.log)"; fi
# 5. cover
t=$(date +%s)
if "$DRATTRIM" cubes/cover_pure.cnf cubes/cover_pure.drat 2>&1 | tr -d '\r' | grep -qx "s VERIFIED"; then ok 5 "drat-trim cover_pure: s VERIFIED ($(grep -c ' 0$' cubes/cover_pure.cnf) negated cubes) [$(( $(date +%s) - t )) s]"; else bad 5 "cover_pure NOT VERIFIED"; fi
n_icnf=$(grep -c '^a ' cubes/cubes.icnf); n_cov=$(grep -vc '^p' cubes/cover_pure.cnf)
[ "$n_icnf" = "$n_cov" ] && ok 5b "cubes.icnf has $n_icnf cubes == $n_cov cover clauses" || bad 5b "cube count $n_icnf != cover clauses $n_cov"
# 6. L2 + L3 via chain.py (needs kissat at the path inside scripts/certify4.py)
t=$(date +%s)
if $PY scripts/chain.py --haugland inputs --out rebuild/chain > rebuild/chain.log 2>&1; then
  grep -E '^\[L2\] copy|^\[L3\]' rebuild/chain.log | sed 's/^/   /'
  if $PY - <<'EOF'
import json
a = json.load(open("rebuild/chain/pairs.json"))["pairs"]; b = json.load(open("L2/pairs.json"))["pairs"]
raise SystemExit(0 if a == b else 1)
EOF
  then ok 6 "chain.py: L2 copy maps reproduce L2/pairs.json; L3 re-solved and re-checked [$(( $(date +%s) - t )) s]"; else bad 6 "pairs.json differs"; fi
else bad 6 "chain.py failed: $(tail -3 rebuild/chain.log)"; fi
# 7. L3 drat-trim on the shipped certificate + lemma clauses present
if "$DRATTRIM" L3/L3.cnf L3/L3.drat 2>&1 | tr -d '\r' | grep -qx "s VERIFIED"; then
  if $PY - <<'EOF'
import json
pairs = json.load(open("L2/pairs.json"))["pairs"]
lem = {tuple(sorted((-((pairs[k]["A"] - 1) * 4 + c), -((pairs[k]["B"] - 1) * 4 + c)))) for k in pairs for c in range(1, 5)}
have = set()
for line in open("L3/L3.cnf"):
    t = line.split()
    if t and t[0] != "p" and len(t) == 3:
        have.add(tuple(sorted((int(t[0]), int(t[1])))))
raise SystemExit(0 if lem <= have else 1)
EOF
  then ok 7 "drat-trim L3: s VERIFIED; the 16 lemma clauses from L2/pairs.json are present in L3.cnf"; else bad 7 "lemma clauses missing from L3.cnf"; fi
else bad 7 "L3 NOT VERIFIED"; fi
# 8. 5-colouring
if $PY - <<'EOF'
import sys
sys.path.insert(0, "scripts")
from exactfield import load_edges
n, E = load_edges("inputs/G3.edge")
col = {}
for line in open("extra/G3-5.col"):
    t = line.split()
    if len(t) == 2 and t[0].isdigit():
        col[int(t[0])] = int(t[1])
bad = [(u, v) for u, v in E if col[u] == col[v]]
print("   G3-5.col: %d vertices, %d colours, %d/%d edges bichromatic" % (len(col), len(set(col.values())), len(E) - len(bad), len(E)))
raise SystemExit(0 if len(col) == n and not bad and len(set(col.values())) <= 5 else 1)
EOF
then ok 8 "5-colouring checked edge by edge"; else bad 8 "5-colouring check failed"; fi
echo "== quick layer done: $([ $fail = 0 ] && echo ALL OK || echo SOME CHECKS FAILED) in $(( $(date +%s) - T0 )) s == $(date)"
echo "   (the 14786 leaf proofs of L1 and the spindle-freeness DRAT are in the Zenodo layer: bash rerun.sh --full /path/to/bundle)"
exit $fail
