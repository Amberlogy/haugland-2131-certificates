# reduction_blocked — the three batches that cannot be deleted

Deleting the first batch of 30 vertices from G1 keeps the pair property
(`reduction_S30/`), and so does the first two batches together, 60 vertices
(`reduction_S60/`). The **third** batch does not, and neither does either half of it.
This directory holds the machine-checkable evidence for that.

A blocked batch is certified by a **witness colouring**, not by an UNSAT proof: a
proper 4-colouring of G1 − S in which A and B receive the *same* colour. Such a
colouring exists exactly when G1 − S has lost the pair property, so S cannot be
deleted as a whole. Checking one needs no solver — read the colouring, check every
edge is bichromatic, check col(A) = col(B).

## The three witnesses

| directory | |S| | witness | proper 4-colouring? | col(A) = col(B)? | minimal blocking set B | \|B\| |
|---|---|---|---|---|---|---|
| `blocked_90/` | 90 | `G1minus_90v.col` | yes, 3929 edges checked, 0 bad | yes, both colour 1 | 221, 295, 417, 591, 610, 615, 675, 732 | **8** |
| `blocked_75a/` | 75 | `G1minus_75v.col` | yes, 3901 edges checked, 0 bad | yes, both colour 1 | 72, 121, 141, 370, 371, 373, 422, 495, 529, 531, 563, 616 | **12** |
| `blocked_75b/` | 75 | `G1minus_75v.col` | yes, 3936 edges checked, 0 bad | yes, both colour 1 | 257, 272, 397, 446, 584, 597, 692 | **7** |

`witness/witness_blocked.json` is the machine record of all three checks
(`verified: true`, `bad_edges: 0`, `col_A`, `col_B`, the blocking set, and the degree
of each of its vertices). The `witness/*_minus_blocked.col` files are the same
colourings after greedily re-inserting as many of the deleted vertices as possible:
what survives is the smaller set B in the table, so **B itself cannot be deleted as a
whole** — a sharper statement than "this batch of 75 or 90 is blocked".

The 8, 12 and 7 in the last column are the three numbers the note quotes.

## Checking a witness by hand

```bash
# rebuild G1 - S from the vertex list in <dir>/base.json, then, for the colouring:
#   every edge bichromatic, col(A) = col(B), every colour in 1..4, every vertex coloured
python3 best_S315/scripts/phase3b/witness_g2.py --col blocked_90/G1minus_90v.col
```

`<dir>/base.json` records S and the sha256 of the CNF, coordinate and edge files, so
the graph being coloured is pinned. `<dir>/G1minus_*v.json` records the run that
found the colouring.

## What is here, and what is not

Each `blocked_*/` directory also carries the inputs and the partial cube run that
found the SAT answer: `base.cnf`, `cubes_d14.icnf`, `cnc/state.json` (the cubes that
were solved before a satisfiable one appeared), `cnc/ledger.csv`, and the logs.

There are **no DRAT proofs** in this directory and none are possible: the claim here
is satisfiability, and its certificate is the colouring itself. Nothing is withheld.

`SHA256SUMS` covers every file here.
