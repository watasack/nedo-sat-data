#!/usr/bin/env python3
"""過去回（Green Earth／農林水産業）の受賞結果・審査委員・講評の取得スクリプト。

サンドボックスからは nedo.go.jp / space-data-challenge.nedo.go.jp / sorabatake.jp が
egress 遮断されているため、Actions ランナー上で取得して past_awards ブランチに置く。
fetch_koubo_docs.py と同じ方式（trigger-fetch-awards ブランチへの push で起動）。
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("past_awards")
UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"

SEEDS = [
    # Green Earth 回（第1弾・2024-2025）
    "https://space-data-challenge.nedo.go.jp/green_earth/index.html",
    "https://space-data-challenge.nedo.go.jp/green_earth/pdf/Final_Judging_Results.pdf",
    "https://space-data-challenge.nedo.go.jp/green_earth/pdf/program.pdf",
    "https://www.nedo.go.jp/ugoki/ZZ_101365.html",
    "https://www.nedo.go.jp/koubo/SR3_100014.html",
    "https://www.nedo.go.jp/content/800020197.pdf",
    "https://www.nedo.go.jp/activities/ZZJP2_100419.html",
    "https://www.nedo.go.jp/activities/ZZJP_100268.html",
    # 農林水産業 回（第2弾・2025-2026）
    "https://www.nedo.go.jp/koubo/SR2_100018.html",
    "https://www.nedo.go.jp/news/press/AA5_101851.html",
    "https://webmagazine.nedo.go.jp/pickupnews/prize07.html",
    "https://space-data-challenge.nedo.go.jp/aff/",
    "https://space-data-challenge.nedo.go.jp/aff/index.html",
    "https://www.nedo.go.jp/koubo/SR3_100018.html",
    "https://sorabatake.jp/43566/",
    # 今回（都市インフラ）
    "https://space-data-challenge.nedo.go.jp/infrastructure/",
    "https://space-data-challenge.nedo.go.jp/",
    # 農水回の最終選考結果は画像でしか公開されていない
    "https://space-data-challenge.nedo.go.jp/aff/img/t1_01.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t1_02.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t1_03.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t1_04.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t2_01.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t2_02.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t2_03.png",
    "https://space-data-challenge.nedo.go.jp/aff/img/t2_04.png",
    # 解説記事
    "https://sorabatake.jp/39615/",
    "https://sorabatake.jp/40588/",
    "https://ssil.tech/satellite_data_award_2024.html",
    "https://prtimes.jp/main/html/rd/p/000000036.000118467.html",
    "https://news.livedoor.com/pr_topics/detail/31708687/",
]

CRAWL_HOSTS = {
    "www.nedo.go.jp", "nedo.go.jp",
    "space-data-challenge.nedo.go.jp",
    "webmagazine.nedo.go.jp",
    "sorabatake.jp",
}
DOC_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".png", ".jpg")

KEYWORDS = [
    "green_earth", "agriculture", "infrastructure", "result", "judging",
    "award", "winner", "prize", "koubo", "press", "news", "ugoki", "aff",
    "受賞", "結果", "選考", "審査", "講評", "ファイナリスト", "一覧",
    "最終", "賞", "通過", "コメント", "審査委員",
]

MAX_FILES = 120
MAX_DEPTH = 2


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
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
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        html = html.replace(a, b)
    lines = [l.strip() for l in html.split("\n")]
    return "\n".join(l for l in lines if l)


def safe_name(url: str) -> str:
    p = urllib.parse.urlparse(url)
    name = (p.netloc + p.path).replace("/", "_").strip("_")
    if not name.endswith(DOC_EXT) and not name.endswith(".html"):
        name += ".html"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:150]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    seen = set()
    queue = [(u, 0) for u in SEEDS]
    count = 0

    while queue and count < MAX_FILES:
        url, depth = queue.pop(0)
        url = url.split("#")[0]
        if url in seen:
            continue
        seen.add(url)
        entry = {"url": url, "depth": depth}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read()
                entry["status"] = r.status
                ctype = r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            entry["status"] = e.code
            manifest.append(entry)
            continue
        except Exception as e:
            entry["status"] = "ERR"
            entry["error"] = str(e)[:200]
            manifest.append(entry)
            continue

        fn = safe_name(url)
        (OUT / fn).write_bytes(body)
        entry["file"] = fn
        entry["bytes"] = len(body)
        count += 1

        if "html" in ctype or fn.endswith(".html"):
            try:
                html = body.decode("utf-8", errors="replace")
            except Exception:
                html = ""
            (OUT / (fn + ".txt")).write_text(strip_tags(html), encoding="utf-8")
            if depth < MAX_DEPTH:
                p = LinkParser()
                try:
                    p.feed(html)
                except Exception:
                    pass
                for href, text in p.links:
                    nxt = urllib.parse.urljoin(url, href).split("#")[0]
                    h = urllib.parse.urlparse(nxt).netloc
                    if h not in CRAWL_HOSTS or nxt in seen:
                        continue
                    blob = (nxt + " " + text).lower()
                    if nxt.lower().endswith(DOC_EXT) or any(k.lower() in blob for k in KEYWORDS):
                        queue.append((nxt, depth + 1))
        manifest.append(entry)
        time.sleep(0.4)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"fetched {ok}/{len(manifest)} ok, {count} files")


if __name__ == "__main__":
    main()
