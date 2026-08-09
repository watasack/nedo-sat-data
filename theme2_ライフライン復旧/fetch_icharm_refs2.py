#!/usr/bin/env python3
"""ICHARM／玉川勝徳の積雪プラットフォーム調査 第2バッチ（直URL狙い撃ち）。

第1バッチの検索で判明した一次情報の直URLを取りに行く。
- ICHARM 特設ページ（NEDO受賞告知の原文）
- ICHARM Activity Report FY2018-2019 / FY2023 / FY2024（土研資料No.4469）
- NEDO 受賞者一覧・懸賞金プログラムのページ
- WEB-DHM-S 関連論文（犀川ダム流入予測、Water 2024 ほか）
- 玉川勝徳の既往論文（マイクロ波による積雪量推定 ほか）

出力先は icharm_refs2/。トリガ: trigger-fetch-icharm2 ブランチへの push
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

OUT = Path("icharm_refs2")
Q = urllib.parse.quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

TARGETS = [
    # --- ICHARM 受賞告知の原文（最重要） ---
    ("icharm_nedo_topic", "https://www.pwri.go.jp/icharm/special_topic/20250423_nedo.html"),
    ("icharm_nedo_topic_j", "https://www.pwri.go.jp/icharm/special_topic/20250423_nedo_j.html"),
    ("icharm_topic_index", "https://www.pwri.go.jp/icharm/special_topic/index.html"),
    ("icharm_topic_index_j", "https://www.pwri.go.jp/icharm/special_topic/index_j.html"),
    ("pwri_news_2025", "https://www.pwri.go.jp/news/"),
    ("pwri_news_r7", "https://www.pwri.go.jp/jpn/news/2025/index.html"),
    ("pwri_team_index", "https://www.pwri.go.jp/jpn/research/team/index.html"),
    ("icharm_org_staff_j",
     "https://www.pwri.go.jp/icharm/about/organization_and_staff_j.html"),
    ("icharm_org_staff_e",
     "https://www.pwri.go.jp/icharm/about/organization_and_staff.html"),

    # --- ICHARM Activity Report（年次の実体。積雪プラットフォームの進捗が載る） ---
    ("icharm_ar_fy2024_thesis", "https://thesis.pwri.go.jp/files/15707710836a163ecf246a8.pdf"),
    ("icharm_ar_fy2024_gb",
     "https://www.pwri.go.jp/icharm/about/governingboard/images/9th_governingboard/"
     "4_ICHARM_activity_report_all_j.pdf"),
    ("icharm_ar_fy2023_gb",
     "https://www.pwri.go.jp/icharm/about/governingboard/images/8th_governingboard/"
     "4_ICHARM_activity_report_all_j.pdf"),
    ("icharm_ar_fy2018_19",
     "https://www.pwri.go.jp/icharm/special_topic/20200609_GoverningBoard/"
     "4_Activity%20Report_j.pdf"),
    ("icharm_pro2_2016", "https://www.pwri.go.jp/icharm/research/pdf/pro_2_2016.pdf"),
    ("pwri_thesis_search_tamagawa", "https://thesis.pwri.go.jp/search?q=" + Q("玉川勝徳")),
    ("pwri_thesis_top", "https://thesis.pwri.go.jp/"),

    # --- NEDO 側 ---
    ("nedo_100980452", "https://www.nedo.go.jp/content/100980452.pdf"),
    ("nedo_awardees", "https://www.nedo.go.jp/activities/ZZJP2_100419.html"),
    ("nedo_prog", "https://www.nedo.go.jp/activities/ZZJP_100268.html"),
    ("nedo_ge_index2", "https://space-data-challenge.nedo.go.jp/green_earth/index.html"),
    ("nedo_webmag_prize07", "https://webmagazine.nedo.go.jp/pickupnews/prize07.html"),

    # --- WEB-DHM-S / 犀川ダム流入予測（技術の実体） ---
    ("mdpi_w16182577", "https://www.mdpi.com/2073-4441/16/18/2577"),
    ("mdpi_w16182577_pdf", "https://www.mdpi.com/2073-4441/16/18/2577/pdf"),
    ("doaj_saikawa", "https://doaj.org/api/search/articles/" +
     Q('title:"Ensemble Inflow-Prediction System for Upstream Reservoirs in Sai River"')),
    ("crossref_w16182577", "https://api.crossref.org/works/10.3390/w16182577"),
    ("hess_web_dhm_s", "https://hess.copernicus.org/articles/14/2577/2010/hess-14-2577-2010.pdf"),

    # --- 玉川勝徳の既往論文（マイクロ波SWE推定、水工学論文集） ---
    ("jstage_search_tamagawa_ronbun",
     "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" +
     Q("マイクロ波放射伝達理論 積雪量 積雪粒径 推定 衛星 アルゴリズム") + "&count=50"),
    ("jstage_search_tamagawa_name",
     "https://api.jstage.jst.go.jp/searchapi/do?service=3&text=" + Q("玉川勝徳") + "&count=100"),
    ("cinii_tamagawa2", "https://cir.nii.ac.jp/opensearch/all?q=" + Q("玉川勝徳") +
     "&format=json&count=200"),
    ("cinii_tamagawa_creator", "https://cir.nii.ac.jp/opensearch/all?creator=" + Q("玉川勝徳") +
     "&format=json&count=200"),
    ("openalex_tamagawa_raw", "https://api.openalex.org/works?filter=" +
     Q("raw_author_name.search:Katsunori Tamagawa") + "&per-page=100"),
    ("openalex_pwri_snow", "https://api.openalex.org/works?filter=" +
     Q("raw_affiliation_strings.search:ICHARM,title_and_abstract.search:snow") + "&per-page=100"),
    ("s2_tamagawa2", "https://api.semanticscholar.org/graph/v1/paper/search?query=" +
     Q("Tamagawa snow depth microwave") +
     "&fields=title,year,abstract,authors,venue,externalIds&limit=100"),
    ("scholar_researchmap", "https://researchmap.jp/search?q=" + Q("玉川勝徳")),

    # --- 山岳・高標高での積雪検証、火山への言及 ---
    ("ddg_icharm_volcano", "https://html.duckduckgo.com/html/?q=" +
     Q("ICHARM 積雪 火山 泥流 玉川")),
    ("ddg_platform_url", "https://html.duckduckgo.com/html/?q=" +
     Q('ICHARM 積雪 "プラットフォーム" 公開 URL 積雪水量 マップ')),
    ("ddg_tamagawa_all", "https://html.duckduckgo.com/html/?q=" + Q('"玉川勝徳"')),
    ("bing_tamagawa_all", "https://www.bing.com/search?q=" + Q('"玉川勝徳"') + "&count=50"),
    ("mojeek_tamagawa_all", "https://www.mojeek.com/search?q=" + Q('"玉川勝徳"')),
    ("ddg_tamagawa_en", "https://html.duckduckgo.com/html/?q=" + Q('"Katsunori Tamagawa" snow')),
    ("bing_icharm_swe", "https://www.bing.com/search?q=" +
     Q('ICHARM snow water equivalent platform DIAS real-time')),
    ("ddg_snowdias", "https://html.duckduckgo.com/html/?q=" +
     Q('DIAS 積雪 プラットフォーム ICHARM 融雪 リアルタイム 公開')),

    # --- 制度: 過去回要項の原本（重複規定の文言比較） ---
    ("nedo_aff_guidelines2",
     "https://space-data-challenge.nedo.go.jp/aff/file/Application_Guidelines.pdf"),
    ("nedo_aff_session",
     "https://space-data-challenge.nedo.go.jp/aff/file/Application_Information_Session.pdf"),
    ("nedo_ge_requirements",
     "https://space-data-challenge.nedo.go.jp/green_earth/pdf/Application_requirements.pdf"),
    ("nedo_aff_awards", "https://space-data-challenge.nedo.go.jp/aff/"),
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


def fetch(name, url, cap=60_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120) as r:
            data = _read(r)
            rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
            rec["final_url"] = r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
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
    elif "json" in ctype or "api." in url or "doaj.org/api" in url:
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


KEYS = ["玉川", "Tamagawa", "積雪", "融雪", "降雪", "snow", "SWE", "分解能", "resolution",
        "メッシュ", "mesh", "標高", "elevation", "山岳", "mountain", "リアルタイム",
        "real-time", "プラットフォーム", "platform", "GSMaP", "MODIS", "LAI", "再解析",
        "reanalysis", "火山", "volcan", "泥流", "lahar", "NEDO", "水力", "hydropower",
        "ダム", "dam", "犀川", "Sai River", "WEB-DHM"]


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
                if any(k.lower() in ln.lower() for k in KEYS)]
        if hits:
            out.append("=" * 70)
            out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n---\n".join(hits[:80]))
    OUT.joinpath("_digest_txt.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        s = re.sub(r"\s+", " ", strip_html(h.read_text("utf-8", "replace")))
        out2.append("=" * 70)
        out2.append(f"FILE: {h.name} len={len(s)}")
        out2.append(s[:40_000])
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))

    out3 = []
    for j in sorted(list(OUT.glob("*.json")) + list(OUT.glob("*.xml"))):
        raw = j.read_text("utf-8", "replace")
        out3.append("=" * 70)
        out3.append(f"FILE: {j.name} bytes={len(raw)}")
        out3.append(raw[:80_000])
    OUT.joinpath("_digest_api.txt").write_text("\n".join(out3))


def main():
    OUT.mkdir(exist_ok=True)
    man = [fetch(n, u) for n, u in TARGETS]
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print(f"fetched {len(man)}, ok={sum(1 for r in man if r.get('status') == 200)}")


if __name__ == "__main__":
    main()
