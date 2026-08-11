#!/usr/bin/env python3
"""S1/S3 の例外(a)と制度の原典を閉じる第2巡（GitHub Actions ランナー上で実行する想定）

第1巡（`fetch_s123_refs.py`）の結果と、そこから決めた方針:

- 官庁の原典は 11/34 件取れた（S3のガイドライン原文で「雑草は努力義務」が判明し、S3を減点した）
- **例外(a)＝先行の有無だけが閉じなかった。** DuckDuckGo の HTML版・lite版は
  10クエリ×2エンドポイントの20件すべてが **status 202 のbot判定ページ**を返した
- **したがって第2巡は検索エンジンに寄りかからない。** 方針を3つに分ける:
  1. **法令は e-Gov 法令検索の条文を直接引く**（S1の許可対象規模。検索不要）
  2. **先行は「誰が買っているか」から引く**——NETIS（新技術情報提供システム）、
     官公需情報ポータル、各省の入札・公募ページ。**`origin/bid-refs` でテーマ2の契約金額を
     取ったときに実証済みの経路である**
  3. **研究の先行は CiNii / KAKEN / J-STAGE の検索URL**（いずれもサーバ側レンダリングで、
     bot判定を持たない）。あわせて **Mojeek**（独自クローラでチャレンジを出さない）を1本だけ試す

新規候補 N38（再エネ設備の災害リスク評価＝保険・レンダー向け）の下調べも同じ便で取る。

`fetch_s123_refs.py` と同じ方式（`trigger-fetch-s123b` ブランチへの push で起動 →
`s123-refs2` ブランチにコミット）。

**判断はこのスクリプトがしない。** 資料を運ぶだけで、「先行がある/ない」の結論は原典を読んで出す。
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("s123_refs2")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

# --- 1. 法令の条文（検索不要。e-Gov 法令検索） -----------------------------
SEEDS = [
    # S1: 宅地造成及び特定盛土等規制法（盛土規制法）。許可対象の規模は政令にある
    ("s1_law_egov", "https://laws.e-gov.go.jp/law/336AC0000000191"),
    ("s1_law_search", "https://laws.e-gov.go.jp/search/elawsSearch/elaws_search/lsg0500/?lawName=%E7%9B%9B%E5%9C%9F"),
    # 盛土規制法ポータル（第1巡で親ページは取れたので、その先を直接）
    ("s1_portal_mlit", "https://www.mlit.go.jp/toshi/web/toshi_tk_000059.html"),
    ("s1_morido_kisei", "https://www.mlit.go.jp/toshi/web/morido.html"),
    # 建設発生土の搬出先の届出（資源有効利用促進法の省令改正）。S1と同根で、S1を強化する材料
    ("s1_hasseido", "https://www.mlit.go.jp/sogoseisaku/region/recycle/index.htm"),

    # S1b: 産業廃棄物の不法投棄の年次統計（母数）
    ("s1b_touki_stats", "https://www.env.go.jp/recycle/ill_dum.html"),

    # S3: FIT 認定情報の設備別公表（台帳の粒度＝型⑥の境界を決める）
    ("s3_nintei_list", "https://www.fit-portal.go.jp/PublicInfoSummary"),
    ("s3_nintei_dl", "https://www.fit-portal.go.jp/PublicInfoDownload"),
    # 太陽光発電設備の適切な管理・小規模事業用の規律（資源エネルギー庁）
    ("s3_enecho_taiyoko", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/solar/index.html"),
    ("s3_enecho_kaitori", "https://www.enecho.meti.go.jp/category/saving_and_new/saiene/kaitori/index.html"),

    # N38: 再エネ設備の自然災害リスク（保険・レンダー向け）の下調べ
    ("n38_jpea_saigai", "https://www.jpea.gr.jp/"),
    ("n38_meti_jiko", "https://www.meti.go.jp/policy/safety_security/industrial_safety/index.html"),

    # --- 2. 「誰が買っているか」＝調達・技術登録の台帳 ---
    ("bid_kkj_top", "https://www.kkj.go.jp/"),
    ("netis_top", "https://www.netis.mlit.go.jp/netis/"),
    ("netis_search", "https://www.netis.mlit.go.jp/netis/pubsearch/details?REG_NO="),
    ("chotatsu_portal", "https://www.p-portal.go.jp/pps-web-biz/UAA01/OAA0101"),
]

# --- 3. 研究の先行（サーバ側レンダリングでbot判定を持たない検索） -----------
CINII = "https://cir.nii.ac.jp/all?q={q}"
KAKEN = "https://kaken.nii.ac.jp/ja/search/?qb={q}"
JSTAGE = "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey={q}"
MOJEEK = "https://www.mojeek.com/search?q={q}"

QUERIES = [
    ("s1_morido_sat", "盛土 衛星 監視"),
    ("s1_touki_sat", "不法投棄 衛星 監視"),
    ("s3_pv_sat", "太陽光発電所 衛星 監視"),
    ("s3_pv_ndvi", "太陽光発電 雑草 植生 リモートセンシング"),
    ("n38_pv_risk", "太陽光発電 自然災害 リスク評価 保険"),
    ("a_takoji", "埋設管 他工事 損傷 衛星"),
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


def save(name: str, url: str, manifest: list, note: str = ""):
    entry = {"name": name, "url": url}
    if note:
        entry["note"] = note
    try:
        status, ctype, body = fetch(url)
        entry.update(status=status, content_type=ctype, bytes=len(body))
        suffix = ".pdf" if "pdf" in ctype.lower() or url.lower().endswith(".pdf") else ".html"
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

    print("=== 1. 法令・官庁の原典と、調達の台帳 ===")
    for name, url in SEEDS:
        save(name, url, manifest)

    print("\n=== 2. 研究・商用の先行（サーバ側レンダリングの検索） ===")
    for key, q in QUERIES:
        enc = urllib.parse.quote(q)
        for tag, tmpl in (("cinii", CINII), ("kaken", KAKEN), ("jstage", JSTAGE), ("mojeek", MOJEEK)):
            save(f"q_{key}_{tag}", tmpl.format(q=enc), manifest, note=q)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")
    print(f"未取得: {[m['url'] for m in manifest if m.get('status') != 200]}")


if __name__ == "__main__":
    main()
