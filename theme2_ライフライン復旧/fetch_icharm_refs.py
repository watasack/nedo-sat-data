#!/usr/bin/env python3
"""ICHARM／玉川勝徳の「降雪・積雪・融雪量リアルタイム解析プラットフォーム」の実体調査。

過去回 NEDO Challenge, Satellite Data for Green Earth テーマ②の審査委員特別賞受賞案が、
(a) 先行技術・競合として何を作ったのか（分解能・範囲・期間・手法・検証）
(b) 制度上の「重複」判定にどう効くか
を一次情報で確かめるための取得スクリプト。

出力先は icharm_refs/。トリガ: trigger-fetch-icharm ブランチへの push
"""

import gzip
import io
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

OUT = Path("icharm_refs")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

QJ = urllib.parse.quote


# ---------- (1) DIAS（受賞の告知元。プラットフォームの実体があるならここ） ----------
DIAS = [
    ("dias_topic_en", "https://diasjp.net/en/information/topics/20250517-nedochallenge-icharm/"),
    ("dias_topic_ja", "https://diasjp.net/information/topics/20250517-nedochallenge-icharm/"),
    ("dias_topics_ja", "https://diasjp.net/information/topics/"),
    ("dias_topics_en", "https://diasjp.net/en/information/topics/"),
    ("dias_applist", "https://diasjp.net/app_list/"),
    ("dias_applist_en", "https://diasjp.net/en/app_list/"),
    ("dias_top", "https://diasjp.net/"),
    ("dias_search_snow", "https://diasjp.net/?s=" + QJ("積雪")),
    ("dias_dataset", "https://search.diasjp.net/en/dataset?q=snow"),
]

# ---------- (2) ICHARM / 土木研究所 ----------
ICHARM = [
    ("icharm_top", "https://www.pwri.go.jp/icharm/"),
    ("icharm_top_en", "https://www.pwri.go.jp/icharm/index_e.html"),
    ("icharm_news", "https://www.pwri.go.jp/icharm/news/index.html"),
    ("icharm_topics", "https://www.pwri.go.jp/icharm/topics/index.html"),
    ("icharm_research", "https://www.pwri.go.jp/icharm/research/index.html"),
    ("icharm_member", "https://www.pwri.go.jp/icharm/about/member/index.html"),
    ("icharm_pro2_2016", "https://www.pwri.go.jp/icharm/research/pdf/pro_2_2016.pdf"),
    ("icharm_activity_fy2023",
     "https://www.pwri.go.jp/icharm/about/governingboard/images/8th_governingboard/"
     "4_ICHARM_activity_report_all_j.pdf"),
    ("icharm_gb_index", "https://www.pwri.go.jp/icharm/about/governingboard/index.html"),
    ("icharm_gb_index_e", "https://www.pwri.go.jp/icharm/about/governingboard/index_e.html"),
    ("pwri_top", "https://www.pwri.go.jp/"),
    ("pwri_news", "https://www.pwri.go.jp/jpn/news/index.html"),
    ("pwri_results", "https://www.pwri.go.jp/jpn/results/index.html"),
    ("pwri_annual", "https://www.pwri.go.jp/jpn/about/pr/nenpou/nenpou.html"),
    ("pwri_search_tamagawa",
     "https://www.pwri.go.jp/search.html?q=" + QJ("玉川勝徳")),
]

# ---------- (3) 文献データベース ----------
NAME_J = "玉川勝徳"
NAME_E = "Katsunori Tamagawa"

