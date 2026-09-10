#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
facts_check.py —— Phase 3b 第 5 步: 逐句抽出 note_v1.tex 正文所有數字, 對照 paper/facts.json → facts_check.md (每個數字 → 來源 → 一致/不一致/冇來源; 唔改正文)
用法: python3 facts_check.py --tex paper/note_v1.tex --facts paper/facts.json --out paper/facts_check.md [--extra phase3b/extra_facts.json]
"""
import sys, os, re, json, argparse, math

TRIVIAL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}     # 細整數 (色數, 幾何常數, 列舉) 唔對 facts
YEARS = set(range(1990, 2031))

def flatten(v, prefix=""):
    out = []
    if isinstance(v, bool):
        return out
    if isinstance(v, (int, float)):
        out.append((prefix, v))
    elif isinstance(v, str):
        for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", v):
            out.append((prefix + "(str)", float(m.group(1)) if "." in m.group(1) else int(m.group(1))))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            out += flatten(x, prefix + "[%d]" % i)
    elif isinstance(v, dict):
        for k, x in v.items():
            out += flatten(x, prefix + "." + str(k))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True); ap.add_argument("--facts", required=True); ap.add_argument("--out", required=True); ap.add_argument("--extra", default=None)
    a = ap.parse_args()
    tex = open(a.tex, encoding="utf-8").read()
    body = tex[tex.index(r"\begin{document}"):]
    bib_start = body.find(r"\begin{thebibliography}")
    main_body = body[:bib_start] if bib_start > 0 else body
    bib = body[bib_start:] if bib_start > 0 else ""
    def clean(s):
        s = re.sub(r"(?<!\\)%.*", "", s)               # 注釋
        while True:                                          # 14\,786 / 2\,269\,515 → 14786 / 2269515 (千位 thin space, 重複直至冇)
            s2 = re.sub(r"(\d)\\,(\d{3})(?!\d)", r"\1\2", s)
            if s2 == s:
                break
            s = s2
        s = s.replace(r"\,", " ").replace("~", " ")          # 其他 thin space (17.7\,s) → 空格, 免得數字黐住單位
        s = re.sub(r"\\(?:ref|label|cite|url|href|texttt|emph|textbf|section\*?|subsection\*?)\{[^}]*\}", " ", s)
        return s
    facts = json.load(open(a.facts, encoding="utf-8"))["facts"]
    idx = {}
    for k, f in facts.items():
        for sub, val in flatten(f.get("value"), k):
            idx.setdefault(val, []).append((sub, f.get("source"), f.get("verified", True)))
    if a.extra and os.path.exists(a.extra):
        for k, f in json.load(open(a.extra, encoding="utf-8")).items():
            for sub, val in flatten(f.get("value"), "extra." + k):
                idx.setdefault(val, []).append((sub, f.get("source"), f.get("verified", True)))
    # 派生數 (常用): 加入 idx 做「派生一致」
    derived = {}
    def add_d(val, how):
        derived.setdefault(val, []).append(how)
    add_d(2 * 1066 - 1, "2·G2_v − 1 = 2131"); add_d(2 * 6264 + 2, "2·G2_e + 2 = 12530"); add_d(740 - 30, "G1_v − 30"); add_d(740 - 60, "G1_v − 60"); add_d(740 - 90, "G1_v − 90"); add_d(740 - 75, "G1_v − 75")
    add_d(round(948 / 60), "L1.wall_s / 60 ≈ 16 min"); add_d(round(12.3), "part3 wall 12.3 h"); add_d(round(44430 / 3600, 1), "part3 resume wall 12.34 h")
    add_d(round(340800 / 3600), "tail wasted 94.7 → 95 CPU-h"); add_d(round(94.7), "wasted CPU-h"); add_d(2131 * 2130 // 2, "C(2131,2) = 2269515")
    add_d(round(1800 / 60), "1800 s = 30 min"); add_d(round(7200 / 3600), "7200 s = 2 h"); add_d(round(120 / 60), "120 s = 2 min")
    for r_ in (facts.get("probe.rounds", {}).get("value") or []):
        add_d(round(r_["wall_s"] / 3600, 2), "%s wall_s %s / 3600" % (r_["tag"], r_["wall_s"]))
    add_d(round(948 / 3600, 2), "L1.wall_s 948 / 3600 = 0.26 h"); add_d(round(0.462 + 0.321, 2), "L1 mean_solve 0.462 + mean_verify 0.321 = 0.78 s")
    add_d(83, "u_0..u_83 = 84 unit vectors, index range"); add_d(round(4.76, 1), "part3 mean_solve_s 4.76 → 4.8")
    def rounds_to(val, tok):
        """facts 值四捨五入到 tok 嘅小數位 == val ?"""
        nd = len(tok.split(".")[1]) if "." in tok else 0
        hits = []
        for v2, hs in idx.items():
            if isinstance(v2, (int, float)) and not isinstance(v2, bool):
                try:
                    if round(float(v2), nd) == float(val) and v2 != val:
                        hits += hs
                except Exception:
                    pass
        return hits
    # 抽數字 (正文)
    rows = []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\\$(])", clean(main_body))
    seen_ctx = set()
    for s in sentences:
        s1 = " ".join(s.split())
        if not s1:
            continue
        # 特殊識別碼
        ids = re.findall(r"arXiv:\s*\d{4}\.\d{4,5}|10\.\d{4,9}/[^\s},]+|\d{4}-\d{4}-\d{4}-\d{3}[\dX]", s1)
        for t in ids:
            hit = [k for k, f in facts.items() if isinstance(f.get("value"), str) and t.replace("arXiv:", "").strip() in f["value"]]
            rows.append((t, s1[:120], hit, "一致 (識別碼喺 facts.json)" if hit else ("常數/引用 (arXiv 編號)" if t.startswith("arXiv") else "冇喺 facts.json (ORCID / DOI 由 release 檔核)")))
        s2 = re.sub(r"arXiv:\s*\d{4}\.\d{4,5}|10\.\d{4,9}/[^\s},]+|\d{4}-\d{4}-\d{4}-\d{3}[\dX]", " ", s1)
        for m in re.finditer(r"(?<![\w.\\])(\d+(?:\.\d+)?)(?![\w])", s2):
            tok = m.group(1); val = float(tok) if "." in tok else int(tok)
            ctx = s2[max(0, m.start() - 60):m.end() + 60].strip()
            key = (tok, ctx)
            if key in seen_ctx:
                continue
            seen_ctx.add(key)
            if isinstance(val, int) and val in TRIVIAL and not re.search(r"(hours?|h\b|min|GB|MB|s\b|seconds|%)", s2[m.end():m.end() + 12]):
                verdict = "常數 (細整數: 色數 / 幾何 / 列舉)"; hit = []
            elif isinstance(val, int) and val in YEARS and not re.search(r"(vertices|cubes|leaves|edges)", s2[m.end():m.end() + 20]):
                verdict = "年份"; hit = []
            elif re.search(r"(p\{|\\linewidth|tabular\{)", ctx):
                verdict = "排版常數 (tabular 欄寬)"; hit = []
            else:
                hit = idx.get(val, [])
                if not hit:
                    rh = rounds_to(val, tok)
                    if rh:
                        hit = rh; verdict = "一致 (四捨五入: %s)" % ", ".join(sorted({"%s=%s" % (h[0].split("(")[0], next(v2 for v2, hs in idx.items() if h in hs)) for h in rh})[:3])
                        rows.append((tok, ctx, hit, verdict)); continue
                if not hit and val in derived:
                    rows.append((tok, ctx, [], "派生一致 (%s)" % "; ".join(derived[val]))); continue
                if not hit and isinstance(val, float):
                    hit = [h for v2, hs in idx.items() if isinstance(v2, (int, float)) and abs(v2 - val) <= 0.05 * max(abs(val), 1e-9) + 1e-9 for h in hs]
                    if hit:
                        verdict = "≈一致 (5%% 內: %s)" % ", ".join(sorted({h[0].split("(")[0] for h in hit})[:3])
                    else:
                        verdict = "冇來源 (facts.json 冇呢個數)"
                elif not hit and val in derived:
                    verdict = "派生一致 (%s)" % "; ".join(derived[val])
                elif not hit:
                    near = [(v2, hs) for v2, hs in idx.items() if isinstance(v2, (int, float)) and v2 and abs(v2 - val) / max(abs(v2), 1) <= 0.06 and v2 != val]
                    verdict = "**不一致?** 最近: %s" % ", ".join("%s=%s" % (hs[0][0].split("(")[0], v2) for v2, hs in near[:3]) if near else "冇來源 (facts.json 冇呢個數)"
                else:
                    verdict = "一致" + (" [來源 verified=false]" if any(not h[2] for h in hit) else "")
            rows.append((tok, ctx, hit, verdict))
    # 參考文獻嘅數字
    bib_rows = []
    for item in re.split(r"\\bibitem", clean(bib))[1:]:
        key = re.match(r"\{([^}]*)\}", item); key = key.group(1) if key else "?"
        nums = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])", item)
        bib_rows.append((key, nums))
    # 寫 md
    L = ["# facts_check.md —— note_v1.tex 正文數字 vs facts.json (機器抽取, %s; 只標唔改)" % __import__("time").strftime("%Y-%m-%d %H:%M"), "",
         "來源: `%s` (%d 項 facts) ; 正文 %d 句, 抽出 %d 個數字 / 識別碢. 判定: 一致 = 數值同 facts.json 某項完全相等; ≈一致 = 5%% 內 (通常係四捨五入); 派生一致 = 由 facts 簡單運算得出; 常數 / 年份 = 唔對; 冇來源 = facts.json 冇呢個數 (要人手核); **不一致?** = 有相近 (6%% 內) 但唔相等嘅 facts 值." % (a.facts, len(facts), len(sentences), len(rows)), "",
         "| # | 數字 | 上下文 | facts.json 來源 (key = value) | 判定 |", "|---|---|---|---|---|"]
    cnt = {}
    for i, (tok, ctx, hit, verdict) in enumerate(rows, 1):
        vk = verdict.split(" ")[0].replace("**", ""); cnt[vk] = cnt.get(vk, 0) + 1
        src = "; ".join(sorted({"%s" % h[0] for h in hit})[:4]) if hit else "—"
        L.append("| %d | %s | %s | %s | %s |" % (i, tok, ctx.replace("|", "\\|"), src.replace("|", "\\|"), verdict))
    L += ["", "統計: %s" % cnt, "", "## 參考文獻 (thebibliography) 入面嘅數字 (唔喺 facts.json; 由 bib_check.md / Crossref 核)", ""]
    for key, nums in bib_rows:
        L.append("- %s: %s" % (key, ", ".join(nums)))
    L += ["", "## 人手覆核 (由 Claude 讀返上表逐項寫; 只標唔改)", "", "(見下方由 phase3b 報告補充嘅段落)"]
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("[facts_check] %d 句 %d 個數字 → %s; 統計 %s" % (len(sentences), len(rows), a.out, cnt))
    for i, (tok, ctx, hit, verdict) in enumerate(rows, 1):
        if verdict.startswith(("**不一致", "冇來源", "≈")):
            print("  #%d %s | %s | %s" % (i, tok, ctx[:100], verdict))

if __name__ == "__main__":
    main()
