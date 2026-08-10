#!/usr/bin/env python3
"""テーマ2 未解決B ── 那須岳R8の契約結果を取りに行く（Actions迂回）。

**なぜ今なのか（V-26）**: `13_事業計画の裏付け.md` 3.1節は那須岳R8を「公告予定 令和8年5月／
入札予定 第2四半期」と書いており、9節はBの期限を「2026年10月下旬」に置いていた。
**しかし今日は2026年8月10日で、公告も第2四半期の入札も既に進行中または終了している。**
第4バッチ（`fetch_bid_refs.py`）は発注見通しの時点で走っており、契約結果はまだ出ていなかった。

契約結果が公表されていれば3つが同時に動く:

  (i)  受注者名 → **未解決A(d)（共同提案の相手）が確定する**
  (ii) 契約金額 → **未解決B（火山砂防検討業務の単価の実額）が閉じる**
  (iii) 内訳が出れば「人工衛星を活用した積雪深推定の検討 1式」が業務全体に占める割合が見え、
       **設計共同体での分担割合（V-22。4.3節の粗利率が上限側である問題）まで届く**

狙うのは静的公開の契約情報だけ（PPI/GEPS は動的サイトで到達不可なのが第4バッチで確認済み）:

  1. 日光砂防事務所の入札・契約情報（那須岳の発注元）
  2. 関東地方整備局の「公共調達の適正化に基づく契約に係る情報の公表」月次一覧
  3. 電子調達システムの公開文書（第2バッチで雌阿寒岳の公告を取れた経路と同じ）
  4. 東北地方整備局（蔵王＝山形河川国道／鳥海＝新庄河川）の契約情報

出力先は bid2_refs/。トリガ: trigger-fetch-bid2 ブランチへの push
（`fetch_policy_refs2.py` と同じくファイル名にURLハッシュを付けて上書き事故を防ぐ）
"""
import gzip
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

OUT = Path("bid2_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {"User-Agent": UA,
     "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
     "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip, deflate", "Connection": "close"}
MAX_BYTES = 40 * 1024 * 1024


def Q(s):
    return urllib.parse.quote_plus(s)


SINGLE = [
    # 発注見通し原本（第3バッチで取得済み。契約結果と突き合わせる基準として再取得）
    ("b2_nikko_mitooshi_r8", "https://www.ktr.mlit.go.jp/ktr_content/content/000942554.pdf"),
]

INDEX = [
    # --- 那須岳の発注元 ---
    ("b2_nikko_nyuusatu", "https://www.ktr.mlit.go.jp/nikko/nikko_index014.html"),
    ("b2_nikko_top", "https://www.ktr.mlit.go.jp/nikko/index.html"),
    # --- 関東地整の契約情報（公共調達の適正化に基づく公表） ---
    ("b2_ktr_keiyaku", "https://www.ktr.mlit.go.jp/nyuusatu/index00000075.html"),
    ("b2_ktr_nyuusatu_top", "https://www.ktr.mlit.go.jp/nyuusatu/index.html"),
    # --- 東北地整（蔵王・鳥海の発注元） ---
    ("b2_thr_keiyaku", "https://www.thr.mlit.go.jp/nyuusatu/keiyakujouhou/index.html"),
    ("b2_yamagata", "https://www.thr.mlit.go.jp/yamagata/index.html"),
    ("b2_shinjyou", "https://www.thr.mlit.go.jp/shinjyou/index.html"),
]

QUERIES = [
    'Ｒ８那須岳火山噴火緊急減災対策検討業務 落札',
    '那須岳火山噴火緊急減災対策検討業務 契約 令和8年度',
    '日光砂防事務所 建設コンサルタント業務 契約結果 令和8年度',
    '関東地方整備局 契約に係る情報の公表 建設コンサルタント 令和8年度 砂防',
]
SEARCH = []
for i, q in enumerate(QUERIES):
    SEARCH.append((f"b2_ddg_{i}", "https://html.duckduckgo.com/html/?q=" + Q(q)))
    SEARCH.append((f"b2_bing_{i}", "https://www.bing.com/search?q=" + Q(q)))
    SEARCH.append((f"b2_mojeek_{i}", "https://www.mojeek.com/search?q=" + Q(q)))

LINK_KEY = re.compile(
    r"契約|落札|入札|結果|公表|一覧|適正化|業務|コンサル|砂防|火山|那須|蔵王|鳥海|"
    r"緊急減災|積雪|発注|見通し|令和[０-９0-9]|公告|随意")
DOC_EXT = (".pdf", ".csv", ".xls", ".xlsx")
GOV = re.compile(r"://[^/]*\.(go\.jp|lg\.jp|or\.jp)(/|$)")


