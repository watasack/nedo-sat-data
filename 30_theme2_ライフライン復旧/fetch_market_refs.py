#!/usr/bin/env python3
"""テーマ2「火口周辺の積雪水量」案の**事業性（実用化による社会発展性）**の一次情報取得。

問い:
 (1) 火山噴火緊急減災対策砂防計画・火山ハザードマップは誰がどう発注しているか（入札公告・落札金額）
 (2) リアルタイムハザードマップの運用実態、噴火警戒レベルでの積雪の使われ方
 (3) 予算の出どころ（砂防関係予算の火山分／文科省 火山研究事業／火山本部）
 (4) 電力インフラ（水力・送電）と融雪型火山泥流想定区域の重なり／融雪出水予測
 (5) 海外の積雪火山・ラハール市場

出力先は market_refs/。トリガ: trigger-fetch-market ブランチへの push
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

OUT = Path("market_refs")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

# ---------------------------------------------------------------- 検索クエリ
QUERIES = [
    # (1) 発注の実態
    '火山噴火緊急減災対策砂防計画 検討業務 入札公告',
    '火山噴火緊急減災対策砂防計画 業務 落札 金額 地方整備局',
    'site:mlit.go.jp 火山噴火緊急減災対策砂防計画 検討業務 契約',
    '火山ハザードマップ作成業務 委託 落札 金額 県',
    '火山噴火緊急減災対策砂防計画 策定 令和7年度 業務',
    '火山噴火緊急減災対策砂防計画 改定 令和6年度',
    '砂防 業務 落札結果 火山 令和7年度 一般競争入札 建設コンサルタント',
    '火山基礎調査 業務 入札公告 砂防',
    '融雪型火山泥流 数値シミュレーション 業務 委託',
    # (2) リアルタイム側
    'リアルタイムハザードマップ 火山 運用 砂防 国土交通省',
    '噴火警戒レベル 引上げ 積雪 融雪型火山泥流 避難計画',
    '火山防災協議会 コアグループ 予算 事務局',
    '火山防災協議会 活動火山対策特別措置法 改正 2023 義務',
    # (3) 予算
    '砂防関係予算 令和7年度 火山砂防 国土交通省',
    '火山調査研究推進本部 基本計画 令和6年',
    '火山調査研究推進本部 総合的な調査観測計画 融雪',
    '次世代火山研究・人材育成総合プロジェクト 後継 令和8年度 概算要求 火山',
    '火山調査研究推進本部 予算 文部科学省 令和7年度',
    # (4) 電力
    '融雪型火山泥流 発電所 被害 想定 水力',
    '常願寺川 水力発電所 土砂 火山 立山',
    '十勝岳 泥流 発電所 送電線',
    '積雪水量 融雪出水予測 水力発電 電力会社',
    '電力中央研究所 融雪 出水予測 積雪水量 衛星',
    # (5) 海外
    'Cotopaxi lahar snow ice melt hazard assessment glacier volume',
    'Mount Rainier lahar detection system snow water equivalent',
    'Ruapehu Katla Villarrica lahar snowpack hazard assessment',
    'snow water equivalent volcano lahar hazard assessment satellite',
]

SEARCH = []
for i, q in enumerate(QUERIES):
    SEARCH.append((f"bing_{i:02d}", "https://www.bing.com/search?q=" + urllib.parse.quote(q)))
    SEARCH.append((f"ddg_{i:02d}", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)))

# ---------------------------------------------------------------- 直URL
DIRECT = [
    # --- 火山本部（文科省 火山調査研究推進本部）
    ("kazanhonbu_top", "https://www.mext.go.jp/kazan_honbu/"),
    ("kazanhonbu_top2", "https://www.kazan-honbu.mext.go.jp/"),
    ("kazanhonbu_seisaku", "https://www.mext.go.jp/kazan_honbu/seisaku/index.html"),
    ("mext_kazan_index", "https://www.mext.go.jp/a_menu/kaihatu/jishin/index.htm"),
    ("mext_kazan_bousai", "https://www.mext.go.jp/a_menu/kaihatu/kazan/index.htm"),
    # --- 活火山法（2023改正）
    ("egov_katsukazanhou", "https://laws.e-gov.go.jp/api/1/lawdata/348AC1000000061"),
    ("bousai_kazan_index", "https://www.bousai.go.jp/kazan/index.html"),
    ("bousai_kazan_kyogikai", "https://www.bousai.go.jp/kazan/kyougikai/index.html"),
    ("bousai_kazan_shiryo", "https://www.bousai.go.jp/kazan/shiryo/index.html"),
    ("bousai_kazan_houkaisei", "https://www.bousai.go.jp/kazan/kaisei/index.html"),
    # --- 国交省 砂防・予算
    ("mlit_sabo_top", "https://www.mlit.go.jp/mizukokudo/sabo/index.html"),
    ("mlit_sabo_kazan", "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_disaster.html"),
    ("mlit_yosan_index", "https://www.mlit.go.jp/river/basic_info/yosan/index.html"),
    ("mlit_yosan_r7", "https://www.mlit.go.jp/page/kanbo08_hh_000041.html"),
    ("mlit_chotatsu", "https://www.mlit.go.jp/chotatsu.html"),
    ("mlit_sabo_realtime_hm", "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_sabo_kazan.html"),
    # --- 各地方整備局の入札・契約情報
    ("nyusatsu_thr", "https://www.thr.mlit.go.jp/bumon/b00097/k00030/index.html"),
    ("nyusatsu_thr2", "https://www.thr.mlit.go.jp/nyusatsu/"),
    ("nyusatsu_ktr", "https://www.ktr.mlit.go.jp/nyusatsu/index.html"),
    ("nyusatsu_hrr", "https://www.hrr.mlit.go.jp/nyusatsu/index.html"),
    ("nyusatsu_cbr", "https://www.cbr.mlit.go.jp/nyusatsu/index.html"),
    ("nyusatsu_hkd", "https://www.hkd.mlit.go.jp/ky/kn/kei_kan/ud49g70000005wo9.html"),
    ("ppi_top", "https://www.i-ppi.jp/"),
    ("geps_top", "https://www.geps.go.jp/"),
    # --- 建設コンサルタント側（業務実績）
    ("jcca_top", "https://www.jcca.or.jp/"),
    # --- リアルタイムハザードマップ
    ("hrr_midagahara_realtime", "https://www.hrr.mlit.go.jp/tateyama/jigyo/sabo/plan04.pdf"),
    ("nilim_kazan", "https://www.nilim.go.jp/lab/rbg/"),
    # --- 国土数値情報（発電施設・送電線）
    ("ksj_datalist", "https://nlftp.mlit.go.jp/ksj/index.html"),
    ("ksj_p03_hatsuden", "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P03-v3_1.html"),
    ("ksj_l02_soden", "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-L02-v3_0.html"),
    # --- 海外
    ("usgs_rainier_lahar", "https://www.usgs.gov/volcanoes/mount-rainier/lahar-detection-system"),
    ("usgs_lahar_hazards", "https://www.usgs.gov/programs/VHP/lahars-and-their-effects"),
    ("gvp_search", "https://volcano.si.edu/gvp_votw.cfm"),
    # --- 文献API（海外・国内の先行研究と市場）
    ("openalex_lahar_swe",
     "https://api.openalex.org/works?search=" + urllib.parse.quote("lahar snow water equivalent hazard") +
     "&per_page=50"),
    ("openalex_snowpack_volcano",
     "https://api.openalex.org/works?search=" + urllib.parse.quote("volcano snowpack lahar hazard assessment remote sensing") +
     "&per_page=50"),
    ("openalex_cotopaxi",
     "https://api.openalex.org/works?search=" + urllib.parse.quote("Cotopaxi lahar glacier ice melt hazard") +
     "&per_page=50"),
    ("openalex_swe_reconstruction",
     "https://api.openalex.org/works?search=" + urllib.parse.quote("snow water equivalent reconstruction snow disappearance date satellite") +
     "&per_page=50"),
    ("openalex_hydropower_swe",
     "https://api.openalex.org/works?search=" + urllib.parse.quote("snow water equivalent hydropower inflow forecasting") +
     "&per_page=50"),
    ("cinii_火山砂防_業務",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("火山砂防 計画 策定 業務") + "&format=json&count=50"),
    ("cinii_リアルタイムハザードマップ",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("火山 リアルタイムハザードマップ 運用") + "&format=json&count=50"),
    ("cinii_融雪出水",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("融雪出水 予測 水力発電") + "&format=json&count=50"),
]

# 索引ページからPDFを追跡するときのキーワード
PDF_KEY = re.compile(
    r"火山|砂防|入札|落札|契約|予算|概算要求|ハザード|泥流|積雪|発電|協議会|基本計画|調査観測")

# digest 抽出キーワード
KEYS_JP = ["入札", "落札", "契約金額", "予定価格", "業務名", "委託", "随意契約", "一般競争",
           "百万円", "億円", "千円", "予算", "概算要求", "火山砂防", "緊急減災",
           "リアルタイムハザードマップ", "火山防災協議会", "火山調査研究推進本部",
           "基本計画", "融雪型火山泥流", "積雪水量", "積雪深", "噴火警戒レベル",
           "水力発電", "送電線", "発電所", "建設コンサルタント"]
KEYS_EN = ["lahar", "snow water equivalent", "SWE", "Cotopaxi", "Rainier", "Ruapehu",
           "Katla", "Villarrica", "glacier", "hazard assessment", "warning system"]


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


def fetch(name, url, cap=40_000_000):
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
    pdf = data[:5] == b"%PDF"
    ext = ".pdf" if pdf else (".json" if ("json" in ctype or "format=json" in url
                                          or "api.openalex" in url) else ".html")
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=pdf)
    if pdf:
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    return rec


def crawl(name, url, man, seen, limit=12):
    rec = fetch(name, url)
    man.append(rec)
    f = rec.get("file")
    if not f or not f.endswith(".html"):
        return
    html = Path(f).read_text("utf-8", "replace")
    n = 0
    for m in re.finditer(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        full = urllib.parse.urljoin(rec.get("final_url") or url, href)
        if full in seen:
            continue
        if not (PDF_KEY.search(label) or PDF_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        safe = re.sub(r"[^0-9A-Za-z　-鿿]+", "_", label)[:40] or "pdf"
        sub = fetch(f"{name}__{safe}", full, cap=30_000_000)
        sub.update(from_index=name, label=label)
        man.append(sub)
        n += 1
        if n >= limit:
            break


def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


def digest():
    """検索結果HTMLはスニペットを、PDFは本文ヒット行を、それぞれ別ファイルにまとめる。"""
    # 検索結果のスニペット（URL付き）
    snips = []
    for h in sorted(OUT.glob("bing_*.html")) + sorted(OUT.glob("ddg_*.html")):
        s = h.read_text("utf-8", "replace")
        txt = strip_html(s)
        links = []
        for m in re.finditer(r'href="(https?://[^"]+)"', s):
            u = m.group(1).replace("&amp;", "&")
            if any(b in u for b in ("bing.com", "duckduckgo.com", "microsoft.com",
                                    "go.microsoft", "msn.com")):
                continue
            links.append(urllib.parse.unquote(u)[:220])
        seen, uniq = set(), []
        for u in links:
            k = u.split("?")[0]
            if k in seen:
                continue
            seen.add(k)
            uniq.append(u)
        snips.append("=" * 78)
        snips.append(f"FILE: {h.name}")
        snips.append("TEXT: " + txt[:4500])
        snips.append("LINKS:\n" + "\n".join("  " + u for u in uniq[:40]))
    OUT.joinpath("_digest_search.txt").write_text("\n".join(snips))

    # PDF本文
    out = []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_digest"):
            continue
        rows = t.read_text(errors="replace").split("\n")
        hits = [f"[L{i}]\n" + "\n".join(rows[max(0, i - 2):i + 3])
                for i, ln in enumerate(rows) if any(k in ln for k in KEYS_JP)]
        if hits:
            out.append("=" * 78)
            out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n---\n".join(hits[:60]))
    OUT.joinpath("_digest_pdf.txt").write_text("\n".join(out))

    # 直URLのHTML
    out2 = []
    for h in sorted(OUT.glob("*.html")):
        if h.name.startswith(("bing_", "ddg_")):
            continue
        s = strip_html(h.read_text("utf-8", "replace"))
        frag = [s[max(0, m.start() - 250):m.start() + 350]
                for m in re.finditer("|".join(KEYS_JP + KEYS_EN), s)]
        if frag:
            out2.append("=" * 78)
            out2.append(f"FILE: {h.name} hits={len(frag)}")
            out2.append("\n---\n".join(frag[:30]))
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for n, u in SEARCH:
        man.append(fetch(n, u))

    seen = set()
    for n, u in DIRECT:
        if u.endswith(".pdf") or "api." in u or "opensearch" in u:
            man.append(fetch(n, u))
        else:
            crawl(n, u, man, seen)

    # 検索結果から拾ったPDF（入札・落札・予算・火山関係のみ）を追跡
    follow = set()
    for h in OUT.glob("bing_*.html"):
        s = h.read_text("utf-8", "replace")
        for m in re.finditer(r'https?://[^\s"\'<>]+?\.pdf', s):
            u = urllib.parse.unquote(m.group(0).replace("&amp;", "&"))
            if len(u) > 300:
                continue
            if PDF_KEY.search(u):
                follow.add(u)
    for i, u in enumerate(sorted(follow)[:40]):
        if u in seen:
            continue
        man.append(fetch(f"follow_{i:02d}", u, cap=30_000_000))

    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))
    for m in man:
        print(" ", m.get("status"), m["name"], m.get("bytes"), str(m.get("error", ""))[:60])


if __name__ == "__main__":
    main()
