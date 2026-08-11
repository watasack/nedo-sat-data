#!/usr/bin/env python3
"""災害廃棄物の発生量推計に関する一次情報の取得（GitHub Actions ランナー上で実行）

テーマ2候補「災害廃棄物の発生量を衛星で面的に推定できるか」の調査用。
サンドボックスからは env.go.jp / soumu.go.jp / pref.ishikawa.lg.jp / jstage 等が
すべて egress 遮断されているため、Actions ランナーで取得して waste-docs ブランチに置く。

固定URLリストのみ取得する（クロールしない）。PDFは pdftotext -layout でテキスト化する。
1件失敗しても止めず、manifest.json に全件の結果を記録する。
"""

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("waste_docs")
UA = "Mozilla/5.0 (compatible; nedo-applicant-research/1.0)"

URLS = [
    # --- 環境省: 発生量推計の手法と精度 ---
    # 衛星画像を活用した災害廃棄物の発生量の推計手法の検証（最重要）
    "https://www.env.go.jp/content/900536512.pdf",
    "https://www.env.go.jp/content/900536374.pdf",
    "https://www.env.go.jp/recycle/waste/disaster/earthquake/committee2/29-02/01-3_h29_2giji.pdf",
    "https://www.env.go.jp/recycle/waste/disaster/earthquake/committee/05/mat02.pdf",
    "http://kouikishori.env.go.jp/guidance/download/pdf/046_gi14-2.pdf",
    "http://kouikishori.env.go.jp/action2/investigative_commission/r4_fiscal_year/estimated-amount-of-disaster-waste/",
    "http://kouikishori.env.go.jp/action2/investigative_commission/h25_fiscal_year/estimate/",
    "https://www.env.go.jp/recycle/waste/disaster/earthquake/committee2.html",
    "https://www.env.go.jp/recycle/waste/disaster/earthquake/committee/committee16b.html",
    "https://www.env.go.jp/press/press_04255.html",
    # --- 総務省 行政評価・監視（災害廃棄物対策） ---
    "https://www.soumu.go.jp/main_content/000795388.pdf",
    "https://www.soumu.go.jp/main_content/000795390.pdf",
    # --- 能登半島地震 ---
    "https://kinki.env.go.jp/content/000364501.pdf",
    "https://www.env.go.jp/content/000214810.pdf",
    "https://www.env.go.jp/content/000215193.pdf",
    "https://www.pref.ishikawa.lg.jp/haitai/documents/r060826kasokukaplan.pdf",
    "https://www.pref.ishikawa.lg.jp/haitai/documents/jikkoukeikaku.pdf",
    "https://www.pref.ishikawa.lg.jp/haitai/r6kihonhoushin.html",
    "https://all62.jp/wp-content/uploads/2025/03/file_2024_06_01_01.pdf",
    # --- 熊本地震・東日本大震災 ---
    "https://kyushu.env.go.jp/content/000127178.pdf",
    "https://policies.env.go.jp/recycle/disaster_waste/document_video/pdf/wg_report_01.pdf",
    "https://policies.env.go.jp/recycle/disaster_waste/action/d_waste_net/pdf/symposium_250906_lecture_02.pdf",
    # --- 学術（和文） ---
    "https://www.jstage.jst.go.jp/article/jjsmcwm/29/0/29_104/_pdf",
    "https://www.jstage.jst.go.jp/article/jscejer/75/6/75_II_261/_pdf",
    "https://www.nies.go.jp/shinsai/enpdf/genntanni_no1_110628.pdf",
]


def fetch(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", "\n", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")):
        html = html.replace(a, b)
    return "\n".join(l.strip() for l in html.split("\n") if l.strip())


def safe_name(url: str) -> str:
    p = urllib.parse.urlparse(url)
    name = f"{p.netloc}{p.path or '/'}"
    if name.endswith("/"):
        name += "index.html"
    return re.sub(r"[^A-Za-z0-9._/-]", "_", name).replace("/", "__")[:150]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for url in URLS:
        entry = {"url": url}
        try:
            status, ctype, body = fetch(url)
            name = safe_name(url)
            (OUT / name).write_bytes(body)
            entry.update(status=status, content_type=ctype, bytes=len(body),
                         sha256=hashlib.sha256(body).hexdigest(), file=name)

            if body[:4] == b"%PDF" or name.lower().endswith(".pdf"):
                txt = OUT / (name + ".txt")
                r = subprocess.run(["pdftotext", "-layout", str(OUT / name), str(txt)],
                                   capture_output=True)
                if r.returncode == 0 and txt.exists():
                    entry["text_file"] = txt.name
                    entry["text_chars"] = len(txt.read_text(errors="replace"))
                else:
                    entry["pdftotext_error"] = r.stderr.decode(errors="replace")[:300]
            elif "html" in ctype.lower() or name.endswith(".html"):
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
        time.sleep(1.0)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")
    print("未取得:", [m["url"] for m in manifest if m.get("status") != 200])


if __name__ == "__main__":
    main()