def _read(r):
    d = r.read()
    enc = (r.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            d = gzip.decompress(d)
        elif enc == "deflate":
            d = zlib.decompress(d, -zlib.MAX_WBITS)
    except Exception:
        pass
    return d


def safe(s, url, fallback):
    s = re.sub(r"[^0-9A-Za-z぀-ヿ一-鿿]+", "_", (s or "").strip())[:50].strip("_") or fallback
    return f"{s}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def fetch(name, url):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90) as r:
            if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
                rec.update(status=r.status, skipped="too_large_declared")
                return rec
            body = _read(r)
            rec["status"] = r.status
            rec["final_url"] = r.geturl()
            ctype = (r.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec
    if len(body) > MAX_BYTES:
        rec["skipped"] = f"too_large_actual:{len(body)}"
        return rec

    is_pdf = body[:5] == b"%PDF"
    ext = ".pdf" if (is_pdf or "pdf" in ctype or url.lower().endswith(".pdf")) else (
        ".json" if "json" in ctype else ".html")
    p = OUT / (name + ext)
    p.write_bytes(body)
    rec["bytes"] = len(body)
    if ext == ".pdf":
        try:
            # 契約結果は表組みなので -layout は必須（列がつぶれると金額と業務名の対応が消える）
            subprocess.run(["pdftotext", "-layout", str(p), str(p.with_suffix(".txt"))],
                           check=True, capture_output=True, timeout=300)
        except Exception as e:
            rec["pdftotext"] = repr(e)
    elif ext == ".html":
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body.decode("utf-8", "replace"),
                   flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", "\n", t)
        p.with_suffix(".txt").write_text(re.sub(r"\n{3,}", "\n\n", t))
    return rec


def links_of(rec, base):
    p = OUT / (rec["name"] + ".html")
    if not p.exists():
        return []
    html = p.read_bytes().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        full = urllib.parse.urljoin(rec.get("final_url") or base, href)
        if "duckduckgo.com/l/" in full:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(full).query).get("uddg")
            if q:
                full = q[0]
        out.append((full, re.sub(r"\s+", " ", label).strip()))
    return out


def crawl(name, url, man, seen, depth2=10, per=8):
    r = fetch(name, url)
    man.append(r)
    kids = []
    for full, label in links_of(r, url):
        if full in seen:
            continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        if full.lower().endswith(DOC_EXT):
            man.append(fetch(f"{name}__{safe(label, full, 'd')}", full))
        else:
            kids.append((full, label))
    for full, label in kids[:depth2]:
        n2 = f"{name}__{safe(label, full, 'sub')}"
        r2 = fetch(n2, full)
        man.append(r2)
        c = 0
        for f3, l3 in links_of(r2, full):
            if f3 in seen or not f3.lower().endswith(DOC_EXT):
                continue
            if not (LINK_KEY.search(l3) or LINK_KEY.search(urllib.parse.unquote(f3))):
                continue
            seen.add(f3)
            man.append(fetch(f"{n2}__{safe(l3, f3, 'd')}", f3))
            c += 1
            if c >= per:
                break


def harvest(name, url, man, seen, per=8):
    r = fetch(name, url)
    man.append(r)
    c = 0
    for full, label in links_of(r, url):
        if full in seen:
            continue
        if not (GOV.search(full) or full.lower().endswith(".pdf")):
            continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        man.append(fetch(f"{name}__{safe(label, full, 'hit')}", full))
        c += 1
        if c >= per:
            break


NAME_KEY = re.compile(r"那須岳|火山噴火緊急減災|緊急減災対策検討|積雪深推定|火山砂防|"
                      r"蔵王|鳥海|砂防計画|ハザードマップ")
MONEY = re.compile(r"[0-9０-９,，]{4,}\s*(円|千円|百万円)")


def digest():
    money, named = [], []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_"):
            continue
        rows = t.read_text(errors="replace").split("\n")
        for i, ln in enumerate(rows):
            if not NAME_KEY.search(ln):
                continue
            ctx = [x.rstrip() for x in rows[max(0, i - 2):i + 3] if x.strip()]
            blob = " / ".join(ctx)
            (money if MONEY.search(blob) else named).append(f"[{t.name} L{i}] {blob}")
    OUT.joinpath("_digest_bid2.txt").write_text(
        "# 未解決B: 火山砂防検討業務の契約金額\n"
        "受注者名が取れれば未解決A(d)、金額が取れれば未解決B、"
        "内訳が取れれば設計共同体の分担割合（V-22）まで届く。\n\n"
        "### 業務名キーワード＋金額表記あり（最優先で読む）\n" + "\n".join(money[:400])
        + "\n\n### 業務名キーワードのみ（金額が近傍に無い）\n" + "\n".join(named[:400]))
    print("digest: money", len(money), "named", len(named))


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for n, u in SINGLE:
        man.append(fetch(n, u))
    seen = set()
    for n, u in INDEX:
        try:
            crawl(n, u, man, seen)
        except Exception as e:
            man.append({"name": n, "url": u, "error": "crawl:" + repr(e)})
    for n, u in SEARCH:
        try:
            harvest(n, u, man, seen)
        except Exception as e:
            man.append({"name": n, "url": u, "error": "harvest:" + repr(e)})
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))


if __name__ == "__main__":
    main()
