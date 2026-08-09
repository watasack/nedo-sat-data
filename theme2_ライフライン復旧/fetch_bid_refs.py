#!/usr/bin/env python3
"""テーマ2 事業性調査 第4バッチ ── 単価（契約金額）の実額を取りに行く。

第3バッチ（`fetch_market3_refs.py`）で日光砂防の R8 発注見通しに
「Ｒ８那須岳火山噴火緊急減災対策検討業務／人工衛星を活用した積雪深推定の検討」を発見したが、
**落札金額は一件も取れなかった**（入札情報サービス PPI と GEPS は動的サイトで到達不可）。
`01_検討経緯.md` 8.7節に「規模感を書くなら手動確認が要る。推測値は書かないこと」として残っている。

このバッチはそこだけを狙う。動的サイトは避け、**静的に公開されている契約結果の一覧PDF**を取る:

  1. 公共調達の適正化に基づく「契約に係る情報の公表」（各地方整備局・北海道開発局の月次一覧PDF）
  2. 積雪火山を抱える砂防事務所そのものの入札・契約情報ページ
  3. （一財）砂防・地すべり技術センターの事業報告・財務諸表（受託業務の規模の外形）
  4. 都道府県（山形・宮城＝蔵王、秋田・山形＝鳥海、福島＝磐梯、北海道＝十勝岳/樽前）の委託業務入札結果

digest は「業務名の行」と「金額らしき行」を別々に拾う。契約結果の一覧PDFは表組みなので
`pdftotext -layout` を通した上で、火山砂防系のキーワードを含む行の前後を出す。

出力先は bid_refs/。トリガ: trigger-fetch-bid ブランチへの push
（workflow_dispatch API はこの環境の GitHub 統合では 403 になるため push 駆動）
"""
import gzip
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

OUT = Path("bid_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {"User-Agent": UA,
     "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
     "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip, deflate", "Connection": "close"}

SINGLE = [
    # 那須岳（那須岳＝日光砂防）の発注見通し原本。第3バッチで取得済みだが金額欄が無いことの再確認用
    ("nikko_mitooshi_r8", "https://www.ktr.mlit.go.jp/ktr_content/content/000942554.pdf"),
    # 砂防・地すべり技術センター（受託の常連。事業報告に受託業務の件数と規模が出る）
    ("stc_top", "https://www.stc.or.jp/"),
    ("stc_jigyou", "https://www.stc.or.jp/about/disclosure.html"),
]

# crawl の起点。契約結果・入札結果の一覧は各サイトとも「入札・契約情報」配下の静的PDF
INDEX = [
    # --- 地方整備局・開発局の契約情報（公共調達の適正化に基づく公表） ---
    ("ktr_keiyaku", "https://www.ktr.mlit.go.jp/nyuusatu/index00000075.html"),
    ("thr_nyuusatu", "https://www.thr.mlit.go.jp/nyuusatu/index.html"),
    ("thr_keiyaku_jouhou", "https://www.thr.mlit.go.jp/nyuusatu/keiyakujouhou/index.html"),
    ("hrr_nyusatsu", "https://www.hrr.mlit.go.jp/nyusatsu/index.html"),
    ("hkd_keiyaku", "https://www.hkd.mlit.go.jp/ky/ky/keiyaku/index.html"),
    # --- 積雪火山を抱える砂防事務所 ---
    ("nikko_nyuusatu", "https://www.ktr.mlit.go.jp/nikko/nikko_index014.html"),      # 那須岳
    ("shinjyou", "https://www.thr.mlit.go.jp/shinjyou/index.html"),                  # 鳥海山
    ("fukushima_kokudou", "https://www.thr.mlit.go.jp/fukushima/index.html"),        # 磐梯山
    ("yamagata_kasen", "https://www.thr.mlit.go.jp/yamagata/index.html"),            # 蔵王
    ("tateyama_keiyaku", "https://www.hrr.mlit.go.jp/tateyama/keiyaku/index.html"),  # 弥陀ヶ原
    ("obihiro_kaihatsu", "https://www.hkd.mlit.go.jp/ob/index.html"),                # 十勝岳
    # --- 都道府県（県事業火山。委託業務の入札結果は県サイトに静的公開されることが多い） ---
    ("yamagata_pref_nyusatsu", "https://www.pref.yamagata.jp/020055/bosai/index.html"),
    ("miyagi_pref_sabo", "https://www.pref.miyagi.jp/soshiki/sabou/index.html"),
]

