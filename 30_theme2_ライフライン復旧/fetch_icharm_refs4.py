#!/usr/bin/env python3
"""ICHARM調査 第3バッチ。第2バッチで判明した直URLの詰め。

(1) ICHARM側: WEB-DHM-S のプロジェクト紹介（分解能・対象流域）、玉川勝徳のスタッフページ、
    研究紹介「気候変動影響評価のための雪水文モデル(WEB-DHM-S)」、東大GEDCでの現況。
(2) 犀川ダム流入予測論文（Water 2024）の本文（MDPIが403なのでミラー経路）。
(3) 第2バッチの検索で見つかった、本案により近い先行：
    新潟大NHDR「御嶽山積雪期火山防災情報プラットフォーム」（実運用中）と
    「融雪型火山泥流リアルタイムハザードマップのための山地積雪水量推定方法の研究(4)」。
(4) 過去回（農林水産業回）の受賞結果（重複運用の実例確認）。

出力先は icharm_refs4/。トリガ: trigger-fetch-icharm3 ブランチへの push
"""

import gzip
import io
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

OUT = Path("icharm_refs4")
Q = urllib.parse.quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

TARGETS = [
    ("gedc_top", "https://www.coms.u-tokyo.ac.jp/"),
    ("gedc_member", "https://www.coms.u-tokyo.ac.jp/about_coms/member/"),
    ("gedc_news", "https://www.coms.u-tokyo.ac.jp/news/"),
    ("gedc_search_tamakawa", "https://www.coms.u-tokyo.ac.jp/?s=" + Q("玉川")),
    ("icharm_awards_j", "https://www.pwri.go.jp/icharm/about/award/index_j.html"),
    ("icharm_awards", "https://www.pwri.go.jp/icharm/about/award/index.html"),
    ("icharm_nl_index", "https://www.pwri.go.jp/icharm/publication/newsletter/index_j.html"),
    ("nedo_aff_result_img1", "https://space-data-challenge.nedo.go.jp/img/judge_t1.png"),
    ("nedo_aff_result_img2", "https://space-data-challenge.nedo.go.jp/img/judge_t2.png"),
    ("bing_aff_winners", "https://www.bing.com/search?q=" + Q("NEDO Challenge 農林水産業 衛星データ 受賞 2位 3位 2026")),
    ("bing_tamakawa_now", "https://www.bing.com/search?q=" + Q('"玉川勝徳" 2026 所属')),
    ("ddg_nhdr_arakawa", "https://html.duckduckgo.com/html/?q=" + Q("荒川逸人 山地積雪水量 機械学習 融雪型火山泥流 蔵王")),
    ("nhdr_kyodo_index", "https://www.nhdr.niigata-u.ac.jp/kyodo/"),
]


def _read(r):
    d = r.read()
    enc = (r.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            d = gzip.decompress(d)
        elif enc == "deflate":
            d = zlib.decompress(d, -zlib.MAX_WBITS)
    except Exception:
        try:
            d = gzip.GzipFile(fileobj=io.BytesIO(d)).read()
        except Exception:
            pass
    return d


def fetch(name, url, cap=60_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=120) as r:
            data = _read(r)
            rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
            rec["final_url"] = r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec
    if len(data) > cap:
        rec["truncated_from"] = len(data)
        data = data[:cap]
    if data[:5] == b"%PDF":
        ext = ".pdf"
    elif "json" in ctype or "api." in url or "webservices/rest" in url:
        ext = ".json"
    else:
        ext = ".html"
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=(ext == ".pdf"))
    if ext == ".pdf":
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    return rec


def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t　]+", " ", s)
    return "\n".join(l.strip() for l in s.split("\n") if l.strip())


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        out.append("=" * 70)
        out.append(f"FILE: {t.name}")
        out.append(t.read_text(errors="replace")[:120_000])
    OUT.joinpath("_digest_pdf.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        out2.append("=" * 70)
        out2.append(f"FILE: {h.name}")
        out2.append(strip_html(h.read_text("utf-8", "replace"))[:45_000])
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))

    out3 = []
    for j in sorted(OUT.glob("*.json")):
        out3.append("=" * 70)
        out3.append(f"FILE: {j.name}")
        out3.append(j.read_text("utf-8", "replace")[:50_000])
    OUT.joinpath("_digest_api.txt").write_text("\n".join(out3))


def main():
    OUT.mkdir(exist_ok=True)
    man = [fetch(n, u) for n, u in TARGETS]
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print(f"fetched {len(man)}, ok={sum(1 for r in man if r.get('status') == 200)}")


if __name__ == "__main__":
    main()