LIT = [
    # CiNii Research OpenSearch
    ("cinii_tamagawa_j", "https://cir.nii.ac.jp/opensearch/all?q=" + QJ(NAME_J) +
     "&format=json&count=100"),
    ("cinii_tamagawa_e", "https://cir.nii.ac.jp/opensearch/all?q=" + QJ(NAME_E) +
     "&format=json&count=100"),
    ("cinii_icharm_snow", "https://cir.nii.ac.jp/opensearch/all?q=" +
     QJ("ICHARM 積雪") + "&format=json&count=50"),
    # J-STAGE WebAPI（service=3: 論文検索）
    ("jstage_tamagawa", "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" +
     QJ(NAME_J) + "&count=100"),
    ("jstage_tamagawa_en", "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" +
     QJ("Tamagawa snow") + "&count=100"),
    ("jstage_swe_mountain", "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" +
     QJ("積雪水量 衛星 山地") + "&count=100"),
    # KAKEN / NRID
    ("kaken_tamagawa", "https://nrid.nii.ac.jp/opensearch/?qm=" + QJ(NAME_J)),
    ("kaken_search_html", "https://kaken.nii.ac.jp/ja/search/?qm=" + QJ(NAME_J)),
    # researchmap
    ("researchmap_search", "https://researchmap.jp/researchers?q=" + QJ(NAME_J)),
    ("researchmap_api", "https://api.researchmap.jp/search/researchers?format=json&name=" +
     QJ(NAME_J)),
    # OpenAlex / Crossref / Semantic Scholar / OpenAIRE
    ("openalex_author", "https://api.openalex.org/authors?search=" + QJ(NAME_E)),
    ("openalex_works", "https://api.openalex.org/works?search=" +
     QJ("Tamagawa snow water equivalent") + "&per-page=50"),
    ("openalex_works2", "https://api.openalex.org/works?filter=" +
     QJ("raw_author_name.search:Tamagawa,title_and_abstract.search:snow") + "&per-page=50"),
    ("crossref_tamagawa", "https://api.crossref.org/works?query.author=" + QJ("Tamagawa") +
     "&query.bibliographic=" + QJ("snow") + "&rows=50"),
    ("crossref_icharm_snow", "https://api.crossref.org/works?query.affiliation=" +
     QJ("ICHARM") + "&query.bibliographic=" + QJ("snow") + "&rows=50"),
    ("s2_tamagawa", "https://api.semanticscholar.org/graph/v1/paper/search?query=" +
     QJ("Tamagawa snow water equivalent Japan") +
     "&fields=title,year,abstract,authors,venue,externalIds&limit=50"),
    ("s2_author", "https://api.semanticscholar.org/graph/v1/author/search?query=" +
     QJ(NAME_E) + "&fields=name,affiliations,paperCount,papers.title,papers.year"),
    ("openaire_tamagawa", "https://api.openaire.eu/search/publications?author=" + QJ("Tamagawa") +
     "&keywords=snow&size=50"),
    # 機関リポジトリ横断
    ("irdb_tamagawa", "https://irdb.nii.ac.jp/api/opensearch?q=" + QJ(NAME_J)),
    # 土木学会論文集（水工学論文集）などのタイトル検索
    ("jstage_ronbun_tamagawa", "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" +
     QJ("玉川 積雪 融雪 流出") + "&count=100"),
]

# ---------- (4) 検索エンジンHTML（スニペット採取のフォールバック） ----------
QUERIES = [
    '"玉川勝徳" 積雪',
    '"玉川勝徳" ICHARM',
    '"玉川勝徳" 融雪 水力',
    'ICHARM 降雪 積雪 融雪 リアルタイム 解析 プラットフォーム NEDO',
    '"Katsunori Tamagawa" snow',
    'ICHARM snow water equivalent platform real-time NEDO Challenge',
    'ICHARM 積雪 水力発電 ダム 運用 衛星 実証',
    '土木研究所 ICHARM 積雪 プラットフォーム 公開',
    'NEDO Challenge Green Earth 受賞後 事業化 積雪 ICHARM',
    '融雪型火山泥流 積雪水量 ICHARM',
]
SEARCH = []
for i, q in enumerate(QUERIES):
    SEARCH.append((f"ddg_{i}", "https://html.duckduckgo.com/html/?q=" + QJ(q)))
    SEARCH.append((f"ddglite_{i}", "https://lite.duckduckgo.com/lite/?q=" + QJ(q)))
    SEARCH.append((f"bing_{i}", "https://www.bing.com/search?q=" + QJ(q)))
    SEARCH.append((f"mojeek_{i}", "https://www.mojeek.com/search?q=" + QJ(q)))

# ---------- (5) NEDO / 過去回の重複規定まわり（目的2の裏取り） ----------
NEDO = [
    ("nedo_ge_index", "https://space-data-challenge.nedo.go.jp/green_earth/"),
    ("nedo_aff_index", "https://space-data-challenge.nedo.go.jp/aff/"),
    ("nedo_aff_guidelines",
     "https://space-data-challenge.nedo.go.jp/aff/file/Application_Guidelines.pdf"),
    ("nedo_ge_guidelines",
     "https://space-data-challenge.nedo.go.jp/green_earth/pdf/Application_requirements.pdf"),
    ("nedo_infra_index", "https://space-data-challenge.nedo.go.jp/infrastructure/"),
    ("nedo_press_aff_result", "https://www.nedo.go.jp/news/press/AA5_101851.html"),
    ("nedo_news_index", "https://www.nedo.go.jp/news/press/presslist.html"),
    ("sorabatake_ge_final", "https://sorabatake.jp/39615/"),
    ("prtimes_icharm", "https://prtimes.jp/main/html/searchrlp/company_id/118467"),
]


