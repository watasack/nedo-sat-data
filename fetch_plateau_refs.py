#!/usr/bin/env python3
"""応募例6（3D都市モデル×衛星）探索用 一次資料取得スクリプト。

サンドボックスからは bousai.go.jp / mlit.go.jp / jstage 等が egress 遮断されているため、
GitHub Actions ランナー上で取得し、plateau-refs ブランチにテキスト化して置く。
（fetch_koubo_docs.py と同じ Actions 迂回方式。workflow_dispatch API は 403 なので push 駆動）

URL は plateau_urls.txt（1行1URL、# はコメント）から読む。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plateau_refs")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def slug(url):
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])[-90:]
    return hashlib.md5(url.encode()).hexdigest()[:8] + "_" + tail


def html_to_text(b):
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        for enc in ("cp932", "euc-jp", "shift_jis"):
            try:
                s = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            s = b.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    s = re.sub(r"[ \t　]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def main():
    os.makedirs(OUT, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "plateau_urls.txt"), encoding="utf-8") as f:
        urls = [l.strip() for l in f
                if l.strip() and not l.strip().startswith("#")]

    manifest = []
    for url in urls:
        name = slug(url)
        rec = {"url": url, "name": name}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
                rec["status"] = r.status
                ctype = r.headers.get("Content-Type", "")
            rec["bytes"] = len(body)
            is_pdf = body[:4] == b"%PDF" or url.lower().endswith(".pdf")
            if is_pdf:
                raw = os.path.join(OUT, name + ".pdf")
                with open(raw, "wb") as fh:
                    fh.write(body)
                txt = os.path.join(OUT, name + ".txt")
                subprocess.run(["pdftotext", "-layout", raw, txt], check=False)
                os.remove(raw)
                rec["kind"] = "pdf"
                rec["text"] = os.path.exists(txt) and os.path.getsize(txt) or 0
            else:
                txt = os.path.join(OUT, name + ".txt")
                with open(txt, "w", encoding="utf-8") as fh:
                    fh.write(html_to_text(body))
                rec["kind"] = "html"
                rec["text"] = os.path.getsize(txt)
            print("OK  ", rec.get("status"), rec["kind"], rec["text"], url)
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {e}"
            print("FAIL", url, rec["error"], file=sys.stderr)
        manifest.append(rec)

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    ok = sum(1 for m in manifest if "error" not in m)
    print(f"\n{ok}/{len(manifest)} fetched")


if __name__ == "__main__":
    main()
