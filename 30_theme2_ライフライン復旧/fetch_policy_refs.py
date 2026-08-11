#!/usr/bin/env python3
"""テーマ2 未解決 C・G・E の一次資料を取りに行く（Actions 迂回）。

`13_事業計画の裏付け.md` 9節の未解決のうち、**取得で閉じられる3件**だけを狙う。
いずれも静的公開の制度文書・マニュアル・発注情報なので、動的サイト（PPI/GEPS）は最初から避ける。

  C（下流被害額の原単位）  … 13 8節の物量表（堤防嵩上げ11.0→20.6km、大型土のう36,600→78,700個、
                             総作業日数256→518日、氾濫範囲347→803世帯、床上浸水133→356）に
                             掛けると金額になる原単位を探す。国交省「治水経済調査マニュアル(案)」の
                             一般資産被害額原単位／家屋被害額原単位、砂防関係事業の費用便益分析マニュアル、
                             水害統計調査。→ ⑤の社会的インパクトと投資家レビュー #7・#8
  G（再委託の制度上の可否）… 「土木設計業務等委託契約書(案)」の一括再委託・主たる部分の再委託の制限、
                             設計業務等共通仕様書、設計共同体（協同企業体）の取扱基準、
                             簡易公募型プロポーザル方式の参加要件。→ 13 2節の選択肢(a)〜(d)の絞り込み。
                             **未解決A（元請けか再委託か）の前提**
  E（Phase 2 が年次になるか）… 「リアルタイムハザードマップの運用・整備」が単発か年次かを
                             発注の見通し・入札契約情報の実物で見る。→ 13 6節の閉ループの抜け道

経路は3本立てにしてある（`fetch_bid_refs.py` の第4バッチが index crawl だけで金額に届かなかったため）:

  (1) SINGLE … 直接URLの当てにいき
  (2) INDEX  … 所管課・砂防事務所の索引ページから1〜2階層のクロール
  (3) SEARCH … 検索エンジンHTML（ddg/bing/mojeek）→ 結果リンクのうち go.jp とPDFだけを追う

digest は C・G・E で別々に出す（同じ本文を3つの目的で読み分けるため）。
出力先は policy_refs/。トリガ: trigger-fetch-policy ブランチへの push
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

OUT = Path("policy_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {"User-Agent": UA,
     "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
     "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip, deflate", "Connection": "close"}

# GitHub は1ファイル100MBで push を弾く（`fetch_bid_refs.py` の初回はここで落ちた）。余裕を見て40MB。
MAX_BYTES = 40 * 1024 * 1024


def Q(s):
    return urllib.parse.quote_plus(s)


# ---------- (1) 直接URLの当てにいき ----------
SINGLE = [
    # --- C: 治水経済調査マニュアル・費用便益分析 ---
    ("c_mlit_hyouka_index",
     "https://www.mlit.go.jp/river/basic_info/seisaku_hyouka/gaiyou/hyouka/index.html"),
    ("c_mlit_seisaku_hyouka",
     "https://www.mlit.go.jp/river/basic_info/seisaku_hyouka/index.html"),
    ("c_mlit_suigai_toukei",
     "https://www.mlit.go.jp/river/toukei_chousa/kasen/suigaitoukei/index.html"),
    # --- G: 建設コンサルタント業務の契約制度（大臣官房技術調査課） ---
    ("g_mlit_tec_index", "https://www.mlit.go.jp/tec/index.html"),
    ("g_mlit_tec_gyoumu", "https://www.mlit.go.jp/tec/tec_tk_000006.html"),
    ("g_mlit_tec_nyuusatsu", "https://www.mlit.go.jp/tec/nyuusatsu.html"),
    ("g_mlit_sogo_const", "https://www.mlit.go.jp/sogoseisaku/const/index.html"),
    ("g_mlit_kensetsu_consul", "https://www.mlit.go.jp/tec/consultant.html"),
    # --- E: 砂防部・火山砂防 ---
    ("e_mlit_sabo_index", "https://www.mlit.go.jp/mizukokudo/sabo/index.html"),
    ("e_mlit_kazan_sabo", "https://www.mlit.go.jp/mizukokudo/sabo/kazan.html"),
    ("e_nikko_mitooshi_r8", "https://www.ktr.mlit.go.jp/ktr_content/content/000942554.pdf"),
]

# ---------- (2) 索引ページからのクロール ----------
INDEX = [
    # C
    ("c_hyouka_manual", "https://www.mlit.go.jp/river/basic_info/seisaku_hyouka/gaiyou/hyouka/"),
    ("c_sabo_hyouka", "https://www.mlit.go.jp/mizukokudo/sabo/jigyouhyouka.html"),
    # G
    ("g_tec_kijun", "https://www.mlit.go.jp/tec/tec_tk_000058.html"),
    ("g_tec_sekkei", "https://www.mlit.go.jp/tec/sekkeigyoumu.html"),
    ("g_ktr_nyuusatu", "https://www.ktr.mlit.go.jp/nyuusatu/index00000075.html"),
    ("g_thr_nyuusatu", "https://www.thr.mlit.go.jp/nyuusatu/index.html"),
    # E（積雪火山を抱える砂防事務所の発注の見通し・入札契約情報）
    ("e_nikko_nyuusatu", "https://www.ktr.mlit.go.jp/nikko/nikko_index014.html"),  # 那須岳
    ("e_shinjyou", "https://www.thr.mlit.go.jp/shinjyou/index.html"),              # 鳥海山
    ("e_yamagata_kasen", "https://www.thr.mlit.go.jp/yamagata/index.html"),        # 蔵王
    ("e_tateyama", "https://www.hrr.mlit.go.jp/tateyama/index.html"),              # 弥陀ヶ原
    ("e_obihiro", "https://www.hkd.mlit.go.jp/ob/index.html"),                     # 十勝岳
]

LINK_KEY = re.compile(
    r"マニュアル|便益|経済調査|評価|被害|原単位|水害統計|"
    r"委託契約|契約書|共通仕様書|再委託|共同体|プロポーザル|参加資格|要領|基準|通知|"
    r"ハザードマップ|リアルタイム|火山|砂防|緊急減災|発注|見通し|入札|契約|業務|公表|一覧|令和")
DOC_EXT = (".pdf", ".csv", ".xls", ".xlsx", ".doc", ".docx")

# ---------- (3) 検索エンジン ----------
QUERIES_C = [
    '治水経済調査マニュアル(案) 一般資産被害額 原単位',
    '治水経済調査マニュアル 家屋被害額 原単位 床上浸水',
    '砂防関係事業 費用便益分析マニュアル 原単位',
    '土砂災害 被害額 原単位 人家 1戸あたり 国土交通省',
    '火山砂防事業 事業評価 費用便益 想定被害額 融雪型火山泥流',
    '水害統計調査 一般資産等被害額 世帯 原単位',
]
QUERIES_G = [
    '土木設計業務等委託契約書(案) 一括再委託の禁止 第七条',
    '建設コンサルタント業務 再委託 主たる部分 発注者の承諾',
    '設計業務等共通仕様書 再委託 国土交通省',
    '建設コンサルタント業務 設計共同体 取扱基準 参加資格',
    '簡易公募型プロポーザル方式 参加要件 建設コンサルタント登録',
]
QUERIES_E = [
    'リアルタイムハザードマップ 整備 業務 火山 発注の見通し',
    'リアルタイムハザードマップ 更新 業務 落札 砂防',
    '火山噴火緊急減災対策砂防計画 改定 業務 発注の見通し 令和',
]
SEARCH = []
for tag, qs in (("c", QUERIES_C), ("g", QUERIES_G), ("e", QUERIES_E)):
    for i, q in enumerate(qs):
        SEARCH.append((f"{tag}_ddg_{i}", "https://html.duckduckgo.com/html/?q=" + Q(q)))
        SEARCH.append((f"{tag}_bing_{i}", "https://www.bing.com/search?q=" + Q(q) + "&count=50"))
        SEARCH.append((f"{tag}_mojeek_{i}", "https://www.mojeek.com/search?q=" + Q(q)))


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
        with urllib.request.urlopen(req, timeout=90) as r:
            declared = int(r.headers.get("Content-Length") or 0)
            if declared > MAX_BYTES:
                rec["status"] = r.status
                rec["skipped"] = f"too_large_declared:{declared}"
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

    # Content-Length を返さないサーバがあるので実体でももう一度見る
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
            # マニュアルの原単位表も契約情報も表組みなので -layout は必須（列がつぶれると
            # 金額と項目名の対応が消える）
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
        # DuckDuckGo は結果を /l/?uddg=<encoded> に包む。中身を取り出す
        if "duckduckgo.com/l/" in full:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(full).query).get("uddg")
            if q:
                full = q[0]
        out.append((full, re.sub(r"\s+", " ", label).strip()))
    return out


def crawl(name, url, man, seen, depth2=8, per=6):
    """索引ページ → 関連文書、および索引ページ → 下位ページ → 関連文書の2階層。"""
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


# 検索結果から追うのは公的機関のドメインとPDFに限る（ブログ・まとめサイトは根拠にならない）
GOV = re.compile(r"://[^/]*\.(go\.jp|lg\.jp|or\.jp|ac\.jp)(/|$)")


def harvest(name, url, man, seen, per=6):
    """検索エンジンHTMLを取り、結果リンクのうち公的ドメイン／PDFだけを追う。"""
    r = fetch(name, url)
    man.append(r)
    c = 0
    for full, label in links_of(r, url):
        if full in seen:
            continue
        u = urllib.parse.unquote(full)
        if not (GOV.search(full) or full.lower().endswith(".pdf")):
            continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(u)):
            continue
        seen.add(full)
        man.append(fetch(f"{name}__{safe(label, 'hit')}", full))
        c += 1
        if c >= per:
            break


# ---------- digest ----------
MONEY = re.compile(r"[0-9０-９,，\.]{2,}\s*(円|千円|百万円|億円|万円)")

KEY_C = re.compile(r"原単位|被害額|被害率|一般資産|家庭用品|家屋|事業所|償却資産|在庫資産|"
                   r"床上浸水|床下浸水|営業停止|便益|B/C|費用便益|治水経済|水害統計")
KEY_G = re.compile(r"再委託|一括委任|一括下請|主たる部分|承諾|設計共同体|共同企業体|competitive|"
                   r"プロポーザル|参加資格|参加表明|建設コンサルタント登録|受注者は|委託契約書")
KEY_E = re.compile(r"リアルタイムハザードマップ|ハザードマップ|緊急減災|火山噴火緊急減災|"
                   r"発注の見通し|発注見通し|履行期間|継続|更新|運用|整備")


def digest(tag, key, need_money, fname, head):
    hits, hits2 = [], []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_"):
            continue
        # ファイル名の接頭辞で対象を絞る（c_ / g_ / e_）。検索由来の派生名も接頭辞を継ぐ
        if not t.name.startswith(tag + "_"):
            continue
        rows = t.read_text(errors="replace").split("\n")
        for i, ln in enumerate(rows):
            if not key.search(ln):
                continue
            ctx = [x.rstrip() for x in rows[max(0, i - 2):i + 3] if x.strip()]
            blob = " / ".join(ctx)
            if need_money and MONEY.search(blob):
                hits.append(f"[{t.name} L{i}] {blob}")
            else:
                hits2.append(f"[{t.name} L{i}] {blob}")
    body = head + "\n\n"
    if need_money:
        body += ("### キーワード＋金額表記あり（最優先で読む）\n" + "\n".join(hits[:500])
                 + "\n\n### キーワードのみ\n" + "\n".join(hits2[:500]))
    else:
        body += "### キーワードのヒット\n" + "\n".join(hits2[:800])
    OUT.joinpath(fname).write_text(body)
    print(f"digest {tag}: money-hits {len(hits)} / other {len(hits2)}")


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

    digest("c", KEY_C, True, "_digest_C_genntanka.txt",
           "# 未解決C: 下流被害額の原単位\n"
           "13 8節の物量表（氾濫範囲347→803世帯、床上浸水133→356、堤防嵩上げ11.0→20.6km、"
           "大型土のう36,600→78,700個、総作業日数256→518日）に掛けられる原単位を探す。")
    digest("g", KEY_G, False, "_digest_G_saiitaku.txt",
           "# 未解決G: 再委託の制度上の可否\n"
           "13 2節の選択肢(a)登録／(b)横売り／(c)県事業／(d)共同提案 のうち、制度上不可能なものを消す。"
           "見るのは「一括再委託の禁止」「主たる部分の再委託の制限」「設計共同体の参加資格」"
           "「プロポーザルの参加要件」の4点。")
    digest("e", KEY_E, True, "_digest_E_realtime.txt",
           "# 未解決E: リアルタイムハザードマップの運用・整備が年次発注か\n"
           "13 6節の閉ループ（一巡すると終わる）に抜け道があるかを、発注の実物で見る。")

    ok = sum(1 for m in man if m.get("status") == 200)
    print("ok:", ok, "/", len(man))


if __name__ == "__main__":
    main()
