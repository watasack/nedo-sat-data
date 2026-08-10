#!/usr/bin/env python3
"""S3 を現行テーマ1と差し替えられるかを決めるための取得（第3巡・決定用）

第2巡までで S3 に残っている穴は3つ。**この3つが埋まれば差し替えの是非が判定できる。**

| # | 穴 | 取り方 |
|---|---|---|
| **1** | **母数**（事業用の野立てPVが何件・何MWあるか）。⑤の社会的インパクトと市場規模がここで決まる | FIT情報公表サイトの統計表 |
| **2** | **例外(a)の残り半分**。CiNii は和文学術しか見ておらず、**英語圏の研究と商用サービス**が未確認 | Semantic Scholar / arXiv / Crossref の公開API（bot判定を持たない）＋ 主要ベンダのサイト直 |
| **3** | **痛みの一次出典**（②の課題の妥当性）。PV設備の事故・被災がどれだけ起きているか | 経産省の電気保安・事故報告 |

**あわせて例外(b)の判定材料**も取る——再エネ設備を対象にすると Green Earth（カーボンクレジット／
エネルギーマネジメント／気候変動・環境レジリエンス）を主たる目的と見られる危険がある。
**主たる目的を「設備の保安と災害リスク低減」に置けるかは事務局照会で確定させるしかない**が、
その質問文を書くために制度側の言葉を揃えておく。

`trigger-fetch-s3d` ブランチへの push で起動 → `s3-decisive` ブランチにコミット。

**判断はこのスクリプトがしない。** 資料を運ぶだけである。
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("s3_decisive")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

SEEDS = [
    # === 1. 母数: FIT 認定・導入状況の統計表 ===
    ("fit_summary", "https://www.fit-portal.go.jp/PublicInfoSummary"),
    ("fit_toukei_enecho", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/statistics/"),
    ("fit_kaitori_jisseki", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/kaitori/kakaku.html"),

    # === 3. 痛み: 電気設備の事故報告・太陽光の被災 ===
    ("meti_denki_hoan", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/index.html"),
    ("meti_jiko_houkoku", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/detail/denki_hoan.html"),
    ("nite_denki", "https://www.nite.go.jp/"),

    # === 例外(b) の判定材料: 今回テーマとGreen Earthの境界 ===
    ("koubo_site", "https://space-data-challenge.nedo.go.jp/"),
    ("green_earth_site", "https://space-data-challenge.nedo.go.jp/green_earth"),

    # === 2b. 商用の先行（英語圏の主要ベンダ。サイト直） ===
    ("v_raptormaps", "https://raptormaps.com/"),
    ("v_sitemark", "https://www.sitemark.com/"),
    ("v_heliolytics", "https://heliolytics.com/"),
    ("v_abovesurveying", "https://www.abovesurveying.com/"),
    ("v_solarpower_sat", "https://www.dnv.com/services/solar-energy-services/"),
]

# === 2a. 英語圏の研究先行（公開API。JSON。bot判定を持たない） ===
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=20&fields=title,year,venue,abstract"
CROSSREF = "https://api.crossref.org/works?query={q}&rows=20&select=title,issued,container-title"
ARXIV = "http://export.arxiv.org/api/query?search_query=all:{q}&max_results=20"

EN_QUERIES = [
    ("pv_sat_monitor", "solar photovoltaic plant satellite monitoring operation maintenance"),
    ("pv_vegetation", "photovoltaic plant vegetation encroachment remote sensing"),
    ("pv_detection", "solar farm detection Sentinel-2 deep learning"),
    ("pv_risk_insurance", "photovoltaic plant natural hazard risk assessment insurance"),
]


class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def strip_tags(html: str) -> str:
    p = TagStripper()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(p.parts)
    text = re.sub(r"[ \t　]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def fetch(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def save(name: str, url: str, manifest: list, note: str = ""):
    entry = {"name": name, "url": url}
    if note:
        entry["note"] = note
    try:
        status, ctype, body = fetch(url)
        entry.update(status=status, content_type=ctype, bytes=len(body))
        low = ctype.lower()
        if "json" in low:
            suffix = ".json"
        elif "xml" in low or "atom" in low:
            suffix = ".xml"
        elif "pdf" in low or url.lower().endswith(".pdf"):
            suffix = ".pdf"
        else:
            suffix = ".html"
        (OUT / (name + suffix)).write_bytes(body)
        entry["file"] = name + suffix
        if suffix == ".html":
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                text = body.decode("cp932", errors="replace")
            (OUT / (name + ".txt")).write_text(strip_tags(text), encoding="utf-8")
            entry["text_file"] = name + ".txt"
        print(f"OK   {status} {len(body):>9,}  {url}")
    except urllib.error.HTTPError as e:
        entry.update(status=e.code, error=f"HTTPError {e.code}")
        print(f"FAIL {e.code} {url}")
    except Exception as e:
        entry.update(status=None, error=f"{type(e).__name__}: {e}")
        print(f"FAIL --- {url}  {type(e).__name__}: {e}")
    manifest.append(entry)
    time.sleep(1.5)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    print("=== 官庁・ベンダのページ ===")
    for name, url in SEEDS:
        save(name, url, manifest)

    print("\n=== 英語圏の研究先行（公開API） ===")
    for key, q in EN_QUERIES:
        enc = urllib.parse.quote(q)
        save(f"en_{key}_s2", S2_API.format(q=enc), manifest, note=q)
        save(f"en_{key}_crossref", CROSSREF.format(q=enc), manifest, note=q)
        save(f"en_{key}_arxiv", ARXIV.format(q=urllib.parse.quote(q.replace(" ", "+AND+"))), manifest, note=q)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")
    print(f"未取得: {[m['url'] for m in manifest if m.get('status') != 200]}")


if __name__ == "__main__":
    main()
