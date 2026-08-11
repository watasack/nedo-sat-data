#!/usr/bin/env python3
"""テーマ2 事業性調査 第3バッチ。第2バッチで日光砂防の R8 発注見通しに
「Ｒ８那須岳火山噴火緊急減災対策検討業務／人工衛星を活用した積雪深推定の検討」を発見した。
第3バッチはその周辺（契約結果＝金額、那須岳計画）と、予算の出どころ（内閣府・文科省火山本部）、
電力インフラ、海外を埋める。

出力先は market_refs3/。トリガ: trigger-fetch-market3 ブランチへの push
"""
import gzip, io, json, re, subprocess, urllib.error, urllib.parse, urllib.request, zlib
from pathlib import Path

OUT = Path("market_refs3")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {"User-Agent": UA,
     "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
     "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip, deflate", "Connection": "close"}

SINGLE = [
    ("mext_kazanhonbu_top", "https://www.mext.go.jp/a_menu/kaihatu/jishin/1285728_00005.html"),
    ("mext_kazanhonbu_chukan", "https://www.mext.go.jp/content/20250929-mxt_jishin01-000044975_16.pdf"),
    ("nikko_nasu_plan", "https://www.ktr.mlit.go.jp/nikko/nikko00169.html"),
    ("kazansabo_nasu", "https://www.kazan-sabo.jp/pdf/05.pdf"),
    ("tochigi_nasu_kiso", "https://www.pref.tochigi.lg.jp/l01/documents/20260330144514.pdf"),
    ("tochigi_nasu_shiryo", "https://www.pref.tochigi.lg.jp/l01/documents/20260330163834.pdf"),
    ("ksj_p03_v3", "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P03-v3_0.html"),
    ("usgs_vhp", "https://www.usgs.gov/programs/volcano-hazards"),
    ("usgs_lahar", "https://www.usgs.gov/programs/volcano-hazards/lahars"),
    ("oa_swe_return_period", "https://api.openalex.org/works?search=" +
     urllib.parse.quote("snow water equivalent return period extreme value design") + "&per_page=30"),
    ("oa_landsat_snow_disappearance", "https://api.openalex.org/works?search=" +
     urllib.parse.quote("Landsat snow disappearance date reconstruction mountain SWE") + "&per_page=30"),
]

INDEX = [
    ("ktr_keiyakukekka_r7", "https://www.ktr.mlit.go.jp/nyuusatu/index00000075.html"),
    ("ktr_nyuusatu", "https://www.ktr.mlit.go.jp/nyuusatu/index.html"),
    ("nikko_nyuusatu", "https://www.ktr.mlit.go.jp/nikko/nikko_index014.html"),
    ("bousai_yosan", "https://www.bousai.go.jp/kazan/yosan/index.html"),
    ("bousai_yosan_r06g", "https://www.bousai.go.jp/kazan/yosan/r06gaisan/index.html"),
    ("bousai_yosan_r05y", "https://www.bousai.go.jp/kazan/yosan/r05yosan/index.html"),
    ("mext_kazanhonbu_kaigi", "https://www.mext.go.jp/a_menu/kaihatu/jishin/mext_02705.html"),
    ("kazansabo", "https://www.kazan-sabo.jp/"),
    ("shinjyou_kazan", "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/kazan-funka.html"),
    ("tateyama_keiyaku", "https://www.hrr.mlit.go.jp/tateyama/keiyaku/index.html"),
    ("enecho_hydro_db", "https://www.enecho.meti.go.jp/category/electricity_and_gas/electric/hydroelectric/database/"),
]

LINK_KEY = re.compile(r"契約|落札|入札|結果|公表|予算|概算要求|火山|砂防|那須|積雪|発電|水力|包蔵|"
                      r"調査観測|基本計画|中間|とりまとめ|議事|資料")
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
        try:
            d = gzip.GzipFile(fileobj=io.BytesIO(d)).read()
        except Exception:
            pass
    return d


def fetch(name, url, cap=30_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90) as r:
            data = _read(r); rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower(); rec["final_url"] = r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code; rec["error"] = str(e); return rec
    except Exception as e:
        rec["error"] = repr(e); return rec
    if len(data) > cap:
        rec["truncated_from"] = len(data); data = data[:cap]
    pdf = data[:4] == b"%PDF"
    low = url.lower()
    if pdf: ext = ".pdf"
    elif low.endswith(".csv"): ext = ".csv"
    elif low.endswith(".xlsx"): ext = ".xlsx"
    elif low.endswith(".xls"): ext = ".xls"
    elif "json" in ctype or "api.openalex" in url: ext = ".json"
    else: ext = ".html"
    p = OUT / f"{name}{ext}"; p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=pdf)
    if pdf:
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
    return rec


def links_of(rec, url):
    f = rec.get("file")
    if not f or not f.endswith(".html"): return []
    html = Path(f).read_text("utf-8", "replace")
    base = rec.get("final_url") or url
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if href.lower().startswith(("javascript:", "mailto:", "tel:")): continue
        out.append((urllib.parse.urljoin(base, href), label))
    return out


def safe(l, fb):
    s = re.sub(r"[^0-9A-Za-z　-鿿ぁ-んァ-ヶ]+", "_", l)[:46]
    return s or fb


def crawl(name, url, man, seen, depth2=10, per=14):
    rec = fetch(name, url); man.append(rec)
    kids = []
    for full, label in links_of(rec, url):
        if full in seen: continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))): continue
        seen.add(full)
        if full.lower().endswith(DOC_EXT):
            man.append(fetch(f"{name}__doc_{safe(label,'d')}", full))
        else:
            kids.append((full, label))
    for full, label in kids[:depth2]:
        n2 = f"{name}__{safe(label,'sub')}"
        r2 = fetch(n2, full); man.append(r2); c = 0
        for f3, l3 in links_of(r2, full):
            if f3 in seen or not f3.lower().endswith(DOC_EXT): continue
            if not (LINK_KEY.search(l3) or LINK_KEY.search(urllib.parse.unquote(f3))): continue
            seen.add(f3); man.append(fetch(f"{n2}__{safe(l3,'d')}", f3)); c += 1
            if c >= per: break


KEYS = ["契約金額", "落札", "予定価格", "業務名", "火山", "積雪", "那須", "予算", "概算要求",
        "億円", "百万円", "千円", "水力", "発電", "包蔵", "調査観測計画", "融雪"]


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        if t.name.startswith("_"): continue
        rows = t.read_text(errors="replace").split("\n")
        hits = [f"[L{i}] " + " / ".join(x.strip() for x in rows[max(0, i-1):i+2] if x.strip())
                for i, ln in enumerate(rows) if any(k in ln for k in KEYS)]
        if hits:
            out.append("=" * 78); out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n".join(hits[:70]))
    OUT.joinpath("_digest_pdf.txt").write_text("\n".join(out))


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for n, u in SINGLE: man.append(fetch(n, u))
    seen = set()
    for n, u in INDEX:
        try: crawl(n, u, man, seen)
        except Exception as e: man.append({"name": n, "url": u, "error": "crawl:" + repr(e)})
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))


if __name__ == "__main__":
    main()
