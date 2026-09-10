#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage_v11.py —— Phase 3b 第 3 步: v1.1 材料封存 (唔公開): 收集 Phase 3 探針 (round1/round2 證書, round3/二分 SAT 染色證書 + witness) 同 Phase 3b 每個成功輪嘅證書
  → ~/hadwiger/release_v1_1_staging/reduction/ (+ Windows 鏡像), 寫 REDUCTION_README.md (英文, 每張證書證乜), SHA256SUMS (兩個空格, sha256sum -c 自檢)
  幂等: 可以重跑 (每個成功輪之後), 只加唔刪.
用法: python3 stage_v11.py [--phase3b-run ~/hadwiger/phase3b/runs/p3br1_shrink] [--dst ~/hadwiger/release_v1_1_staging/reduction] [--win /mnt/c/Users/user/Desktop/spindle/release_v1_1_staging/reduction]
"""
import sys, os, json, shutil, hashlib, time, argparse, subprocess, glob
if not __debug__:
    sys.exit("!! 唔准用 python -O")
PH2 = os.path.expanduser("~/hadwiger/phase2"); PH2B = os.path.expanduser("~/hadwiger/phase2b"); PH3 = os.path.expanduser("~/hadwiger/phase3"); PH3B = os.path.expanduser("~/hadwiger/phase3b")
PROBE = os.path.join(PH3, "probe")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def cp(src, dst_dir, name=None):
    if not os.path.exists(src):
        return None
    os.makedirs(dst_dir, exist_ok=True); d = os.path.join(dst_dir, name or os.path.basename(src))
    if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(src) or sha(d) != sha(src):
        shutil.copyfile(src, d)
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase3b-run", default=None); ap.add_argument("--dst", default=os.path.expanduser("~/hadwiger/release_v1_1_staging/reduction"))
    ap.add_argument("--win", default="/mnt/c/Users/user/Desktop/spindle/release_v1_1_staging/reduction")
    a = ap.parse_args()
    D = a.dst; os.makedirs(D, exist_ok=True); t0 = time.time(); log = []
    # ---- Phase 3 探針 ----
    P3 = os.path.join(D, "phase3_G1_probe")
    for f in ("batches.json", "batches.md", "rounds.json", "gate3.md", "hardness.json", "hardness_curve.png"):
        cp(os.path.join(PROBE, f), P3)
    rounds = json.load(open(os.path.join(PROBE, "rounds.json")))
    for r in rounds:
        tag = r["tag"]; sd = os.path.join(PROBE, tag); dd = os.path.join(P3, tag)
        for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3prime.log"):
            cp(os.path.join(sd, f), dd)
        for f in glob.glob(os.path.join(sd, "G1minus_*.col")) + glob.glob(os.path.join(sd, "G1minus_*.json")):
            cp(f, dd)
        for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "cover_with_base.cnf", "cover_with_base.drat", "ledger.csv", "state.json", "status.json"):
            cp(os.path.join(sd, "cnc", f), os.path.join(dd, "cnc"))
        for f in glob.glob(os.path.join(sd, "l3", "*")):
            cp(f, os.path.join(dd, "l3"))
    for f in glob.glob(os.path.join(PROBE, "witness", "*")):
        cp(f, os.path.join(P3, "witness"))
    for f in ("batches.py", "buildbatch.py", "l3prime.py", "probe3.py", "witness_blocked.py", "hardness.py"):
        cp(os.path.join(PH3, f), os.path.join(D, "scripts", "phase3"))
    for f in ("cnc2.py", "cubes.py"):
        cp(os.path.join(PH2B, f), os.path.join(D, "scripts", "phase2b"))
    for f in ("exactfield.py", "certify4.py", "chain.py", "spindlefind.py", "haugland.py"):
        cp(os.path.join(PH2, f), os.path.join(D, "scripts", "phase2"))
    cp(os.path.join(PH2, "refs", "appendixA_paths.json"), os.path.join(D, "scripts", "phase2", "refs"))
    # ---- Phase 3b ----
    p3b_rounds = []; p3b_run = None
    if a.phase3b_run and os.path.exists(os.path.join(a.phase3b_run, "rounds.json")):
        p3b_run = os.path.basename(a.phase3b_run.rstrip("/")); P3B = os.path.join(D, "phase3b_G2_shrink")
        for f in ("batches_g2.json", "batches_g2.md"):
            cp(os.path.join(PH3B, f), P3B)
        for f in ("rounds.json", "state.json", "ledger_g2.md", "gate_g2.md", "hardness_g2.json", "hardness_curve_g2.png", "probe3b.log"):
            cp(os.path.join(a.phase3b_run, f), P3B)
        p3b_rounds = json.load(open(os.path.join(a.phase3b_run, "rounds.json")))
        for r in p3b_rounds:
            for x in r["attempts"]:
                tag = x["tag"]; sd = os.path.join(a.phase3b_run, tag); dd = os.path.join(P3B, tag)
                for f in ("base.cnf", "base.json", "cubes_d14.icnf", "march.log", "cnc.log", "l3g2.log"):
                    cp(os.path.join(sd, f), dd)
                for f in glob.glob(os.path.join(sd, "G2minus_*.col")) + glob.glob(os.path.join(sd, "G2minus_*.json")):
                    cp(f, dd)
                for f in ("bundle.json", "cover_pure.cnf", "cover_pure.drat", "cover_with_base.cnf", "cover_with_base.drat", "ledger.csv", "state.json", "status.json"):
                    cp(os.path.join(sd, "cnc_" + tag, f), os.path.join(dd, "cnc"))
                for f in glob.glob(os.path.join(sd, "l3", "*")):
                    if os.path.isfile(f):
                        cp(f, os.path.join(dd, "l3"))
                for f in glob.glob(os.path.join(sd, "l3", "spindle_B", "*")):
                    cp(f, os.path.join(dd, "l3", "spindle_B"))
                for f in glob.glob(os.path.join(sd, "witness", "*")):
                    cp(f, os.path.join(dd, "witness"))
        for f in glob.glob(os.path.join(PH3B, "*.py")) + glob.glob(os.path.join(PH3B, "*.sh")):
            cp(f, os.path.join(D, "scripts", "phase3b"))
    # ---- README ----
    L = ["# REDUCTION_README.md — v1.1 staging: certificates for the reduction experiments (NOT yet released)", "",
         "Staged %s by `phase3b/stage_v11.py`. Everything here supplements v1.0 (GitHub `Amberlogy/haugland-2131-certificates`, Zenodo DOI 10.5281/zenodo.22435778). "
         "Vertex numbers refer to the v1.0 input files `inputs/G1.*`, `inputs/G3.*` (and `G2.*` from `scripts/phase2/haugland.py`); all coordinates are exact cyclotomic integers." % time.strftime("%Y-%m-%d %H:%M:%S"), "",
         "## A. What each certificate proves", "",
         "**Notation.** G1 (740 vertices) has the *pair property* if every proper 4-colouring gives A=(0,0) and B=(0,√3) different colours. "
         "G2 (1066 vertices) has the *mono-pair property* if every proper 4-colouring gives u=(−1,0) and v=(1,0) the same colour. For a vertex set S, G−S is the induced subgraph on V(G)∖S.", "",
         "| certificate type | file(s) | statement certified | how to check |", "|---|---|---|---|",
         "| L1′ cube-and-conquer bundle (G1−S pair property) | `phase3_G1_probe/roundN/base.cnf` (+`base.json`: S, pinned triangle, sha), `cubes_d14.icnf`, `cnc/bundle.json`, `cnc/cover_pure.{cnf,drat}`, `cnc/ledger.csv`, `cnc/state.json` | `base.cnf` = 4-colouring CNF of G1−S (ALO + AMO + edge clauses, triangle (A,p,q) pinned to colours 1,2,3) + 8 clauses col(A)=col(B). UNSAT ⇔ G1−S has the pair property. Every leaf cube (`cnc/state.json` → `done`) was refuted by kissat with a DRAT proof checked by drat-trim (`verified: true`, proof sha256 + size recorded); the cover certificate `cover_pure.drat` (drat-trim VERIFIED) shows the negated cubes are jointly unsatisfiable, i.e. the cubes cover the whole search space; 5 % of the leaves were re-solved from scratch (`bundle.json` → `audit`). | rebuild `base.cnf` with `scripts/phase3/buildbatch.py --remove <S>` and compare sha; `drat-trim cover_pure.cnf cover_pure.drat`; re-solve any leaf: base.cnf + unit clauses of the cube → kissat → drat-trim. Leaf proofs themselves were deleted after verification (only sha256/size kept, as in the v1.0 policy for un-lifted proofs); regenerating all of them takes ≈2.2 h / 2.4 h on 14 threads (`scripts/phase2b/cnc2.py`). |",
         "| L2′/L3′ assembly (G3′ 5-chromatic) | `phase3_G1_probe/roundN/l3/G1p.{cvtx,edge}`, `G3p.{cvtx,edge}`, `pairs_p.json`, `L3p.{cnf,drat,json}`, `summary.json`, `../l3prime.log` | G3′ = ∪_k φ_k(G1−S) (induced subgraph of G3, renumbered). `exactfield.py check --complete` certifies the edge lists are the complete unit-distance graphs on the exact point sets; `pairs_p.json` lists A′_k,B′_k; `L3p.cnf` = 4-colouring CNF of G3′ + 16 clauses col(A′_k)≠col(B′_k), UNSAT with drat-trim VERIFIED `L3p.drat`. Together with L1′: G3′ has no 4-colouring; 5-colourability and Moser-spindle-freeness are inherited from G3 (subgraph). | `python3 scripts/phase2/exactfield.py check G3p.cvtx G3p.edge --complete`; `drat-trim L3p.cnf L3p.drat`; `scripts/phase3/l3prime.py --remove <S>` regenerates everything. |",
         "| blocking colouring (S contains a necessary vertex) | `phase3_G1_probe/round3*/G1minus_NNv.col` (+`.json`), `phase3_G1_probe/witness/*_minus_blocked.col` | a proper 4-colouring of G1−S with col(A)=col(B) — a machine-checkable witness that G1−S does **not** have the pair property, i.e. S cannot be deleted as a whole. The `witness/` files are the same colourings after greedily re-inserting as many deleted vertices as possible: G1−B has such a colouring for the smaller set B listed in the header, so B (7, 8 or 12 vertices) cannot be deleted as a whole. | check every edge of G1−S (or G1−B) is bichromatic and col(A)=col(B) (`scripts/phase3/witness_blocked.py` does this and regenerates B). |"]
    if p3b_run:
        L += ["| L1″ cube-and-conquer bundle (G2−S mono-pair property) | `phase3b_G2_shrink/rNNx/base.cnf` (+`base.json`), `cubes_d14.icnf`, `cnc/bundle.json`, `cnc/cover_pure.{cnf,drat}`, `cnc/ledger.csv`, `cnc/state.json` | `base.cnf` = 4-colouring CNF of G2−S (ALO + AMO + edges, triangle (u,p,q) pinned) + 4 clauses ¬(col(u)=c ∧ col(v)=c). UNSAT ⇔ G2−S has the mono-pair property. Same leaf/cover/audit structure as L1′. | `scripts/phase3b/buildg2.py --remove <S>`; `drat-trim cover_pure.cnf cover_pure.drat`. |",
              "| L2″/L3″ assembly (G3″ = (G2−S) ∪ ρ(G2−S) 5-chromatic) | `phase3b_G2_shrink/rNNx/l3/G2p.*`, `G3p.*`, `maps.json`, `L3pp.{cnf,drat,json}`, `summary.json`, `../l3g2.log` | identity and ρ(z)=(z+1)(7+i√15)/8−1 map V(G2−S) injectively into V(G3″) and E(G2−S) into E(G3″) (exact); `exactfield.py check --complete` on G2p and G3p; `L3pp.cnf` = 4-colouring CNF of G3″ + 16 clauses col(u)=col(v), col(u)=col(ρv) (bi-implications per colour), UNSAT with verified DRAT (the spindle edge v–ρ(v) makes the lemma set contradictory). Moser-spindle-freeness re-checked by exact rhombus enumeration (`summary.json` → `spindle_A.copies = 0`), and for the final graph also by the SAT engine (`l3/spindle_B/`). | `scripts/phase3b/l3g2.py --remove <S> [--engine-b]`. |",
              "| blocking colouring for G2 | `phase3b_G2_shrink/rNNx/G2minus_NNv.col` (+`.json`), `rNNx/witness/*_minus_blocked.col` | proper 4-colouring of G2−S with col(u)≠col(v): S cannot be deleted as a whole; `witness/` = greedy re-insertion → smaller blocking set B. | `scripts/phase3b/witness_g2.py --col <file>`. |"]
    L += ["", "## B. Phase 3 reduction of G1 (2026-09-05; order: influence↓, degree↑, |Re z|↓; protected {10,172,181,560,569,574}; `phase3_G1_probe/batches.md`)", "",
          "| tag | |S| | result | cubes | leaves verified | mean solve+verify / cube | wall (14 thr) | |G1−S| | |G3′| | L3′ |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rounds:
        L.append("| %s | %d | %s | %s | %s | %s s | %.2f h | %s | %s | %s |" % (r["tag"], r["removed"], r["status"], r.get("n_cubes"), r.get("leaves"), r.get("mean_sv_s"), r["wall_s"] / 3600,
                                                                    r.get("G1p_n") or (740 - r["removed"]), r.get("G3p_n") or "—", ("UNSAT VERIFIED" if r.get("l3_ok") else "—") if r["status"] == "certified" else "— (SAT: `%s`)" % os.path.basename(r["colouring"]["col_file"]) if r.get("colouring") else "—"))
    bj = json.load(open(os.path.join(PROBE, "batches.json")))
    L += ["", "S_30 = batch 1 = %s" % bj["batches"][0], "", "S_60 = batches 1+2 = %s" % sorted(bj["batches"][0] + bj["batches"][1]), "",
          "Blocking sets from `witness/witness_blocked.json`: " + "; ".join("%s: B=%s (|B|=%d)" % (os.path.basename(os.path.dirname(w["witness"])), w["blocked_min"], w["blocked_min_size"]) for w in json.load(open(os.path.join(PROBE, "witness", "witness_blocked.json")))), ""]
    if p3b_run:
        L += ["## C. Phase 3b reduction of G2 (run %s; order: degree↑, |Im z|↓; protected P2 = {172, 187, 646, 994}; `phase3b_G2_shrink/batches_g2.md`)" % p3b_run, "",
              "| round | attempt | |S| | result | cubes | leaves | mean solve+verify / cube | wall | |G2−S| | |G3″| | L2″/L3″/complete/spindle | blocking set B |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in p3b_rounds:
            for x in r["attempts"]:
                L.append("| %d | %s | %d | %s | %s | %s | %s s | %.2f h | %s | %s | %s | %s |" % (
                    r["round"], x["tag"], x["removed"], x["status"], x.get("n_cubes"), x.get("leaves"), x.get("mean_sv_s"), (x.get("wall_s") or 0) / 3600,
                    x["cnf"]["n_remaining"] if x.get("cnf") else "—", x.get("G3p_n") or "—", ("all OK" if x.get("l3_ok") else "!!") if x["status"] == "certified" else "—",
                    ("|B|=%d %s" % (x["B_size"], x["witness"]["blocked_min"])) if x.get("witness") else "—"))
        st3b = json.load(open(os.path.join(a.phase3b_run, "state.json")))
        L += ["", "Certified removable set S_acc (%d vertices) = %s" % (len(st3b["S_acc"]), st3b["S_acc"]), "", "Stop reason: %s" % st3b.get("stop_reason"), ""]
    L += ["## D. Integrity", "", "`SHA256SUMS` covers every file in this directory (format: `<sha256>  <path>`; check with `sha256sum -c SHA256SUMS`). Tool versions and binaries are those of v1.0 (`bundle.json` → `tools`).", "",
          "Not released yet: Amber (K. T. Wong) reviews first; no git push, no new Zenodo version."]
    open(os.path.join(D, "REDUCTION_README.md"), "w").write("\n".join(L) + "\n")
    # SHA256SUMS
    files = sorted(os.path.relpath(os.path.join(r, f), D) for r, _, fs in os.walk(D) for f in fs if f != "SHA256SUMS")
    with open(os.path.join(D, "SHA256SUMS"), "w") as f:
        for rel in files:
            f.write("%s  %s\n" % (sha(os.path.join(D, rel)), rel))
    chk = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=D, capture_output=True, text=True)
    tot = sum(os.path.getsize(os.path.join(D, r)) for r in files)
    print("[stage_v11] %d files, %.1f MB → %s; sha256sum -c: rc=%d %s" % (len(files), tot / 1e6, D, chk.returncode, (chk.stdout + chk.stderr).strip()[:200] or "OK"))
    # Windows 鏡像
    if a.win:
        os.makedirs(a.win, exist_ok=True)
        for rel in files + ["SHA256SUMS"]:
            cp(os.path.join(D, rel), os.path.dirname(os.path.join(a.win, rel)))
        print("[stage_v11] mirrored to %s (%.0fs)" % (a.win, time.time() - t0))

if __name__ == "__main__":
    main()
