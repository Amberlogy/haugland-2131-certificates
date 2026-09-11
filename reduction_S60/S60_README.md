# S60_full — Proposition 2 certificate with all leaf proofs archived

Regenerated 2026-09-08 13:53:09 by `scripts/phase3c/s60_full.py` from the Phase 3 round2 inputs (identical files: `base.cnf` sha `92baa01e7232aecbeaaa92e7eb3464a563eadd4280b1b596eaf43ba7480585a9`, `cubes_d14.icnf` sha `ee90368b61c4008d70638d5a116f11988ad189245e968bfede34af5dd7e9fce8`), using `cnc2k.py --keep-dir` (v1.0 `cnc2.py` + proof retention). Statement: `base.cnf` = 4-colouring CNF of G1 − S60 (680 vertices, 3580 edges) + 8 clauses col(A)=col(B) is UNSAT ⇔ G1 − S60 has the pair property (see `README.md` in this directory, and §10 of the repository README). With `l3_phase3_round2/` (L2′/L3′ from Phase 3, unchanged) this certifies that G3′ (1891 vertices) is not 4-colourable — Proposition 2 of the note.

* leaves: 16384, all kissat UNSAT + drat-trim VERIFIED; cover certificate `cnc/cover_pure.drat` VERIFIED; audit 819/819 re-solved from scratch.
* **Leaf proofs (binary DRAT, 90.8 GB): not deposited in either layer (90.8 GB); sha256 per file in `SHA256SUMS.leaf_proofs` (copy here) and `LEAF_INDEX.json`.**
* Independent re-verification from disk (`verify_final.json`): all_ok = True (16384/16384 leaf proofs drat-trim VERIFIED with sha match, cover OK, audit proofs OK).
* Re-check: `python3 ../best_S315/scripts/phase3c/verify_final.py --attempt-dir <this dir with cnc renamed to cnc_S60_full> --tag S60_full --keep-dir <directory holding the leaf proofs you obtained> --skip-l3`, or per leaf: rebuild base.cnf + cube unit clauses, `drat-trim cube.cnf leaf_proofs/cnc_S60_full_<id>.drat`.
