# v1.1 layer — a 1501-vertex Moser-spindle-free 5-chromatic unit-distance graph

This directory is the GitHub layer of release **v1.1**. It certifies a graph obtained from
Haugland's construction by deleting vertices, and is independent of the v1.0 material in the
repository root (which certifies Haugland's 2131-vertex graph G3 itself and is unchanged).

`RECORD_README.md` in this directory is the archive's own record, written by the run that
produced it; it is the authoritative description of every certificate here and of how to check
each one. This file only adds what a reader of the repository needs to know about the release.

## The graph

| quantity | value |
|---|---|
| G2′ = G2 − S, deleted set S | **315** vertices (`S315.txt`, and `run/state.json`) |
| G2′ | 751 vertices, 4043 edges |
| **G3′ = G2′ ∪ ρ(G2′)** | **1501 vertices, 8088 edges** |
| previous certified graph (Phase 3c) | 1591 vertices |

**Certified:** χ(G3′) = 5 (no proper 4-colouring, plus an explicit proper 5-colouring checked
edge by edge), and G3′ contains no Moser spindle as a subgraph — by two independent engines
(exact rhombus enumeration finding 0 copies, and a SAT subgraph-monomorphism CNF that is UNSAT
with a drat-trim VERIFIED proof).

**Not a record.** The smallest previously known Moser-spindle-free 5-chromatic unit-distance
graph has **1441** vertices (Heule, *Geombinatorics* 31(2), 2021, as cited in arXiv:2608.04542).
1501 > 1441. That graph is a bibliographic reference here and was **not** re-verified.

## Release notes

finalize3e ran twice: once on 2026-09-09 and again on 2026-09-10 from the
archive, after a packaging bug was fixed. Each run drew an independent
random 5% sample for the cake_lpr cross-check; both passed 819/819. The
sample released here is the second run's, recorded in crosscheck.json.
The leaf_proofs/audit/ directory in the working tree holds the first run's
DRAT artefacts and is not part of this release.

The complete set of 16382 leaf proofs (128.1 GB; ~61 GB with xz, ~79 GB
with gzip) is not uploaded: both exceed Zenodo's 50 GB per-record limit.
Every leaf proof is pinned by sha256 in `L1pp/LEAF_INDEX.json`. `reverify.sh`
re-verifies those proofs with drat-trim and needs them present in
`L1pp/leaf_proofs/`; it does not regenerate them, and step 3 cannot run from a
clone of this repository alone. To check a leaf without the archived proof,
rebuild `base.cnf` plus the cube's unit clauses and re-solve. kissat is not
bit-reproducible, so a fresh proof will not match the recorded sha256 -- the
digest pins the proof that was actually checked; drat-trim accepting a new
proof is an independent confirmation of the same claim.

## Not in this directory

GitHub rejects files above 100 MB, so one certificate file is present here only by fingerprint:

| file | size | sha256 |
|---|---|---|
| `L2L3/l3_final/spindle_B/spindle.drat` | 542 778 955 B (517.6 MiB) | `97cf230e02827a4b18c860b5b0b6a6b046f35d432431c71533e776ed8faff4fe` |
| `L2L3/l3/spindle_B/spindle.drat` | identical file, same sha256 | `97cf230e02827a4b18c860b5b0b6a6b046f35d432431c71533e776ed8faff4fe` |

It is the engine-B spindle-freeness proof (`drat-trim spindle_B/spindle.cnf spindle_B/spindle.drat`
→ `s VERIFIED`). The matching `spindle.cnf` (3.0 MB) **is** here, so the statement being proved is
fully visible; only the proof object is elsewhere. Both copies are in the Zenodo v1.1 record, in
`zenodo_v1.1_core.tar.gz`, at the same paths. Their sha256 values are also in `SHA256SUMS`.

Engine A (exact rhombus-pair enumeration, 0 copies) is independent of this file and is fully
reproducible from `L2L3/l3_final/G3p.edge` with `scripts/phase2/spindlefind.py`, so spindle-freeness
does not rest on the missing proof alone.

The 16382 leaf DRAT proofs are also not here — see the release note above.

## Checking

`reverify.sh` is the end-to-end driver. Without downloading anything further you can already:

```bash
# the deleted set really produces the archived base.cnf
python3 scripts/phase3b/buildg2.py --remove "$(paste -sd, S315.txt | tr -d ' ')" --out /tmp/b --tag base \
        --protected run/batches_g2.json
sha256sum /tmp/b/base.cnf L1pp/base.cnf        # must match 1516417ea9ba4cee...

# the L3'' assembly certificate
drat-trim L2L3/l3_final/L3pp.cnf L2L3/l3_final/L3pp.drat        # s VERIFIED

# the cover certificate: the 16382 cubes really cover the whole search space
drat-trim L1pp/cnc_r05a/cover_pure.cnf L1pp/cnc_r05a/cover_pure.drat

# the 5-colouring, edge by edge
python3 scripts/phase2/certify4.py L2L3/l3_final/G3p.edge --out /tmp/c5 --k 5 --expect sat
```

Verification recorded at archive time (`L1pp/verify_final.json`, `L1pp/crosscheck.json`,
`L1pp/col5_check.json`): every one of the 16382 leaf proofs re-checked with drat-trim
(16382/16382, 0 bad), cover and audit checks passed, an independent 5% sample (819 leaves)
passed all three of drat-trim, the formally verified cake_lpr, and lrat-check, and the archived
5-colouring was re-checked both from the file and by a fresh solve.
