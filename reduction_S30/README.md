# reduction_S30 — the certificate for G1 − S₃₀

The cube-and-conquer certificate that **G1 − S₃₀** (710 vertices, 3779 edges) has the
pair property, together with the L2′/L3′ assembly in `l3/`, which certifies that the
corresponding G3′ (2011 vertices) is not 4-colourable.

S₃₀ is the first batch of the Phase 3 reduction of G1; deleting it leaves the pair
property intact. `base.json` records the 30 vertices, the pinned triangle, and the
sha256 of the CNF and of the input coordinate and edge files.

## 1. Read this before comparing with `reduction_S60/`

Three things differ from the S₆₀ layer, and copying its wording would be wrong:

**The leaf proofs were never retained.** They were checked with drat-trim as they were
produced and deleted immediately afterwards — the v1.0 policy for un-lifted proofs.
They do **not** exist anywhere: not here, not on any local disk, not in the Zenodo
record. This is *not* the `reduction_S60/` situation, where 95.2 GiB of proofs exist
but are too large to deposit. Here there is nothing to deposit and nothing to
withhold; the 81.8 GB of DRAT that passed through drat-trim during the run is gone.

**The per-leaf digests are in `cnc/state.json`, not in a `LEAF_INDEX.json`.** There is
no `LEAF_INDEX.json` in this directory. `cnc/state.json` has a `done` map with one
entry per cube:

```
"done": { "<cube id>": { "cube": [...], "solve_s": 1.2, "conflicts": 30824,
                         "proof_bytes": 2096539,
                         "proof_sha": "aa38788774ef3faa…",   <- sha256 of the DRAT proof
                         "cnf_sha":   "9665de2052c3583b…",   <- sha256 of the exact cube CNF
                         "checker": "drat-trim", "checker_rc": 0, "verify_s": 0.9 } , … }
```

All **16 383** entries carry both digests, and all 16 383 have
`checker == "drat-trim"` and `checker_rc == 0`. Note there is no `verified` boolean:
`checker_rc == 0` is the record of the check.

**So a leaf is re-checked by regenerating it**, not by downloading it. Because
`cnf_sha` is recorded as well as `proof_sha`, you can confirm you rebuilt exactly the
CNF that was solved before you compare the proof.

## 2. Regenerate and re-check

```bash
# one leaf <id>: rebuild base.cnf + the unit clauses of cube <id> from cubes_d14.icnf,
# check the CNF against cnf_sha in cnc/state.json, then
kissat --binary=false <cube.cnf> <leaf.drat>
drat-trim <cube.cnf> <leaf.drat>          # s VERIFIED
sha256sum <leaf.drat>                     # compare with proof_sha

# all 16383 leaves, about 2.2 h on 14 threads (v1.0 script, or best_S315/scripts/phase2b/)
python3 ../best_S315/scripts/phase2b/cnc2.py --cnf base.cnf --icnf cubes_d14.icnf --out DIR --workers 14
```

kissat is not bit-reproducible across builds, so a regenerated proof will usually
differ from the recorded `proof_sha`; what the digest pins is the proof that was
actually checked in the original run. A fresh proof that drat-trim accepts is an
independent confirmation of the same claim, which is the point of regenerating.

Nothing below needs any leaf proof:

```bash
drat-trim cnc/cover_pure.cnf cnc/cover_pure.drat    # the 16383 cubes cover the search space
drat-trim l3/L3p.cnf l3/L3p.drat                    # the L3' assembly certificate
python3 ../best_S315/scripts/phase2/exactfield.py check l3/G3p.cvtx l3/G3p.edge --complete   # needs numpy
sha256sum -c SHA256SUMS                             # integrity of this directory
```

## 3. What is here

| path | what |
|---|---|
| `S30.txt` | the 30 deleted vertices (generated at packaging time from `base.json`) |
| `base.cnf`, `base.json` | the 4-colouring CNF of G1 − S₃₀ plus the 8 clauses col(A) = col(B); UNSAT ⇔ the pair property holds |
| `cubes_d14.icnf` | the march_cu split, 16 383 cubes |
| `cnc/cover_pure.cnf`, `cnc/cover_pure.drat` | the cover certificate |
| `cnc/state.json` | the per-leaf record described above (16 383 entries) |
| `cnc/bundle.json`, `cnc/ledger.csv`, `cnc/status.json` | the campaign record and the sha256 of every tool binary used |
| `l3/` | the L2′/L3′ assembly: `G1p.{cvtx,edge}`, `G3p.{cvtx,edge}`, `pairs_p.json`, `L3p.{cnf,drat,json}`, `summary.json` |
| `cnc.log`, `march.log`, `l3prime.log` | logs of the run |
| `SHA256SUMS` | digests of every file in this directory |
