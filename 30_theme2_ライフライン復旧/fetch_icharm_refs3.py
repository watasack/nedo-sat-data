#!/usr/bin/env python3
"""ICHARM調査 第3バッチ。第2バッチで判明した直URLの詰め。

(1) ICHARM側: WEB-DHM-S のプロジェクト紹介（分解能・対象流域）、玉川勝徳のスタッフページ、
    研究紹介「気候変動影響評価のための雪水文モデル(WEB-DHM-S)」、東大GEDCでの現況。
(2) 犀川ダム流入予測論文（Water 2024）の本文（MDPIが403なのでミラー経路）。
(3) 第2バッチの検索で見つかった、本案により近い先行：
    新潟大NHDR「御嶽山積雪期火山防災情報プラットフォーム」（実運用中）と
    「融雪型火山泥流リアルタイムハザードマップのための山地積雪水量推定方法の研究(4)」。
(4) 過去回（農林水産業回）の受賞結果（重複運用の実例確認）。

出力先は icharm_refs3/。トリガ: trigger-fetch-icharm3 ブランチへの push
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

OUT = Path("icharm_refs3")
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
    # (1) ICHARM 側の技術の実体
    ("icharm_project16_j", "https://www.pwri.go.jp/icharm/research/articles/project-16_j.html"),
    ("icharm_project16_e", "https://www.pwri.go.jp/icharm/research/articles/project-16.html"),
    ("icharm_research_articles", "https://www.pwri.go.jp/icharm/research/articles/index_j.html"),
    ("icharm_index_j", "https://www.icharm.pwri.go.jp/index_j.html"),
    ("icharm_index_e", "https://www.icharm.pwri.go.jp/index.html"),
    ("staff_tamakawa", "https://pwweb1.pwri.go.jp/icharm/staff/staff_tamakawa.html"),
    ("staff_index", "https://pwweb1.pwri.go.jp/icharm/staff/index.html"),
    ("icharm_ar_fy2025_gb",
     "https://www.pwri.go.jp/icharm/about/governingboard/images/10th_governingboard/"
     "4_ICHARM_activity_report_all_j.pdf"),
    ("gedc_utokyo", "https://www.gedc.u-tokyo.ac.jp/"),
    ("gedc_members", "https://www.gedc.u-tokyo.ac.jp/member/"),

    # (2) 犀川論文の本文（MDPI 403 の迂回）
    ("mdpi_pdf_res", "https://res.mdpi.com/d_attachment/water/water-16-02577/article_deploy/"
                     "water-16-02577.pdf"),
    ("mdpi_pdf_v1", "https://www.mdpi.com/2073-4441/16/18/2577/pdf?version=1726040000"),
    ("europepmc_saikawa", "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" +
     Q('"Ensemble Inflow-Prediction System" Sai River') + "&format=json&resultType=core"),
    ("scilit_saikawa", "https://www.scilit.com/publications?q=" + Q("10.3390/w16182577")),
    ("semanticscholar_doi",
     "https://api.semanticscholar.org/graph/v1/paper/DOI:10.3390/w16182577"
     "?fields=title,abstract,year,authors,externalIds,openAccessPdf"),
    ("unpaywall", "https://api.unpaywall.org/v2/10.3390/w16182577?email=research@example.org"),

    # (3) より近い先行：新潟大NHDR
    ("nhdr_ontake_platform", "https://platform.nhdr.niigata-u.ac.jp/ontake/index.php?help"),
    ("nhdr_ontake_top", "https://platform.nhdr.niigata-u.ac.jp/ontake/"),
    ("nhdr_platform_top", "https://platform.nhdr.niigata-u.ac.jp/"),
    ("nhdr_swe_report4", "https://www.nhdr.niigata-u.ac.jp/wp-content/uploads/2026/04/"
                         "e1c3b068b256434949714dfd03fcfb2e.pdf"),
    ("nhdr_top", "https://www.nhdr.niigata-u.ac.jp/"),
    ("nhdr_results", "https://www.nhdr.niigata-u.ac.jp/research/"),
    ("pwri_kyoudou_0547", "https://www.icharm.pwri.go.jp/jpn/results/db/doken_kankoubutu/"
                          "kyoudoukenkyu_houkokusyo/files/doken_kyoudoukenkyu_0547_00.pdf"),

    # (4) 過去回の重複運用の実例
    ("nedo_aff_result_press", "https://www.nedo.go.jp/news/press/AA5_101851.html"),
    ("prtimes_fishpass", "https://prtimes.jp/main/html/rd/p/000000036.000118467.html"),
    ("sorabatake_43566", "https://sorabatake.jp/43566/"),

    # (5) 検索フォールバック
    ("ddg_ontake_platform", "https://html.duckduckgo.com/html/?q=" +
     Q("御嶽山積雪期火山防災情報プラットフォーム 新潟大学 積雪水量")),
    ("bing_ontake_platform", "https://www.bing.com/search?q=" +
     Q("御嶽山積雪期火山防災情報プラットフォーム 新潟大学")),
    ("bing_nhdr_swe", "https://www.bing.com/search?q=" +
     Q("融雪型火山泥流 リアルタイムハザードマップ 山地積雪水量 推定 新潟大学 機械学習")),
    ("bing_web_dhm_s_res", "https://www.bing.com/search?q=" +
     Q("WEB-DHM-S 犀川 メッシュ 解像度 500m 1km 積雪 モデル")),
    ("bing_tamakawa_gedc", "https://www.bing.com/search?q=" +
     Q("玉川勝徳 東京大学 地球環境データコモンズ")),
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
    if data[:5] == b"%PDF":
        ext = ".pdf"
    elif "json" in ctype or "api." in url or "webservices/rest" in url:
        ext = ".json"
    else:
        ext = ".html"
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=(ext == ".pdf"))
    if ext == ".pdf":
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    return rec


def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t　]+", " ", s)
    return "\n".join(l.strip() for l in s.split("\n") if l.strip())


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        out.append("=" * 70)
        out.append(f"FILE: {t.name}")
        out.append(t.read_text(errors="replace")[:120_000])
    OUT.joinpath("_digest_pdf.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        out2.append("=" * 70)
        out2.append(f"FILE: {h.name}")
        out2.append(strip_html(h.read_text("utf-8", "replace"))[:45_000])
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))

    out3 = []
    for j in sorted(OUT.glob("*.json")):
        out3.append("=" * 70)
        out3.append(f"FILE: {j.name}")
        out3.append(j.read_text("utf-8", "replace")[:50_000])
    OUT.joinpath("_digest_api.txt").write_text("\n".join(out3))


def main():
    OUT.mkdir(exist_ok=True)
    man = [fetch(n, u) for n, u in TARGETS]
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print(f"fetched {len(man)}, ok={sum(1 for r in man if r.get('status') == 200)}")


if __name__ == "__main__":
    main()
