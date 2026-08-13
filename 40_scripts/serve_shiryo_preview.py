#!/usr/bin/env python3
"""60_shiryo/ の説明資料をローカルの実ブラウザで見るための配信サーバ。

    python3 40_scripts/serve_shiryo_preview.py [port]
    → http://localhost:8901/ に一覧、http://localhost:8901/<ファイル名> で資料

`.claude/launch.json` の `shiryo-preview` がこれを呼ぶので、通常は
`preview_start` で開く（Claude Code の Browser pane）。

なぜ `python3 -m http.server` を直に使わないか: 資料のHTMLは `<meta charset>` を
持っていない（Artifact 側のラッパが入れる前提で、資料は本文だけを書く約束になっている）。
素の http.server は `Content-Type: text/html` に charset を付けないので、
ブラウザが Shift_JIS 等と推定して全文が文字化けする。ここで charset を明示して返す。

測るときの注意（実際に踏んだもの）:
  - Browser pane が背面だと `innerWidth` が 0 になり、レイアウトの測定値が全部壊れる。
    先に screenshot を撮って前面に出してから測る。
  - `scrollTo()` の直後は scroll イベントがまだ発火していない。
    `window.dispatchEvent(new Event("scroll"))` を自分で撃ってから読む。
"""
import functools
import http.server
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "60_shiryo")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8",
                      ".md": "text/plain; charset=utf-8"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "200" not in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8901
    print(f"serving {ROOT} at http://localhost:{port}/", flush=True)
    http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(Handler, directory=ROOT)).serve_forever()
