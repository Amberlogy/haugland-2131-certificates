# reduction_S60 — the Proposition 2 certificate for G1 − S₆₀

This directory holds the **metadata layer** of the cube-and-conquer certificate that
G1 − S₆₀ has the pair property, which with the L2′/L3′ assembly in
`l3_phase3_round2/` certifies that G3′ (1891 vertices) is not 4-colourable —
Proposition 2 of the note.

`S60_README.md` is the archive's own record, written by the run that produced it.
Its title carries the label `(NOT released)` because at the time of writing nothing
had been deposited anywhere; that label is superseded for the files in this
directory, and remains accurate for the leaf proofs, which are still not deposited
(see below).

## 1. What is here (41 MB, 26 files)

| path | what |
|---|---|
| `S60.txt` | the 60 deleted vertices (generated at packaging time from `base.json`) |
| `base.cnf`, `base.json` | the 4-colouring CNF of G1 − S₆₀ (680 vertices, 3580 edges) plus the 8 clauses col(A) = col(B); `base.json` records S₆₀, the pinned triangle, and sha256 of the CNF, edge and coordinate files |
| `cubes_d14.icnf` | the march_cu split, 16 384 cubes |
| `cnc/cover_pure.cnf`, `cnc/cover_pure.drat` | the cover certificate: the negated cubes are jointly unsatisfiable, i.e. the split is exhaustive |
| `cnc/bundle.json`, `cnc/state.json`, `cnc/ledger.csv`, `cnc/status.json` | the campaign record: per-cube solve time, proof size and proof sha256 |
| `LEAF_INDEX.json` | **sha256 of every one of the 16 384 leaf proofs** |
| `SHA256SUMS.leaf_proofs` | the same digests in `sha256sum -c` form, 17 203 lines (16 384 leaves + 819 audit proofs) |
| `l3_phase3_round2/` | the L2′/L3′ assembly: `G1p.{cvtx,edge}`, `G3p.{cvtx,edge}`, `pairs_p.json`, `L3p.{cnf,drat,json}`, `summary.json` |
| `verify_final.json`, `verify_final.log`, `cnc.log`, `march.log`, `l3prime.log` | logs of the run and of the independent re-verification |
| `SHA256SUMS` | digests of every file in this directory |

Recorded in `verify_final.json`: all_ok = true — 16 384 / 16 384 leaf proofs
drat-trim VERIFIED with matching sha256, cover OK, audit proofs OK, and 819 of the
leaves re-solved from scratch.

## 2. What is **not** here: the leaf proofs

The 16 384 leaf DRAT proofs and their 819 audit counterparts are **not deposited
anywhere** — not in this repository and not in the Zenodo record.

| | bytes | |
|---|---|---|
| leaf proofs | 90 753 918 800 | 84.5 GiB (90.8 GB) |
| audit proofs | 11 423 561 197 | 10.6 GiB (11.4 GB) |
| **total** | **102 179 232 894** | **95.2 GiB (102.2 GB)** |

That exceeds Zenodo's 50 GB per-record limit even after compression (binary DRAT
compresses about 1.6× with gzip and 2.1× with xz, measured on this project's
proofs), so it is not deposited. Every one of those files is pinned by sha256 in
`LEAF_INDEX.json` and `SHA256SUMS.leaf_proofs`, so a copy of a proof you obtain
can be checked against this record.

Regenerating them takes roughly 2.4 h on 14 threads
(`scripts/phase2b/cnc2.py` in `best_S315/scripts/`, or the v1.0 `scripts/cnc2.py`).

## 3. How to re-check

There is **no driver script in this directory** — unlike the repository root
(`rerun.sh`, the 2131-vertex layer) and `best_S315/` (`reverify.sh`, the
1501-vertex layer). `S60_README.md` gives the command instead:

```bash
# whole-bundle re-verification, once the leaf proofs exist locally
python3 scripts/phase3c/verify_final.py \
        --attempt-dir <this directory, with cnc/ renamed to cnc_S60_full> \
        --tag S60_full \
        --keep-dir <directory holding the regenerated leaf proofs> \
        --skip-l3
```

Nothing above needs the leaf proofs:

```bash
# the cover certificate: the 16384 cubes really cover the whole search space
drat-trim cnc/cover_pure.cnf cnc/cover_pure.drat            # s VERIFIED

# the L3' assembly certificate
drat-trim l3_phase3_round2/L3p.cnf l3_phase3_round2/L3p.drat

# the edge lists are the complete unit-distance graphs on their exact point sets
python3 best_S315/scripts/phase2/exactfield.py check \
        l3_phase3_round2/G3p.cvtx l3_phase3_round2/G3p.edge --complete

# integrity of this directory
sha256sum -c SHA256SUMS
```

For a single leaf: rebuild `base.cnf` plus the unit clauses of cube `<id>` from
`cubes_d14.icnf`, regenerate the proof with kissat, and check it with
`drat-trim`. kissat is not bit-reproducible, so the fresh proof will **not** match
the sha256 in `LEAF_INDEX.json`: that digest pins the proof that was actually
checked in the original run. drat-trim accepting your proof is an independent
confirmation of the same claim, which is the point of regenerating.

`S60_README.md` refers to `../REDUCTION_README.md §A` for the statement being
certified. That staging document is not part of this release; §1 above states the
same thing.
