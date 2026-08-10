#!/usr/bin/env python3
"""施設数と認定制度の経済価値の一次出典を取る（GitHub Actions ランナー上で実行する想定）

未解決C（`15_事業計画の裏付け.md` 3.3節・10節）を閉じるための取得。
サンドボックスからは meti.go.jp / env.go.jp / jdhc.or.jp / paj.gr.jp とも egress 遮断されており、
08 付録E の施設数（150〜250サイト等）に一次出典が無いまま⑤に「セグメント別積算で年20〜40億円」と
書いている状態を直せない（投資家レビュー V1-5・V1-6）。

**取りたいのは4つの施設数と、認定事業者制度の経済価値である。**

| 用途 | 欲しい数 | 当たり先 |
|---|---|---|
| 火力発電・大型清掃工場セグメント | 火力発電所の数 | 資源エネルギー庁 電力調査統計、電気事業連合会 |
| 同 | 清掃工場（ごみ焼却施設）の数・発電設備の有無 | 環境省 一般廃棄物処理実態調査 |
| 地域熱供給・自治体施設セグメント | 熱供給事業者数・供給地区数 | 日本熱供給事業協会 事業者一覧 |
| 横展開先セグメント | 製油所の数 | 石油連盟 統計・会員一覧 |
| 単価の裏取り（V1-6） | 認定事業者制度の連続運転期間の延長年数と、その経済価値の公表事例 | 高圧ガス保安協会、経産省 産業保安・スマート保安 |

`fetch_koubo_docs.py` と同じ方式（`trigger-fetch-facility` ブランチへの push で起動 →
`facility-refs` ブランチにコミット）。workflow_dispatch APIはこの環境のGitHub統合では403なので push 駆動。

- 1件失敗しても止めない。全件の結果を manifest.json に記録する
- HTML は生のまま保存し、あわせてタグを落としたテキスト版も作る
- **数を読み取るのは人間（またはこの後のセッション）である。** このスクリプトは資料を運ぶだけで、
  数字の抽出はしない——原典の表の見出しを確認せずに数を拾うと、対象範囲の違い（事業用/自家用、
  発電設備の有無、休止中の扱い）を取り違える
"""

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("facility_refs")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

# 第3巡（2026年8月10日）: 寄り道をやめ、統計表の本体（xlsx）を直接取る。MAX_DEPTH=0。
#   第2巡は e-Stat のナビゲーションを延々とクロールして80件の予算を食い潰した（51/80件）。
#   ただし環境省の年度ページが取れ、**焼却施設の集計は data/seibi/facility/01.xlsx にある**ことが
#   判明した（r5/index.html のリンク文字列「焼却施設 (xls 535KB)」の実体）。
#   電力調査統計の統計表も ep002/xls/2026/*.xlsx と分かった。
#   **製油所（石油連盟）と認定事業者制度（高圧ガス保安協会）は静的HTMLにリンクが無く、**
#   **経産省スマート保安は403。この2つは未取得のまま残す**（主対象2セグメントではないので優先度は低い）。
#
# 第1巡（2026年8月10日）の結果: 73/80件を取得し、**熱供給だけが静的HTMLで数え切れた**
#   （日本熱供給事業協会 事業者一覧 = 72事業者・133供給地域）。
# 残る3つは第1巡のシードでは数に届かなかったので、第2巡でシードを絞り込んである。
#   - 火力発電所: 電気事業連合会の「主な発電所検索」はJS駆動で静的HTMLに件数が出ない
#     → 資源エネルギー庁 電力調査統計の統計表本体（Excel）と e-Stat を狙う
#   - ごみ焼却施設: 環境省の一覧ページは平成24・25年度しか辿れなかった
#     → 最新年度ページを年度直打ちで並べ、あわせて e-Stat の統計表を狙う
#   - 製油所: 石油連盟の統計トップからは会員会社ページに届かなかった → 直接指定
SEEDS = [
    # --- 清掃工場（ごみ焼却施設）の数: 環境省 一般廃棄物処理実態調査の施設別集計（本体） ---
    #     r5/index.html のリンク文字列「焼却施設 (xls 535KB)」の実体。ここに施設が1行ずつ載る
    "https://www.env.go.jp/recycle/waste_tech/ippan/r5/data/seibi/facility/01.xlsx",
    "https://www.env.go.jp/recycle/waste_tech/ippan/r4/data/seibi/facility/01.xlsx",
    "https://www.env.go.jp/recycle/waste_tech/ippan/r5/data/shori/total/01.xlsx",
    # --- 火力発電所の数: 資源エネルギー庁 電力調査統計の統計表（本体） ---
    "https://www.enecho.meti.go.jp/statistics/electric_power/ep002/xls/2026/1-1-2026.xlsx",
    "https://www.enecho.meti.go.jp/statistics/electric_power/ep002/xls/2026/1-2-2026.xlsx",
    "https://www.enecho.meti.go.jp/statistics/electric_power/ep002/xls/2026/2-1-2026.xlsx",
    "https://www.enecho.meti.go.jp/statistics/electric_power/ep002/xls/2026/2-2-2026.xlsx",
    # --- 熱供給（第1巡で数え切れた。版を固定するため再取得する） ---
    "https://www.jdhc.or.jp/company_list/",
]

