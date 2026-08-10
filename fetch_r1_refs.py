#!/usr/bin/env python3
"""R1候補（線状インフラの第三者行為監視・単独埋設区間）の即死条件を取る

**第8の関門を生成の条件に変えた結果、出てきた候補を検証する。**

3巡の深掘りで、生き残った候補が最後に死ぬ場所は毎回「その顧客をいま誰が押さえているか」だった
（公共なら所管官庁か測量・建設コンサル、民間ならドローン・航空のベンダ）。
そこで**逆から引く**——**ドローン・航空・地上巡視が原理的に使えない構図**を先に決めて、そこから候補を作る。

**使えなくなる条件は1つに絞れる: 見る側と見られる側が違い、対象が他人の土地にあること。**
他人の土地の上空でドローンは飛ばせず、立入もできない。**衛星だけが許可を要さない。**

これに当たる構図が線状インフラの第三者行為監視である。ガス導管・送電線・鉄道は、
**自社用地の外側**で起きる第三者の掘削・盛土・造成によって損傷する。現状の手段は徒歩・車両・
ヘリコプターによる巡視で、頻度と網羅性に限界がある。

**案A（他工事損傷）が型②で死んだのは「都市の道路断面にガス・電力・通信・水道が離隔1m未満で並走する」
からだった。単独埋設の郊外・山間区間に絞ればこの幾何は成立しない。** その絞り込みが妥当かを確かめる。

| # | 閉じたい問い |
|---|---|
| 1 | **例外(a)**: LiveEO 等が国内の導管・鉄道・送電の管理者へ商用展開しているか |
| 2 | **痛みの一次出典**: 他工事による埋設物損傷の件数・被害（ガス・電力・通信） |
| 3 | **現状の手段**: 導管・送電・鉄道の巡視がどう行われているか（頻度・手段） |
| 4 | **母数**: 高圧ガス導管の延長、送電線亘長、鉄道営業キロ |

`trigger-fetch-r1` ブランチへの push で起動 → `r1-refs` ブランチにコミット。
**判断はこのスクリプトがしない。**
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("r1_refs")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

SEEDS = [
    # === 1. 例外(a): 海外の同種サービスと国内展開 ===
    ("v_liveeo", "https://www.live-eo.com/"),
    ("v_liveeo_pipeline", "https://www.live-eo.com/solutions/pipeline"),
    ("v_liveeo_rail", "https://www.live-eo.com/solutions/rail"),
    ("v_orbitaleye", "https://orbitaleye.nl/"),
    ("v_satelytics", "https://satelytics.com/"),

    # === 2. 痛み: 他工事損傷・埋設物事故の統計 ===
    ("gas_jga", "https://www.gas.or.jp/"),
    ("gas_hoan", "https://www.gas.or.jp/anzen/"),
    ("meti_gas_jiko", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/gas/index.html"),
    ("khk_top", "https://www.khk.or.jp/"),

    # === 3. 現状の手段: 巡視 ===
    ("gas_dokan_hoan", "https://www.gas.or.jp/gas-life/anzen/"),
    ("tepco_soden", "https://www.tepco.co.jp/pg/"),

    # === 4. 母数 ===
    ("gas_toukei", "https://www.gas.or.jp/tokei/"),
    ("enecho_gas", "https://www.enecho.meti.go.jp/statistics/gas/"),
    ("mlit_tetsudo", "https://www.mlit.go.jp/tetudo/index.html"),
]

# 研究先行（サーバ側レンダリングでbot判定なし）
CINII = "https://cir.nii.ac.jp/all?q={q}"
CROSSREF = "https://api.crossref.org/works?query.bibliographic={q}&rows=15&select=title,issued"

QUERIES = [
    ("takoji_songai", "他工事 損傷 埋設管 防止"),
    ("pipeline_sat", "パイプライン 第三者 損傷 衛星 監視"),
    ("tetsudo_shamen", "鉄道 沿線 斜面 衛星 監視"),
    ("soden_kaihen", "送電線 用地 土地改変 衛星"),
]
EN_QUERIES = [
    ("en_tpi", "pipeline third party interference satellite monitoring"),
    ("en_rail_slope", "railway lineside slope satellite InSAR monitoring third party"),
]


class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

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
        "User-Agent": UA, "Accept": "*/*", "Accept-Language": "ja,en;q=0.8"})
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
        suffix = ".json" if "json" in low else (".pdf" if "pdf" in low else ".html")
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
    print("=== ベンダ・官庁・統計 ===")
    for name, url in SEEDS:
        save(name, url, manifest)
    print("\n=== 研究先行（和文） ===")
    for key, q in QUERIES:
        save(f"q_{key}_cinii", CINII.format(q=urllib.parse.quote(q)), manifest, note=q)
    print("\n=== 研究先行（英語） ===")
    for key, q in EN_QUERIES:
        save(f"q_{key}_crossref", CROSSREF.format(q=urllib.parse.quote(q)), manifest, note=q)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")
    print(f"未取得: {[m['url'] for m in manifest if m.get('status') != 200]}")


if __name__ == "__main__":
    main()