def _read(r):
    d = r.read()
    enc = (r.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            d = gzip.decompress(d)
        elif enc == "deflate":
            d = zlib.decompress(d, -zlib.MAX_WBITS)
    except Exception:
        try:
            d = gzip.GzipFile(fileobj=io.BytesIO(d)).read()
        except Exception:
            pass
    return d


def fetch(name, url, cap=50_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=180) as r:
            data = _read(r)
            rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
            rec["final_url"] = r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
        try:
            body = _read(e)
            if body:
                (OUT / f"{name}_err.txt").write_bytes(body[:200_000])
        except Exception:
            pass
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec
    if len(data) > cap:
        rec["truncated_from"] = len(data)
        data = data[:cap]
    pdf = data[:5] == b"%PDF"
    if pdf:
        ext = ".pdf"
    elif "json" in ctype or "format=json" in url or "api." in url:
        ext = ".json"
    elif "xml" in ctype:
        ext = ".xml"
    else:
        ext = ".html"
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=pdf)
    if pdf:
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    return rec


PDF_KEY = re.compile(r"積雪|融雪|降雪|snow|ICHARM|活動報告|activity|年報|成果")


def crawl(name, url, man, seen, limit=12):
    """HTMLページ内の関連PDFを1階層だけ追う。"""
    rec = fetch(name, url)
    man.append(rec)
    f = rec.get("file")
    if not f or not f.endswith(".html"):
        return
    html = Path(f).read_text("utf-8", "replace")
    for m in re.finditer(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        full = urllib.parse.urljoin(rec.get("final_url") or url, href)
        if full in seen:
            continue
        if not (PDF_KEY.search(label) or PDF_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        safe = re.sub(r"[^0-9A-Za-z　-鿿]+", "_", label)[:40] or "pdf"
        sub = fetch(f"{name}__{safe}", full, cap=40_000_000)
        sub.update(from_index=name, label=label)
        man.append(sub)
        limit -= 1
        if limit <= 0:
            break


KEYS_J = ["玉川", "ICHARM", "積雪水量", "積雪深", "融雪", "降雪", "プラットフォーム",
          "分解能", "メッシュ", "標高", "山岳", "水力", "ダム", "リアルタイム",
          "再解析", "葉面積指数", "LAI", "積雪域", "火山", "泥流", "NEDO"]
KEYS_E = ["Tamagawa", "ICHARM", "snow water equivalent", "SWE", "snowmelt", "snow cover",
          "resolution", "mesh", "real-time", "reanalysis", "leaf area index",
          "hydropower", "mountain", "elevation", "platform", "NEDO"]


def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t　]+", " ", s)


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        rows = t.read_text(errors="replace").split("\n")
        hits = [f"[L{i}]\n" + "\n".join(rows[max(0, i - 2):i + 3])
                for i, ln in enumerate(rows)
                if any(k in ln for k in KEYS_J) or any(k.lower() in ln.lower() for k in KEYS_E)]
        if hits:
            out.append("=" * 70)
            out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n---\n".join(hits[:60]))
    OUT.joinpath("_digest_txt.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        s = strip_html(h.read_text("utf-8", "replace"))
        s = re.sub(r"\s+", " ", s)
        pat = "|".join(re.escape(k) for k in ["玉川", "ICHARM", "積雪", "融雪", "降雪",
                                              "Tamagawa", "snow"])
        frags, used = [], set()
        for m in re.finditer(pat, s, re.I):
            st = max(0, m.start() - 350)
            if any(abs(st - u) < 200 for u in used):
                continue
            used.add(st)
            frags.append(s[st:m.start() + 450])
            if len(frags) >= 40:
                break
        if frags:
            out2.append("=" * 70)
            out2.append(f"FILE: {h.name}")
            out2.append("\n---\n".join(frags))
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))

    out3 = []
    for j in sorted(list(OUT.glob("*.json")) + list(OUT.glob("*.xml"))):
        raw = j.read_text("utf-8", "replace")
        out3.append("=" * 70)
        out3.append(f"FILE: {j.name} bytes={len(raw)}")
        out3.append(raw[:60_000])
    OUT.joinpath("_digest_api.txt").write_text("\n".join(out3))


def main():
    OUT.mkdir(exist_ok=True)
    man, seen = [], set()
    for name, url in DIAS + ICHARM + NEDO:
        crawl(name, url, man, seen)
    for name, url in LIT + SEARCH:
        man.append(fetch(name, url))
    OUT.joinpath("manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    ok = sum(1 for r in man if r.get("status") == 200)
    print(f"fetched {len(man)} entries, {ok} ok")


if __name__ == "__main__":
    main()