ALLOWED_HOSTS = {
    "www.enecho.meti.go.jp", "www.meti.go.jp", "meti.go.jp",
    "www.fepc.or.jp", "fepc.or.jp",
    "www.env.go.jp", "env.go.jp",
    "www.jdhc.or.jp", "jdhc.or.jp",
    "www.paj.gr.jp", "paj.gr.jp",
    "www.khk.or.jp", "khk.or.jp",
}
DOC_EXT = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv", ".zip")

# 深さ1以降で辿る価値のあるリンクのキーワード（URL・リンク文字列のどちらかに含まれる）
KEYWORDS = [
    "statistics", "statis", "data", "list", "member", "survey", "result",
    "certification", "hipregas", "smart", "safety", "excel", "csv",
    "統計", "調査", "実態", "一覧", "会員", "事業者", "施設", "発電所", "製油所",
    "焼却", "処理施設", "熱供給", "供給区域", "地区",
    "認定", "保安", "スマート保安", "連続運転", "開放検査", "検査周期",
    "便覧", "年報", "集計", "結果", "公表",
]

MAX_FILES = 20
MAX_TOTAL_BYTES = 40 * 1024 * 1024   # GitHubは1ファイル100MB超でブランチ全体を弾く
MAX_DEPTH = 0   # 第2巡でe-Statのナビゲーションをクロールして予算を食い潰したので、寄り道を止めた


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []          # (href, リンク文字列)
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._href = d.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", "\n", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return "\n".join(line.strip() for line in html.split("\n") if line.strip())


def safe_name(url: str) -> str:
    p = urllib.parse.urlparse(url)
    path = p.path or "/"
    name = f"{p.netloc}{path}"
    if name.endswith("/"):
        name += "index.html"
    name = re.sub(r"[^A-Za-z0-9._/-]", "_", name).replace("/", "__")
    return name[:150]


def fetch(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def interesting(href: str, text: str) -> bool:
    low = (href + " " + text).lower()
    if href.lower().endswith(DOC_EXT):
        return True
    return any(k.lower() in low for k in KEYWORDS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    seen = set()
    total = 0
    queue = [(u, 0) for u in SEEDS]

    while queue and len(manifest) < MAX_FILES and total < MAX_TOTAL_BYTES:
        url, depth = queue.pop(0)
        url, _ = urllib.parse.urldefrag(url)
        if url in seen:
            continue
        seen.add(url)

        if urllib.parse.urlparse(url).netloc not in ALLOWED_HOSTS:
            continue

        entry = {"url": url, "depth": depth}
        try:
            status, ctype, body = fetch(url)
            entry.update(status=status, content_type=ctype, bytes=len(body),
                         sha256=hashlib.sha256(body).hexdigest())
            name = safe_name(url)
            (OUT / name).write_bytes(body)
            entry["file"] = name
            total += len(body)

            is_html = "html" in ctype.lower() or name.endswith(".html")
            if is_html:
                try:
                    text = body.decode("utf-8")
                except UnicodeDecodeError:
                    text = body.decode("cp932", errors="replace")
                txt_name = name + ".txt"
                (OUT / txt_name).write_text(strip_tags(text), encoding="utf-8")
                entry["text_file"] = txt_name

                if depth < MAX_DEPTH:
                    parser = LinkParser()
                    parser.feed(text)
                    for href, label in parser.links:
                        nxt = urllib.parse.urljoin(url, href)
                        nxt, _ = urllib.parse.urldefrag(nxt)
                        if nxt in seen:
                            continue
                        if urllib.parse.urlparse(nxt).netloc not in ALLOWED_HOSTS:
                            continue
                        if interesting(href, label):
                            queue.append((nxt, depth + 1))
            print(f"OK   {status} {len(body):>9,}  {url}")
        except urllib.error.HTTPError as e:
            entry.update(status=e.code, error=f"HTTPError {e.code}")
            print(f"FAIL {e.code} {url}")
        except Exception as e:  # ネットワーク・TLS・タイムアウト等
            entry.update(status=None, error=f"{type(e).__name__}: {e}")
            print(f"FAIL --- {url}  {type(e).__name__}: {e}")

        manifest.append(entry)
        time.sleep(1.0)  # 相手方サーバへの負荷を避ける

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件、合計 {total:,} bytes")
    print(f"未取得: {[m['url'] for m in manifest if m.get('status') != 200]}")


if __name__ == "__main__":
    main()
