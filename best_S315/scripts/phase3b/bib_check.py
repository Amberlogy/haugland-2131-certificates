#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bib_check.py —— Phase 3b 第 5 步: refs.bib 同 note_v1.tex 嘅 thebibliography 對齊 + 三條有 DOI 註釋嘅文獻用 Crossref JSON 核卷頁 → bib_check.md (只標唔改)
用法: python3 bib_check.py --tex paper/note_v1.tex --bib paper/refs.bib --doi-dir paper/bib_doi --out paper/bib_check.md
"""
import sys, os, re, json, argparse, time

def parse_bib(path):
    txt = open(path, encoding="utf-8").read()
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", txt, re.S):
        typ, key, body = m.group(1), m.group(2), m.group(3)
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)\s*,?", body):
            v = fm.group(2).strip().strip(",").strip()
            if v[:1] in "{\"":
                v = v[1:-1]
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", v)
        entries[key] = {"type": typ, **fields}
    return entries

def parse_thebib(path):
    txt = open(path, encoding="utf-8").read()
    i = txt.find(r"\begin{thebibliography}")
    if i < 0:
        return {}, []
    seg = txt[i:txt.find(r"\end{thebibliography}")]
    items = {}
    for m in re.finditer(r"\\bibitem\{([^}]*)\}(.*?)(?=\\bibitem\{|$)", seg, re.S):
        key = m.group(1); body = m.group(2)
        comment_doi = re.search(r"%\s*confirm:\s*DOI\s*(\S+)", body)
        body_clean = re.sub(r"(?<!\\)%.*", "", body)
        body_clean = re.sub(r"\s+", " ", body_clean).strip()
        items[key] = {"text": body_clean, "doi_comment": comment_doi.group(1) if comment_doi else None,
                      "years": re.findall(r"\b(19\d\d|20\d\d)\b", body_clean), "pages": re.findall(r"(\d+)\s*--\s*(\d+)", body_clean),
                      "volume": re.findall(r"\\textbf\{(\d+)\}", body_clean) + re.findall(r"LNCS\s*(\d+)", body_clean),
                      "arxiv": re.findall(r"arXiv:\s*(\d{4}\.\d{4,5})", body_clean)}
    cited = sorted(set(re.findall(r"\\cite\{([^}]*)\}", txt[:i])))
    cited = sorted({c.strip() for cc in cited for c in cc.split(",")})
    return items, cited

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True); ap.add_argument("--bib", required=True); ap.add_argument("--doi-dir", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bib = parse_bib(a.bib); items, cited = parse_thebib(a.tex)
    # 對齊: key 正規化 (deGrey2018 ↔ degrey2018), 或者標題 / 年份 / 作者姓
    def match(key, it):
        nk = norm(key)
        for bk, e in bib.items():
            if norm(bk) == nk:
                return bk
        best = None
        for bk, e in bib.items():
            t = norm(e.get("title", "")); words = [w for w in re.findall(r"[a-z]{5,}", e.get("title", "").lower()) if w not in ("problem", "graph", "graphs", "plane", "using", "solving")]
            hits = sum(1 for w in words if w in it["text"].lower())
            yr = e.get("year") in it["years"]
            score = hits + (2 if yr else 0)
            if hits >= 2 and (best is None or score > best[0]):
                best = (score, bk)
        return best[1] if best else None
    rows = []; used = set()
    for key, it in items.items():
        bk = match(key, it); used.add(bk)
        diffs = []
        if bk:
            e = bib[bk]
            if e.get("year") and e["year"] not in it["years"]:
                diffs.append("year: bib %s vs tex %s" % (e["year"], it["years"]))
            if e.get("pages"):
                bp = re.findall(r"(\d+)\s*--\s*(\d+)", e["pages"].replace("–", "--"))
                if bp and bp[0] not in it["pages"]:
                    diffs.append("pages: bib %s vs tex %s" % (e["pages"], it["pages"]))
            if e.get("volume") and e["volume"] not in it["volume"] and e["volume"] not in it["text"]:
                diffs.append("volume: bib %s vs tex %s" % (e["volume"], it["volume"]))
            au_bib = [w.split(",")[0].strip().split()[-1] for w in e.get("author", "").split(" and ") if w.strip()]
            au_missing = [x for x in au_bib if x.split("{")[-1].split("}")[0] not in it["text"]]
            if au_missing:
                diffs.append("authors not in tex item: %s" % au_missing)
        rows.append((key, "✓ cited" if key in cited else "!! not cited in body", bk or "**no refs.bib entry**", "; ".join(diffs) if diffs else ("—" if bk else "—"), it["doi_comment"]))
    unused = [bk for bk in bib if bk not in used]
    uncited_items = [k for k in items if k not in cited]; missing_items = [c for c in cited if c not in items]
    # Crossref 核對
    doi_rows = []
    for key, it in items.items():
        if not it["doi_comment"]:
            continue
        f = os.path.join(a.doi_dir, it["doi_comment"].replace("/", "_") + ".json")
        if not os.path.exists(f):
            doi_rows.append((key, it["doi_comment"], "(Crossref JSON 冇下載)", "", "", "", "")); continue
        d = json.load(open(f, encoding="utf-8"))["message"]
        title = (d.get("title") or [""])[0]; cont = d.get("container-title") or []; page = d.get("page"); yr = (d.get("published-print") or d.get("published-online") or d.get("issued") or {}).get("date-parts", [[None]])[0][0]
        authors = ["%s %s" % (x.get("given", ""), x.get("family", "")) for x in d.get("author", [])]
        isbn = d.get("ISBN")
        bookf = os.path.join(a.doi_dir, "book_" + "_".join(it["doi_comment"].replace("/", "_").split("_")[:-1]) + ".json")
        vol = None
        if os.path.exists(bookf):
            try:
                bd = json.load(open(bookf, encoding="utf-8"))["message"]; vol = bd.get("volume")
            except Exception:
                vol = None
        checks = []
        tp = it["pages"][0] if it["pages"] else None
        checks.append("pages %s" % ("✓" if (tp and page and page.replace("–", "-") == "%s-%s" % tp) else "!! tex %s vs Crossref %s" % (tp, page)))
        checks.append("year %s" % ("✓" if str(yr) in it["years"] else "!! tex %s vs Crossref %s" % (it["years"], yr)))
        fam = [x.get("family", "") for x in d.get("author", [])]
        checks.append("authors %s" % ("✓ (%d: %s)" % (len(fam), ", ".join(fam)) if all(fm in it["text"] for fm in fam) else "!! Crossref %s" % fam))
        checks.append("title: %s" % title)
        checks.append("LNCS volume: %s" % (("Crossref book volume %s %s" % (vol, "✓" if vol and vol in it["volume"] else "!! tex %s" % it["volume"])) if vol else "Crossref 冇卷號 (ISBN %s; tex 寫 LNCS %s — 卷號未獨立核實)" % (isbn, it["volume"])))
        doi_rows.append((key, it["doi_comment"], "; ".join(checks)))
    L = ["# bib_check.md —— refs.bib ↔ note_v1.tex thebibliography 對齊 + Crossref DOI 核 (%s; 只標唔改)" % time.strftime("%Y-%m-%d %H:%M"), "",
         "refs.bib: %d 條; thebibliography: %d 條; 正文 \\cite 用到 %d 個 key: %s" % (len(bib), len(items), len(cited), cited), "",
         "## thebibliography 每條 → refs.bib 對應 + 差異", "", "| \\bibitem key | 正文有 cite? | refs.bib key | 差異 (year / pages / volume / 作者) | DOI 註釋 |", "|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s |" % r)
    L += ["", "- \\cite 但 thebibliography 冇: %s" % (missing_items or "無"), "- thebibliography 有但正文冇 cite: %s" % (uncited_items or "無"),
          "- refs.bib 有但 .tex 冇用 (7 條 TODO verify 之類, 唔影響 PDF): %s" % unused, "",
          "## 三條有 DOI 註釋嘅文獻 (Crossref api.crossref.org/works/<DOI>, 2026-09-06 下載, JSON 喺 paper/bib_doi/)", "", "| key | DOI | Crossref 核對 |", "|---|---|---|"]
    for r in doi_rows:
        L.append("| %s | %s | %s |" % (r[0], r[1], r[2] if len(r) == 3 else " ".join(r[2:])))
    L += ["", "註: Crossref 嘅 book-chapter 記錄唔帶 LNCS 卷號 (只有 ISBN); 卷號 7261 / 12652 / 8561 由 Springer 系列編號 (ISBN ↔ 卷) 對應, 上表標明有冇由 book-level 記錄核到. 其他文獻 (Geombinatorics 等) 冇 DOI, 未核."]
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
