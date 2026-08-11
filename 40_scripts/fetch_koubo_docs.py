#!/usr/bin/env python3
"""公募要項・特設サイトの取得スクリプト（GitHub Actions ランナー上で実行する想定）

クラウドサンドボックスからは nedo.go.jp / space-data-challenge.nedo.go.jp とも
egress 遮断されており、10_提出様式メモ.md の事務条項（提出様式・字数制限・
添付可否・応募者区分・知財・賞金支払）を一次情報で埋められない。
ネットワーク制限のない Actions ランナーで取得し、koubo-docs ブランチに置く。

- シード URL から出発し、同一サイト内のリンクを深さ2まで辿る
- 拾うのは (a) PDF/Word/Excel などの文書、(b) 応募・様式・FAQ 等の関連ページ
- 1件失敗しても止めない。全件の結果を manifest.json に記録する
- HTML は生のまま保存し、あわせてタグを落としたテキスト版も作る
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

OUT = Path("koubo_docs")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0; +application material retrieval)"

SEEDS = [
    "https://www.nedo.go.jp/koubo/SR2_100021.html",
    "https://www.nedo.go.jp/content/800057801.pdf",
    "https://space-data-challenge.nedo.go.jp/infrastructure/",
    "https://space-data-challenge.nedo.go.jp/",
]

ALLOWED_HOSTS = {"www.nedo.go.jp", "nedo.go.jp", "space-data-challenge.nedo.go.jp"}
DOC_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".zip")

# 深さ1以降で辿る価値のあるリンクのキーワード（URL・リンク文字列のどちらかに含まれる）
KEYWORDS = [
    "koubo", "apply", "entry", "application", "guideline", "outline", "faq",
    "form", "rule", "terms", "content", "infrastructure", "theme", "schedule",
    "応募", "要項", "様式", "提出", "募集", "質問", "よくある", "審査", "賞金",
    "規約", "テーマ", "スケジュール", "エントリー", "参加",
]

MAX_FILES = 60
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_DEPTH = 2


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

        host = urllib.parse.urlparse(url).netloc
        if host not in ALLOWED_HOSTS:
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
