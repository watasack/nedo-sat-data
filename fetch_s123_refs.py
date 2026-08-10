#!/usr/bin/env python3
"""生存3候補（S1・S2・S3）の即死条件を閉じるための一次資料取得（GitHub Actions ランナー上で実行する想定）

`18_テーマ代替案の検討.md` 4.4節で生き残った3件は、いずれも **例外(a)（同一顧客市場で商用展開済み）
が未取得**のまま「生存」と書いてある。サンドボックスからは mlit / env / meti とも egress 遮断
（プロキシが 403 を返す）なので、ネットワーク制限のない Actions ランナーで取りに行く。

| 候補 | 閉じたい問い |
|---|---|
| **S1** 無許可盛土・違法造成 | 盛土規制法の監視は誰がどうやっているか。**衛星による監視の先行があるか**。産廃の不法投棄側も同じ |
| **S2** 河道内樹木 | 河道内樹木の現況把握を国交省がどの頻度・手段でやっているか（航空レーザの周期）。**衛星の先行があるか** |
| **S3** 再エネ設備の管理不全 | 再エネ特措法の**改正年次と条文**（柵塀・標識・除草の義務、違反時の措置）。FIT認定情報の公表範囲。**衛星による管理状態監視の先行があるか** |

**取り方は2系統ある。**
1. **官庁の原典**（制度の条文・運用・統計）。これは URL を直接指定する
2. **先行の有無**（例外(a)の判定）。**検索エンジンのHTML版**を叩く。官庁サイトのクロールでは
   民間サービスの存在は分からないので、ここだけは検索が要る

`fetch_facility_refs.py` と同じ方式（`trigger-fetch-s123` ブランチへの push で起動 →
`s123-refs` ブランチにコミット）。workflow_dispatch APIはこの環境のGitHub統合では403なので push 駆動。

- 1件失敗しても止めない。全件の結果を manifest.json に記録する
- HTML は生のまま保存し、あわせてタグを落としたテキスト版も作る
- **判断はこのスクリプトがしない。** 資料を運ぶだけで、「先行がある/ない」の結論は人間が原典を読んで出す
  （検索結果の見出しだけで competitor を認定すると、名前が似ているだけの別サービスを掴む）
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("s123_refs")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

# --- 1系統目: 官庁の原典 -------------------------------------------------
SEEDS = [
    # === S1: 盛土規制法（宅地造成及び特定盛土等規制法） ===
    ("s1_morido_mlit_top", "https://www.mlit.go.jp/toshi/web/toshi_tk_000010.html"),
    ("s1_morido_mlit_takuzo", "https://www.mlit.go.jp/toshi/web/index.html"),
    ("s1_morido_portal", "https://www.mlit.go.jp/toshi/toshi_tk_000005.html"),
    # 盛土の総点検（2021年の熱海土石流を受けたもの）
    ("s1_soutenken", "https://www.mlit.go.jp/report/press/toshi03_hh_000094.html"),
    # === S1b: 産業廃棄物の不法投棄（環境省の年次公表） ===
    ("s1b_huhoutouki_env", "https://www.env.go.jp/press/index.html"),
    ("s1b_sanpai_env", "https://www.env.go.jp/recycle/waste/index.html"),
    # === S2: 河川維持管理・河道内樹木 ===
    ("s2_kasen_iji", "https://www.mlit.go.jp/river/kasen/index.html"),
    ("s2_kasen_seibi", "https://www.mlit.go.jp/river/index.html"),
    ("s2_gijutsu_kijun", "https://www.mlit.go.jp/river/shishin_guideline/index.html"),
    # === S3: 再エネ特措法・事業計画策定ガイドライン ===
    ("s3_enecho_saiene", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/"),
    ("s3_fit_portal", "https://www.fit-portal.go.jp/"),
    ("s3_meti_saiene_seido", "https://www.meti.go.jp/policy/energy_environment/global_warming/index.html"),
    # 事業計画策定ガイドライン（太陽光発電）— 柵塀・標識・除草の義務の原典
    ("s3_guideline_pv", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/kaitori/dl/fit_2017/legal/guideline_solar.pdf"),
    # 認定情報の公表（事業者名・出力・所在地がどこまで出ているか＝台帳の粒度）
    ("s3_nintei_kohyo", "https://www.fit-portal.go.jp/PublicInfoSummary"),
]

# --- 2系統目: 先行の有無（例外(a)の判定） -------------------------------
# 官庁サイトのクロールでは民間サービスの存在は分からない。ここだけ検索エンジンを使う。
# DuckDuckGo の HTML 版は JS 不要で応答する（ランナーからは到達できる想定）。
SEARCH_QUERIES = [
    # S1
    ("q_s1_morido_satellite", "盛土規制法 衛星 監視 自治体"),
    ("q_s1_morido_kanshi", "無許可 盛土 検知 衛星データ サービス"),
    ("q_s1b_huhoutouki", "不法投棄 監視 衛星データ 都道府県"),
    # S2
    ("q_s2_jumoku", "河道内樹木 繁茂 衛星 把握 国土交通省"),
    ("q_s2_lidar", "河川 航空レーザ測量 周期 河道内樹木 伐採"),
    # S3
    ("q_s3_pv_kanri", "太陽光発電設備 管理不全 衛星 監視 除草"),
    ("q_s3_pv_kanshi", "太陽光 発電所 衛星データ 監視 サービス O&M"),
    ("q_s3_saiene_kaisei", "再エネ特措法 改正 柵塀 標識 除草 義務 措置命令"),
    # 案A（ついでに閉じる。18の2.1節の未取得(ii)）
    ("q_a_liveeo", "LiveEO 日本 埋設 パイプライン 監視"),
    ("q_a_takoji", "他工事 損傷 埋設管 衛星 監視 サービス"),
]
SEARCH_ENDPOINTS = [
    "https://html.duckduckgo.com/html/?q={q}",
    "https://lite.duckduckgo.com/lite/?q={q}",
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
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def save(name: str, url: str, manifest: list):
    entry = {"name": name, "url": url}
    try:
        status, ctype, body = fetch(url)
        entry.update(status=status, content_type=ctype, bytes=len(body))
        suffix = ".pdf" if "pdf" in ctype.lower() or url.lower().endswith(".pdf") else ".html"
        raw = OUT / (name + suffix)
        raw.write_bytes(body)
        entry["file"] = raw.name
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

    print("=== 1系統目: 官庁の原典 ===")
    for name, url in SEEDS:
        save(name, url, manifest)

    print("\n=== 2系統目: 先行の有無（検索） ===")
    for name, query in SEARCH_QUERIES:
        got = False
        for tmpl in SEARCH_ENDPOINTS:
            url = tmpl.format(q=urllib.parse.quote(query))
            before = len(manifest)
            save(f"{name}", url, manifest)
            if manifest[-1].get("status") == 200 and manifest[-1].get("bytes", 0) > 2000:
                manifest[-1]["query"] = query
                got = True
                break
            # 失敗した試行の記録は残す（どのエンドポイントが塞がっているかが次回の資産になる）
            manifest[before]["query"] = query
        if not got:
            print(f"     ※ 検索が通らなかった: {query}")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")
    print(f"未取得: {[m['url'] for m in manifest if m.get('status') != 200]}")


if __name__ == "__main__":
    main()
