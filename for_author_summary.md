# Technical summary for the author (attachment) — independent machine verification of arXiv:2608.04542 v4

Prepared 2026-09-05 by King Tat Wong (independent researcher; ORCID https://orcid.org/0009-0003-4009-3619). This is attachment material only; every number below has a machine certificate or a log in the release. Computations were orchestrated with Claude Code (Anthropic); all mathematical claims are independently machine-checked by drat-trim / cake_lpr and reproducible from the included scripts.

## 1. What we reconstructed

* H (21 vertices, 42 edges), the 84 unit vectors u_j (Table 1 checked arc by arc: u_k = head − tail in ℚ(ζ₈₄)), the 3-ball (83 581 points), T₅ (1042), T₆ (12 856), G₀ (1294), the 7-core G₁ (740 vertices, 3985 edges), G₂ (1066 / 6264, |V₁ ∩ V₂| = 414), G₃ (2131 / 12 530, exactly two cross edges (1,0)–ρ(1,0) and (0,√3)–ρ(0,√3)). Every count equals the paper's. All coordinates are exact, and lie in a cyclotomic field, though they are not in general algebraic integers (H, G₁, G₂ ⊂ ℚ(ζ₈₄) with denominators dividing 7; G₃ ⊂ ℚ(ζ₄₂₀) with denominators dividing 28, (7+i√15)/8 = unit of ℚ(ζ₄₂₀)); no floating-point decision anywhere (floats only pre-screen candidate pairs, which are then decided exactly).
* The 231 paths of Appendix A were transcribed; each one, started at A = (0,0) and followed through u_{i₁}, u_{i₂}, …, lands exactly on B = (0,√3) and stays inside V(G₁); the union of the paths is all of V(G₁).
* One floating-point near-miss was found and rejected exactly: G₃ vertices #246 and #1641 are at distance 1.00000062 (not an edge).

## 2. What we certified by machine

| Statement | Method | Time |
|---|---|---|
| Edge lists of G₁ and G₃ are the complete unit-distance graphs on the exact point sets | exact arithmetic, all pairs (G₃: 2 269 515 pairs) | seconds |
| G₃ (also G₁, G₂) contains no Moser spindle as a subgraph | exact rhombus-pair enumeration (858 rhombi, 0 spindles) and a subgraph-monomorphism CNF, kissat UNSAT 91 s, DRAT 789 608 lines, drat-trim VERIFIED | 5 min |
| G₃ is 5-colourable | kissat SAT, 12 530/12 530 edges checked | 0.1 s |
| G₃ is not 4-colourable | L1 + L2 + L3 (below) | see L1 |
| L2: φ₁(z)=z e^{−iπ/3}−1, φ₂(z)=z e^{iπ/3}+1, φ₃=ρ∘φ₁, φ₄=ρ∘φ₂ map V(G₁) injectively into V(G₃) and E(G₁) into E(G₃) | exact arithmetic | 0.5 s |
| L3: 4-colouring CNF of G₃ + 16 clauses col(A_k) ≠ col(B_k) is UNSAT | kissat 0.12 s, DRAT 4891 lines, drat-trim VERIFIED | 0.2 s |

## 3. L1 — the pair property of G₁: method and cost

Claim: G₁ 4-colouring + col((0,0)) = col((0,√3)) is UNSAT (with the triangle (1,13,87) pinned to colours 1,2,3 for symmetry).

* **Direct CDCL did not work for us.** 22 runs (encodings: plain; plain + at-most-one; + pinned A-triangle; + lex-leader symmetry breaking for the reflection σ(z) = i√3 − z and for colour permutations; solvers kissat 4.0.4 and CaDiCaL 3.0.1, with/without `--unsat`, CaDiCaL also with `--lrat`), 30 minutes each: all 22 timed out; no encoding was more than ±10 % faster in conflicts/s; DRAT output grew at 45–90 MB/min with no sign of convergence. Longer runs: kissat 30 min (DRAT 5.6 GB), CaDiCaL 2 h (DRAT 11.3 GB), unfinished.
* **Cube-and-conquer worked immediately.** march_cu (static depth 14) split the at-most-one encoding into 14 786 cubes in 17.7 s. Every cube was refuted by kissat on the first attempt: mean 0.46 s, median 0.20 s, p99 3.1 s, max 8.6 s; total solver CPU 6834 s; each DRAT proof checked by drat-trim (mean 0.32 s, max 7.5 s; checker CPU 4752 s); all 14 786 proofs `s VERIFIED`; wall time 948 s on 14 workers including a 5 % re-solve audit. The cover (conjunction of the 14 786 negated cubes) is a drat-trim-checked tautology. Every leaf proof was lifted to the plain encoding (at-most-one clauses as RAT lemmas) and re-checked: 14 786/14 786 VERIFIED; 739 (5 %) also passed cake_lpr on LRAT. Depth 11 also works (2042 cubes, mean 1.6 s, max 9.4 s).
* The same contrast holds for G₃ directly, with a caveat: CDCL 2 h timeouts (DRAT 15–20 GB); a depth-15 march_cu split (32 768 cubes) refutes most cubes in seconds (mean 4.8 s, median 3.4 s), but 227 cubes hit a 600 s limit and had to be re-split, and one sub-cube needed 561 s with a 480 MB proof. An 8-hour run on 14 cores verified 32 943 leaves and was stopped at the time cap with 210 sub-cubes pending, so we have no direct certificate for G₃ (only the L1 + L2 + L3 chain).
* Our reading: the difficulty is not the size of a refutation but CDCL's choice of splitting; look-ahead splitting finds short refutations that CDCL's heuristics do not.

## 4. Observations on minimality of G₁ (pair-critical scan) — negative/undecided data, no certificates

* For every vertex v ≠ A, B (738 vertices) we ran kissat for 120 s on "G₁ − v + col(A) = col(B)" (SAT direction). Result: 738/738 timed out; not a single vertex was shown necessary (no SAT witness) and not a single deletion was shown safe (no UNSAT certificate). So there is no fast oracle for "does the pair property survive deleting v".
* A cube-and-conquer run for the deletion of one vertex (v = 1, degree 7) needed 3.35 s per cube on average — seven times the L1 cost — and was stopped after 10 958 of 16 384 cubes (75 minutes, no SAT found, no certificate). Estimated cost of one single-vertex deletion certificate: about 2 hours on 14 cores.
* Batch deletion probe (same day, 6.6 h wall on 14 cores). We ordered the 734 unprotected vertices of G₁ by (most G₃ vertices lost when deleted, lowest degree, farthest from the A–B axis) and deleted them in batches of 30, certifying the pair property of G₁ − S by the same cube-and-conquer pipeline after each batch. Deleting 30 vertices: 16 383 cubes, mean 3.5 s per cube (8× the L1 cost), certificate in 2.2 h; deleting 60: 16 384 cubes, 3.8 s per cube, 2.4 h — so the certificate cost grows slowly. Deleting 90 (and each of the two halves of the third batch, i.e. 75 vertices) is **SAT**: kissat found 4-colourings of G₁ − S with col(A) = col(B), each checked edge by edge. Greedily re-inserting deleted vertices into these colourings shows that sets of 7, 8 and 12 specific vertices cannot be deleted together; no single vertex was certified necessary. The corresponding G₃' (2011 and 1891 vertices after deleting 30 and 60 G₁ vertices) still satisfy the L2/L3 assembly, so they are 5-chromatic Moser-spindle-free graphs as well — but the same construction cannot reach 1441 by this ordering, because necessary vertices appear after about 60 deletions. Details and certificates are in `phase3/probe/` (not part of the proof release).

## 5. Data offered

Exact-coordinate files (.cvtx over ℚ(ζ_N)), edge lists, all sha256 fingerprints, the L2/L3 certificates, the L1 cube file, cover certificate and all 14 786 lifted leaf proofs (25 GB), the spindle-freeness certificate, the probe-matrix logs, and a one-command re-verification (`bash rerun.sh`, 12 minutes on 14 cores).
