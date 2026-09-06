# CLAIM_en.md — English rendering of CLAIM.md (the Cantonese original, sealed in the proof archive, is authoritative)

**Proposition (machine-proved).** Let G₃ be Haugland's (arXiv:2608.04542 v4) 2131-vertex unit-distance graph with exact vertex coordinates in `inputs/G3.cvtx` (cyclotomic integers of ℚ(ζ₄₂₀)) and edge list `inputs/G3.edge` (12 530 edges).
**G₃ has no proper 4-colouring.** Together with the 5-colouring certified in Phase 2 (`extra/G3-5.col`, all 12 530 edges checked to have different endpoint colours), **χ(G₃) = 5**.

**Proof chain (every step is a machine certificate; re-verification command `bash rerun.sh`):**

1. **Input certification (`scripts/exactfield.py check --complete`):** the edge lists of G₁ (740 vertices) and G₃ are the complete unit-distance graphs on their point sets (exact arithmetic, no floating-point decision): G₁ 3985/3985 edges, G₃ 12 530/12 530 edges; no missing edge, no non-unit edge.
2. **L1 — the pair property of G₁:** `L1/L1_a.cnf` encodes "a 4-colouring of G₁ + vertices A = (0,0) (#560) and B = (0,√3) (#181) have the same colour + the first triangle (1,13,87) is pinned to colours 1,2,3".
   Certificate: march_cu splits `L1/L1_b.cnf` (= L1_a + "at most one colour per vertex" clauses, A and B excepted) into 14 786 cubes (`cubes/cubes.icnf`);
   (a) `cubes/cover_pure.cnf` (the 14 786 negated cubes) is refuted by `cubes/cover_pure.drat`, drat-trim `s VERIFIED` ⇒ every assignment lies in some cube;
   (b) for every cube c: `L1_a.cnf + the unit clauses of c` is refuted by `L1/lifted/L1a_cube_<id>.drat` (Zenodo layer), drat-trim `s VERIFIED`, 14 786/14 786 (`L1/lifted.jsonl` records the sha256 of every CNF and proof; 5 % = 739 leaves were additionally checked with the formally verified checker cake_lpr on LRAT).
   (a)+(b) ⇒ L1_a.cnf is UNSAT ⇒ **every proper 4-colouring of G₁ has col(A) ≠ col(B)** (the triangle pin is only a colour-permutation symmetry: any colouring can be permuted so that (1,13,87) gets (1,2,3); this is the only non-machine step, identical to Phases 0–2).
3. **L2 — four isometric copies (`L2/pairs.json`, `scripts/chain.py`):** φ₁(z) = z·e^{−iπ/3} − 1, φ₂(z) = z·e^{iπ/3} + 1, φ₃ = ρ∘φ₁, φ₄ = ρ∘φ₂ (ρ(w) = (w+1)(7+i√15)/8 − 1),
   computed exactly: φ_k(V(G₁)) ⊂ V(G₃) (740 points, injective) and all 3985 edges of G₁ map into E(G₃), k = 1..4. ⇒ any 4-colouring of G₃ restricted to copy k is a 4-colouring of G₁ ⇒ by L1, col(A_k) ≠ col(B_k).
4. **L3 — assembly (`L3/L3.cnf`, `L3/L3.drat`):** the 4-colouring CNF of G₃ plus the 16 lemma clauses (¬x_{A_k,c} ∨ ¬x_{B_k,c}) (k = 1..4, c = 1..4) is refuted by L3.drat, drat-trim `s VERIFIED` (4891 lines).
   ⇒ G₃ has no 4-colouring.

**Attachments (Phase 2 certificates, not part of rerun.sh; re-verification commands in parentheses):**
- Moser-spindle-free (in the subgraph sense): `phase2_extra/spindle/spindle.cnf` + `spindle.drat` in the Zenodo layer (subgraph-monomorphism CNF, kissat UNSAT, drat-trim VERIFIED; re-verify with `drat-trim spindle.cnf spindle.drat`, about 3.5 minutes); engine A exact enumeration of rhombus pairs: 0 spindles (`scripts/spindlefind.py enumerate inputs/G3.edge`).
- 5-colouring: `extra/G3-5.col` (re-verify edge by edge against `inputs/G3.edge`).

**What this release does NOT prove (do not misread):**
- It does not prove that G₁ or G₃ is vertex-critical or minimal; it does not prove that any vertex can be deleted (the 120-second pair-critical scan left all 738 vertices undecided; the single-vertex cube-and-conquer run was aborted; see `aborted_runs.md` in the archive).
- It does not contain a single direct "G₃ is 4-UNSAT" cube-and-conquer certificate (only a 30-cube sample was measured); the conclusion that G₃ is not 4-colourable is obtained through L1 + L2 + L3.
- It makes no claim about 1441 vertices or any record.

**Tools (sha256 in the archive's `tools.json`):** kissat 4.0.4, drat-trim (GitHub marijnheule/drat-trim), march_cu (marijnheule/CnC 705b60c), cake_lpr (tanyongkiam/cake_lpr a36874a, sample cross-check only), Python 3.14 + `scripts/exactfield.py` (exact cyclotomic arithmetic; selftest with 29 poison cases).