LINK_KEY = re.compile(
    r"契約|落札|入札|結果|公表|一覧|適正化|業務|コンサル|砂防|火山|那須|蔵王|鳥海|磐梯|十勝|樽前|"
    r"弥陀|緊急減災|積雪|発注|見通し|令和[０-９0-9]|事業報告|決算|財務")
DOC_EXT = (".pdf", ".csv", ".xls", ".xlsx")


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


def safe(s, fallback):
    s = re.sub(r"[^0-9A-Za-z぀-ヿ一-鿿]+", "_", (s or "").strip())[:60]
    return s.strip("_") or fallback


def fetch(name, url):
    rec = {"name": name, "url": url}
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=60) as r:
            body = _read(r)
            rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec

    ext = ".pdf" if ("pdf" in ctype or url.lower().endswith(".pdf")) else (
        ".json" if "json" in ctype else ".html")
    p = OUT / (name + ext)
    p.write_bytes(body)
    rec["bytes"] = len(body)

    if ext == ".pdf":
        try:
            # 契約結果は表組みなので -layout は必須（列がつぶれると金額と業務名の対応が消える）
            subprocess.run(["pdftotext", "-layout", str(p), str(p.with_suffix(".txt"))],
                           check=True, capture_output=True, timeout=180)
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
        out.append((urllib.parse.urljoin(base, href), re.sub(r"\s+", " ", label).strip()))
    return out


def crawl(name, url, man, seen, depth2=8, per=6):
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
            man.append(fetch(f"{name}__doc_{safe(label, 'd')}", full))
        else:
            kids.append((full, label))
    for full, label in kids[:depth2]:
        n2 = f"{name}__{safe(label, 'sub')}"
        r2 = fetch(n2, full)
        man.append(r2)
        c = 0
        for f3, l3 in links_of(r2, full):
            if f3 in seen or not f3.lower().endswith(DOC_EXT):
                continue
            if not (LINK_KEY.search(l3) or LINK_KEY.search(urllib.parse.unquote(f3))):
                continue
            seen.add(f3)
            man.append(fetch(f"{n2}__{safe(l3, 'd')}", f3))
            c += 1
            if c >= per:
                break


# 業務名で当てにいくキーワード（火山砂防系の検討業務）
NAME_KEY = re.compile(r"火山|砂防計画|緊急減災|噴火|那須岳|蔵王|鳥海|磐梯|十勝岳|樽前|弥陀ヶ原|"
                      r"ハザードマップ|積雪|融雪|土砂災害")
# 金額らしき表記
MONEY = re.compile(r"[0-9０-９,，]{4,}\s*(円|千円|百万円|億円)")


def digest():
    """業務名キーワードを含む行と、同じ行または近傍にある金額を突き合わせる。"""
    hits_named, hits_money = [], []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_"):
            continue
        rows = t.read_text(errors="replace").split("\n")
        for i, ln in enumerate(rows):
            if not NAME_KEY.search(ln):
                continue
            ctx = [x.rstrip() for x in rows[max(0, i - 2):i + 3] if x.strip()]
            blob = " / ".join(ctx)
            (hits_money if MONEY.search(blob) else hits_named).append(
                f"[{t.name} L{i}] {blob}")
    OUT.joinpath("_digest_money.txt").write_text(
        "### 業務名キーワード＋金額表記あり（最優先で読む）\n"
        + "\n".join(hits_money[:400])
        + "\n\n### 業務名キーワードのみ（金額が近傍に無い）\n"
        + "\n".join(hits_named[:400]))
    print("digest: money-hits", len(hits_money), "name-only", len(hits_named))


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
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))


if __name__ == "__main__":
    main()
