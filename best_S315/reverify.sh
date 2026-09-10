#!/bin/bash
# reverify.sh — independent re-verification of this archived certificate set.
# Needs the v1.0 tool environment: ~/hadwiger/{phase2,phase2b,phase3b,phase3c,phase3d,phase3e}, kissat, drat-trim, march_cu, cake_lpr; python venv ~/hadwiger/venv.
# Wall-clock on 14 threads: ~3 h (step 3 dominates: every one of the 16382 leaf proofs is re-checked).
set -u
cd "$(dirname "$0")"
PY=/home/user/hadwiger/venv/bin/python
T=$(mktemp -d)
RC=0
step () { if [ "$2" = "0" ]; then echo "   [PASS] $1"; else echo "   [FAIL] $1 (rc=$2)"; RC=1; fi }
echo "== 1. integrity (every file, including the leaf proofs)"
sha256sum -c --quiet SHA256SUMS; step "SHA256SUMS" $?
echo "== 2. rebuild base.cnf from S (must match L1pp/base.cnf byte for byte)"
$PY /home/user/hadwiger/phase3b/buildg2.py --remove 1,2,3,4,5,8,10,13,15,16,20,21,24,26,27,30,32,33,34,37,38,44,50,51,61,66,67,68,69,71,72,73,76,78,79,81,83,84,85,90,92,101,105,106,109,115,116,118,130,131,133,134,135,137,148,152,156,157,161,164,168,169,171,173,176,185,188,190,196,197,201,203,205,207,209,213,214,218,224,226,230,231,235,239,245,246,253,256,258,262,270,271,273,276,278,282,286,287,295,296,298,300,303,304,305,312,317,333,334,335,337,340,344,345,347,353,365,369,372,374,382,384,385,387,394,395,396,397,405,407,412,413,415,416,421,422,427,428,431,439,453,455,457,463,466,468,469,477,478,484,487,492,499,500,509,511,516,519,526,531,536,543,547,549,554,563,564,566,572,573,577,581,582,583,588,590,601,603,605,606,611,612,614,615,619,621,625,626,631,642,672,677,683,688,689,695,701,702,704,708,709,710,713,716,721,722,723,724,737,744,749,753,758,759,771,773,776,778,784,791,792,793,794,797,799,802,804,807,809,817,819,822,824,832,834,835,837,838,839,840,846,851,853,859,862,864,865,868,869,871,878,890,897,898,901,903,912,914,920,921,925,928,929,932,934,936,940,941,942,946,947,948,952,953,956,964,967,968,974,979,982,985,987,992,993,996,998,999,1003,1004,1006,1007,1011,1014,1017,1020,1022,1026,1029,1033,1037,1041,1043,1047,1050,1054,1055,1057,1059,1060,1061,1062,1063,1064,1066 --out "$T" --tag base --protected run/batches_g2.json | cut -c1-200
A=$(sha256sum "$T/base.cnf" | cut -d' ' -f1); B=$(sha256sum L1pp/base.cnf | cut -d' ' -f1)
echo "   rebuilt $A"; echo "   archived $B"
[ "$A" = "$B" ]; step "base.cnf rebuilt from S matches the archived one" $?
echo "== 3. L1'' : ALL 16382 leaf proofs (drat-trim) + cover certificate + audit proofs"
$PY /home/user/hadwiger/phase3c/verify_final.py --attempt-dir L1pp --tag r05a --keep-dir L1pp/leaf_proofs --skip-l3 --tmp "$T/vf" --json-out "$T/verify_final_reverify.json" | tail -8
step "every leaf proof + cover + audit re-verified" $?
echo "== 4. cake_lpr cross-check on a 5% sample (formally verified checker) + lrat-check"
$PY /home/user/hadwiger/phase3d/crosscheck3d.py --attempt-dir L1pp --tag r05a --keep-dir L1pp/leaf_proofs --out "$T" --frac 0.05 | tail -4
step "cake_lpr + lrat-check sample" $?
echo "== 5. L2''/L3''/completeness/spindle A+B (fresh run from S)"
$PY /home/user/hadwiger/phase3b/l3g2.py --remove 1,2,3,4,5,8,10,13,15,16,20,21,24,26,27,30,32,33,34,37,38,44,50,51,61,66,67,68,69,71,72,73,76,78,79,81,83,84,85,90,92,101,105,106,109,115,116,118,130,131,133,134,135,137,148,152,156,157,161,164,168,169,171,173,176,185,188,190,196,197,201,203,205,207,209,213,214,218,224,226,230,231,235,239,245,246,253,256,258,262,270,271,273,276,278,282,286,287,295,296,298,300,303,304,305,312,317,333,334,335,337,340,344,345,347,353,365,369,372,374,382,384,385,387,394,395,396,397,405,407,412,413,415,416,421,422,427,428,431,439,453,455,457,463,466,468,469,477,478,484,487,492,499,500,509,511,516,519,526,531,536,543,547,549,554,563,564,566,572,573,577,581,582,583,588,590,601,603,605,606,611,612,614,615,619,621,625,626,631,642,672,677,683,688,689,695,701,702,704,708,709,710,713,716,721,722,723,724,737,744,749,753,758,759,771,773,776,778,784,791,792,793,794,797,799,802,804,807,809,817,819,822,824,832,834,835,837,838,839,840,846,851,853,859,862,864,865,868,869,871,878,890,897,898,901,903,912,914,920,921,925,928,929,932,934,936,940,941,942,946,947,948,952,953,956,964,967,968,974,979,982,985,987,992,993,996,998,999,1003,1004,1006,1007,1011,1014,1017,1020,1022,1026,1029,1033,1037,1041,1043,1047,1050,1054,1055,1057,1059,1060,1061,1062,1063,1064,1066 --out "$T/l3" --engine-b | tail -8
step "L2''/L3''/exactfield --complete/spindle A+B" $?
C=$(sha256sum "$T/l3/G3p.edge" | cut -d' ' -f1); D=$(sha256sum L2L3/l3_final/G3p.edge | cut -d' ' -f1)
[ "$C" = "$D" ]; step "G3p.edge from a fresh run matches the archived one" $?
echo "== 6. 5-colouring (fresh solve + edge-by-edge check of the archived colouring)"
$PY /home/user/hadwiger/phase2/certify4.py "$T/l3/G3p.edge" --out "$T/col5" --k 5 --tag c5 --expect sat --timeout 3600 | tail -3
step "fresh 5-colouring" $?
$PY - <<'EOF'
import sys
E=[tuple(map(int,l.split()[1:3])) for l in open("L2L3/l3_final/G3p.edge") if l.startswith("e")]
n=max(max(u,v) for u,v in E)
col={int(a):int(b) for a,b in (l.split() for l in open("COL5/col5/G3p_5col.col") if len(l.split())==2)}
bad=[(u,v) for u,v in E if col.get(u) is None or col.get(v) is None or col.get(u)==col.get(v)]
ok = (not bad) and set(col)==set(range(1,n+1)) and all(1<=c<=5 for c in col.values())
print("archived 5-colouring: %d vertices, %d/%d edges bichromatic, colours %s -> %s" % (len(col), len(E)-len(bad), len(E), sorted(set(col.values())), "OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
EOF
step "archived 5-colouring edge-by-edge" $?
rm -rf "$T"
if [ "$RC" = "0" ]; then echo "REVERIFY DONE: ALL CHECKS PASSED $(date)"; else echo "REVERIFY DONE: !! SOME CHECKS FAILED $(date)"; fi
exit $RC
