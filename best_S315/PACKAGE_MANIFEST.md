# zenodo_v1.1_core -- package manifest

Generated at packaging time; everything else in this archive is a
verbatim copy of the record staging tree.

## What is here

| path | what |
|---|---|
| `S315.txt` | the 315 deleted vertices (generated: lifted from `run/state.json`) |
| `L2L3/l3_final/G2p.cvtx`, `G2p.edge` | G2' exact vertex coordinates and edge list |
| `L2L3/l3_final/G3p.cvtx`, `G3p.edge` | G3' exact vertex coordinates and edge list |
| `L2L3/l3_final/L3pp.cnf`, `L3pp.drat` | L3 certificate |
| `L2L3/l3_final/spindle_B/spindle.{cnf,drat}` | L2 spindle certificate |
| `L1pp/base.cnf` | the base CNF all leaf proofs refute |
| `L1pp/cubes_d14.icnf` | the 16,382-way cube split |
| `L1pp/cnc_r05a/cover_pure.{cnf,drat}` | cover certificate (the cube split is exhaustive) |
| `L1pp/LEAF_INDEX.json` | **sha256 of every one of the 16382 leaf proofs** |
| `COL5/` | 5-colouring instances and certificates |
| `scripts/` | every script used |
| `reverify.sh` | end-to-end re-verification driver |
| `SHA256SUMS` | 17356 lines, covering the full record tree including leaf proofs |

## What is deliberately NOT here

The 16382 leaf proofs themselves (128.1 GB of binary DRAT).
Their sha256 values are in `L1pp/LEAF_INDEX.json` and in `SHA256SUMS`,
so anyone can check a proof they obtain or regenerate against this record.

## Verification status recorded in this tree

- every leaf re-verified with drat-trim at archive time: 16382/16382, 0 bad
- proof sha sum-of-sha256: `63fe311ba124f41a1efab7fef74da87b6417b6cab73cd74f6e35fd59099b789b`
- base.cnf sha256: `1516417ea9ba4ceee78c6579b90827d7c026d77cd4cd6b3befc2c766f2ad3d2c`
- independent cross-check on a 5% sample (819 leaves), three checkers
  (drat-trim + cake_lpr + lrat-check): 819/819, 0 bad
- cover check: verified; audit: 819/819 complete, 0 missing

The 25 GB of LRAT produced during that cross-check was regenerated for
deposit and is on the Zenodo record as `zenodo_v1.1_audit_lrat.tar.xz`
(5.99 GB packed, 25.0 GB raw); it is also regenerable from the DRAT with
drat-trim.
