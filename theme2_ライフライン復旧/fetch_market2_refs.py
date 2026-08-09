#!/usr/bin/env python3
"""テーマ2 事業性調査 第2バッチ。第1バッチで Bing/DDG が両方 bot 判定で落ちたので、
検索エンジンに頼らず「索引ページを2段クロールして目的のPDFを拾う」方式に切り替える。

狙い:
 (1) 地方整備局・砂防事務所の**調達情報**（入札公告・落札結果・発注見通し）
 (2) 砂防・地すべり技術センター(STC)の受託実績＝実際に誰が計画を作っているか
 (3) 文科省 火山調査研究推進本部（火山本部）の所在と基本計画・予算
 (4) 内閣府 火山防災協議会の制度と体制
 (5) 電力インフラ（水力発電所・送電線）の所在データ
 (6) 海外（Rainier/Ruapehu/Cotopaxi/Katla）のラハール警報・積雪評価

出力先は market_refs2/。トリガ: trigger-fetch-market2 ブランチへの push
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

OUT = Path("market_refs2")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

# ---- 単発取得（PDF / API / 単ページ）
SINGLE = [
    # 火山本部（URL候補を総当たり）
    ("kh_a", "https://www.kazan-honbu.mext.go.jp/"),
    ("kh_b", "https://www.kazan.mext.go.jp/"),
    ("kh_c", "https://www.mext.go.jp/kazanhonbu/"),
    ("kh_d", "https://www.mext.go.jp/b_menu/shingi/kazan/index.htm"),
    ("kh_e", "https://www.jishin.go.jp/"),
    ("wiki_kazanhonbu",
     "https://ja.wikipedia.org/w/api.php?action=query&prop=extlinks|revisions&rvprop=content&rvslots=main"
     "&format=json&titles=" + urllib.parse.quote("火山調査研究推進本部")),
    ("wiki_kazansabo",
     "https://ja.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main"
     "&format=json&titles=" + urllib.parse.quote("融雪型火山泥流")),
    ("wiki_lahar_en",
     "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main"
     "&format=json&titles=Lahar"),
    ("wiki_rainier_en",
     "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main"
     "&format=json&titles=" + urllib.parse.quote("Mount Rainier")),
    # 代替検索エンジン（Actions から通るか試す）
    ("yahoojp_0", "https://search.yahoo.co.jp/search?p=" +
     urllib.parse.quote("火山噴火緊急減災対策砂防計画 検討業務 入札")),
    ("marginalia_0", "https://search.marginalia.nu/search?query=" +
     urllib.parse.quote("volcano snow water equivalent lahar hazard")),
    ("searx_0", "https://searx.be/search?q=" +
     urllib.parse.quote("火山噴火緊急減災対策砂防計画 落札") + "&format=json"),
    ("ecosia_0", "https://www.ecosia.org/search?q=" +
     urllib.parse.quote("火山噴火緊急減災対策砂防計画 業務 落札")),
    ("startpage_0", "https://www.startpage.com/sp/search?query=" +
     urllib.parse.quote("火山噴火緊急減災対策砂防計画 業務 落札")),
    # OpenAlex 追加（海外市場・先行）
    ("oa_lahar_warning",
     "https://api.openalex.org/works?search=" +
     urllib.parse.quote("lahar warning system volcano glacier snow melt") + "&per_page=50"),
    ("oa_ruapehu",
     "https://api.openalex.org/works?search=" +
     urllib.parse.quote("Ruapehu crater lake lahar warning ERLAWS") + "&per_page=30"),
    ("oa_katla",
     "https://api.openalex.org/works?search=" +
     urllib.parse.quote("Katla jokulhlaup ice cauldron hazard") + "&per_page=30"),
    ("oa_snow_volcano_jp",
     "https://api.openalex.org/works?search=" +
     urllib.parse.quote("snow depth volcanic mudflow Japan sabo planning") + "&per_page=30"),
    # 資源エネルギー庁 包蔵水力・水力発電
    ("enecho_hydro_db",
     "https://www.enecho.meti.go.jp/category/electricity_and_gas/electric/hydroelectric/database/"),
    ("enecho_hydro_top",
     "https://www.enecho.meti.go.jp/category/electricity_and_gas/electric/hydroelectric/"),
    # 国土数値情報（発電施設）
    ("ksj_p03", "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P03.html"),
    # 海外（ラハール警報・積雪）
    ("usgs_rainier", "https://www.usgs.gov/volcanoes/mount-rainier"),
    ("usgs_cvo", "https://www.usgs.gov/observatories/cvo"),
    ("pnsn_lahar", "https://pnsn.org/volcanoes/lahar-detection"),
    ("gns_ruapehu", "https://www.gns.cri.nz/research-projects/ruapehu-crater-lake/"),
    ("geonet_ruapehu", "https://www.geonet.org.nz/volcano/ruapehu"),
    ("igepn_cotopaxi", "https://www.igepn.edu.ec/cotopaxi"),
    ("imo_katla", "https://en.vedur.is/earthquakes-and-volcanism/volcanic-eruptions/katla/"),
]

# ---- 索引ページ（2段クロール）
INDEX = [
    # 地方整備局トップ → 入札・契約・調達
    ("thr", "https://www.thr.mlit.go.jp/"),
    ("ktr", "https://www.ktr.mlit.go.jp/"),
    ("hrr", "https://www.hrr.mlit.go.jp/"),
    ("cbr", "https://www.cbr.mlit.go.jp/"),
    ("hkd", "https://www.hkd.mlit.go.jp/"),
    ("mlit_top", "https://www.mlit.go.jp/"),
    # 火山を持つ砂防事務所
    ("tateyama", "https://www.hrr.mlit.go.jp/tateyama/"),
    ("shinjyou", "https://www.thr.mlit.go.jp/shinjyou/"),
    ("fujisabo", "https://www.cbr.mlit.go.jp/fujisabo/"),
    ("tajimi", "https://www.cbr.mlit.go.jp/tajimi/"),
    ("tonesabo", "https://www.ktr.mlit.go.jp/tonesui/"),
    ("nikko", "https://www.ktr.mlit.go.jp/nikko/"),
    ("hkd_as", "https://www.hkd.mlit.go.jp/as/"),
    # 受託側（砂防・地すべり技術センター）
    ("stc", "https://www.stc.or.jp/"),
    ("stc_jigyo", "https://www.stc.or.jp/jigyou/"),
    ("stc_gaiyo", "https://www.stc.or.jp/gaiyou/"),
    # 内閣府 火山
    ("bousai_kazan_houritsu", "https://www.bousai.go.jp/kazan/kazan_houritsu/index.html"),
    ("bousai_kazan_top", "https://www.bousai.go.jp/kazan/"),
    # 文科省
    ("mext_top", "https://www.mext.go.jp/"),
    ("mext_yosan", "https://www.mext.go.jp/a_menu/yosan/index.htm"),
    ("kazanpj", "https://www.kazan-pj.jp/"),
    ("kazanpj_report", "https://www.kazan-pj.jp/reporting/"),
    # 砂防部の火山砂防
    ("mlit_kazan_sabo", "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_sabo_kazan.html"),
    ("mlit_sabo_yosan", "https://www.mlit.go.jp/mizukokudo/sabo/sabo_yosan.html"),
]

LINK_KEY = re.compile(r"入札|契約|調達|発注|公告|落札|見通し|予算|概算要求|火山|砂防|協議会|"
                      r"基本計画|調査観測|実績|業務|事業報告|決算|会計")
PDF_KEY = re.compile(r"入札|契約|調達|発注|公告|落札|見通し|予算|概算要求|火山|砂防|協議会|"
                     r"基本計画|調査観測|実績|業務|事業報告|決算")

KEYS_JP = ["入札", "落札", "契約金額", "予定価格", "業務名", "委託", "随意契約", "一般競争",
           "百万円", "億円", "千円", "予算", "概算要求", "火山砂防", "緊急減災",
           "リアルタイムハザードマップ", "火山防災協議会", "火山調査研究推進本部",
           "基本計画", "融雪型火山泥流", "積雪水量", "積雪深", "噴火警戒レベル",
           "水力発電", "送電線", "発電所", "建設コンサルタント", "受託"]


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


def fetch(name, url, cap=30_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90) as r:
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
    pdf = data[:4] == b"%PDF"          # ← 第1バッチのバグ（[:5] と 4byte 比較）を修正
    ext = ".pdf" if pdf else (".json" if ("json" in ctype or "api.openalex" in url
                                          or "api.php" in url) else ".html")
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=pdf)
    if pdf:
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    return rec


def links_of(rec, url):
    f = rec.get("file")
    if not f or not f.endswith(".html"):
        return []
    html = Path(f).read_text("utf-8", "replace")
    base = rec.get("final_url") or url
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        out.append((urllib.parse.urljoin(base, href), label))
    return out


def safe(label, fallback):
    s = re.sub(r"[^0-9A-Za-z　-鿿ぁ-んァ-ヶ]+", "_", label)[:46]
    return s or fallback


def crawl(name, url, man, seen, depth2=8, pdf_per_page=10):
    """索引ページ → 入札/契約系の子ページ(depth2件) → その中のPDF(pdf_per_page件)"""
    rec = fetch(name, url)
    man.append(rec)
    kids = []
    for full, label in links_of(rec, url):
        if full in seen:
            continue
        hit = LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))
        if not hit:
            continue
        seen.add(full)
        if full.lower().endswith(".pdf"):
            man.append(fetch(f"{name}__pdf_{safe(label,'p')}", full))
        else:
            kids.append((full, label))
    for full, label in kids[:depth2]:
        n2 = f"{name}__{safe(label,'sub')}"
        r2 = fetch(n2, full)
        man.append(r2)
        cnt = 0
        for f3, l3 in links_of(r2, full):
            if f3 in seen or not f3.lower().endswith(".pdf"):
                continue
            if not (PDF_KEY.search(l3) or PDF_KEY.search(urllib.parse.unquote(f3))):
                continue
            seen.add(f3)
            man.append(fetch(f"{n2}__{safe(l3,'p')}", f3))
            cnt += 1
            if cnt >= pdf_per_page:
                break


def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_digest"):
            continue
        rows = t.read_text(errors="replace").split("\n")
        hits = [f"[L{i}] " + " / ".join(x.strip() for x in rows[max(0, i - 1):i + 2] if x.strip())
                for i, ln in enumerate(rows) if any(k in ln for k in KEYS_JP)]
        if hits:
            out.append("=" * 78)
            out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n".join(hits[:60]))
    OUT.joinpath("_digest_pdf.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        s = strip_html(h.read_text("utf-8", "replace"))
        frag = [s[max(0, m.start() - 200):m.start() + 300]
                for m in re.finditer("|".join(KEYS_JP), s)]
        if frag:
            out2.append("=" * 78)
            out2.append(f"FILE: {h.name} hits={len(frag)}")
            out2.append("\n---\n".join(frag[:20]))
    OUT.joinpath("_digest_html.txt").write_text("\n".join(out2))


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
    for m in man:
        print(" ", m.get("status"), m["name"], m.get("bytes"), str(m.get("error", ""))[:60])


if __name__ == "__main__":
    main()
