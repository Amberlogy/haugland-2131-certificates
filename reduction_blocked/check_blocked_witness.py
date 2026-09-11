"""Check a blocked-batch witness colouring from the shipped files alone.

reduction_blocked/README.md tells the reader to run

    python3 best_S315/scripts/phase3b/witness_g2.py --col blocked_90/G1minus_90v.col

which cannot work: witness_g2.py is missing the required --out, its script path
is relative to the repository root while blocked_90/ is relative to
reduction_blocked/, and above all it builds G2 (asserting 1066 vertices and
6264 edges) while these witnesses are colourings of G1 - S (740 vertices,
3985 edges). Supplying --out only gets you

    AssertionError: 染色頂點集 != V(G₂) − S

There is no G1 counterpart to witness_g2.py in the repository.

This is the check the README's own comment describes -- every edge bichromatic,
col(A) = col(B), every colour in 1..4, every vertex coloured -- done from the
deposited files with nothing but the standard library. Run from
reduction_blocked/:

    python3 check_blocked_witness.py blocked_90
"""
import glob
import json
import sys


def check(d):
    b = json.load(open(d + "/base.json"))
    S, A, B = set(b["removed"]), b["A"], b["B"]
    cf = glob.glob(d + "/G1minus_*v.col")[0]
    col = {}
    for line in open(cf):
        t = line.split()
        if line.startswith("c") or len(t) != 2:
            continue
        col[int(t[0])] = int(t[1])
    E = [tuple(map(int, l.split()[1:3]))
         for l in open("../inputs/G1.edge") if l.startswith("e")]
    V = set(range(1, b["n"] + 1)) - S
    Ein = [(u, v) for u, v in E if u not in S and v not in S]
    bad = [(u, v) for u, v in Ein
           if col.get(u) is None or col.get(u) == col.get(v)]
    ok = (not bad and set(col) == V and col[A] == col[B]
          and all(1 <= c <= 4 for c in col.values()))
    print("  %-12s %d vertices coloured (expected %d) | colours %s | "
          "%d/%d edges bichromatic | col(A)=col(B) %s | %s"
          % (d, len(col), len(V), sorted(set(col.values())),
             len(Ein) - len(bad), len(Ein), col[A] == col[B],
             "OK" if ok else "FAILED"))
    return ok


if __name__ == "__main__":
    dirs = sys.argv[1:] or ["blocked_75a", "blocked_75b", "blocked_90"]
    sys.exit(0 if all([check(d) for d in dirs]) else 1)
