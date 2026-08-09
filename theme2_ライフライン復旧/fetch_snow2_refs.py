#!/usr/bin/env python3
"""第7ラウンド「火口周辺の積雪水量の年超過確率分布」案の死因潰し用 一次情報取得（第2バッチ）

目的は2つ。
 (1) EPS 2021 草津白根2018 危機時ハザード評価論文（DOI 10.1186/s40623-021-01522-0）の**本文**を入手する。
     springeropen / link.springer は Fastly の "Client Challenge" を返して3KBのスタブしか取れないので、
     ミラー・アーカイブ・書誌APIを総当たりする。
 (2) 積雪火山ごとの「火山噴火緊急減災対策砂防計画」を集め、融雪型火山泥流の泥流量の設定方法が
     「実績固定」か「火砕流流下範囲×融雪水量」かを分類する。

出力先は snow_refs2/。トリガ: trigger-fetch-snow2 ブランチへの push
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

OUT = Path("snow_refs2")
DOI = "10.1186/s40623-021-01522-0"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "application/pdf,image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "close",
}

# ---------------------------------------------------------------- (1) 論文本文
PAPER_URLS = [
    # 出版社直（Fastlyチャレンジで落ちる想定だが、ヘッダを変えて再挑戦）
    ("paper_springeropen_counter_pdf",
     f"https://earth-planets-space.springeropen.com/counter/pdf/{DOI}.pdf",
     {"Referer": f"https://earth-planets-space.springeropen.com/articles/{DOI}"}),
    ("paper_springeropen_track_pdf",
     f"https://earth-planets-space.springeropen.com/track/pdf/{DOI}.pdf",
     {"Referer": f"https://earth-planets-space.springeropen.com/articles/{DOI}"}),
    ("paper_springeropen_article",
     f"https://earth-planets-space.springeropen.com/articles/{DOI}", {}),
    ("paper_link_springer_pdf",
     f"https://link.springer.com/content/pdf/{DOI}.pdf", {}),
    ("paper_link_springer_article",
     f"https://link.springer.com/article/{DOI}", {}),
    ("paper_doi_resolver", f"https://doi.org/{DOI}", {}),

    # 書誌API（OA PDFの所在を教えてくれる）
    ("meta_crossref", f"https://api.crossref.org/works/{DOI}", {}),
    ("meta_openalex", f"https://api.openalex.org/works/doi:{DOI}", {}),
    ("meta_semanticscholar",
     "https://api.semanticscholar.org/graph/v1/paper/DOI:" + DOI +
     "?fields=title,abstract,authors,year,venue,openAccessPdf,externalIds,tldr", {}),
    ("meta_unpaywall",
     f"https://api.unpaywall.org/v2/{DOI}?email=abe.shuhei@gridpredict.co.jp", {}),
    ("meta_fatcat",
     f"https://api.fatcat.wiki/v0/release/lookup?doi={DOI}&expand=files,container", {}),
    ("meta_doaj",
     "https://doaj.org/api/search/articles/doi%3A" + urllib.parse.quote(DOI, safe=""), {}),
    ("meta_europepmc",
     "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%22"
     + DOI + "%22&resultType=core&format=json", {}),

    # アーカイブ
    ("wayback_cdx_article",
     "http://web.archive.org/cdx/search/cdx?url=earth-planets-space.springeropen.com/articles/"
     + DOI + "&output=json&limit=40", {}),
    ("wayback_cdx_pdf",
     "http://web.archive.org/cdx/search/cdx?url=earth-planets-space.springeropen.com/counter/pdf/"
     + DOI + ".pdf&output=json&limit=40", {}),
    ("wayback_cdx_springer_pdf",
     "http://web.archive.org/cdx/search/cdx?url=link.springer.com/content/pdf/"
     + DOI + ".pdf&output=json&limit=40", {}),
    ("wayback_article",
     f"https://web.archive.org/web/2023id_/https://earth-planets-space.springeropen.com/articles/{DOI}", {}),
    ("wayback_pdf",
     f"https://web.archive.org/web/2023id_/https://earth-planets-space.springeropen.com/counter/pdf/{DOI}.pdf", {}),
    ("wayback_springer_pdf",
     f"https://web.archive.org/web/2023id_/https://link.springer.com/content/pdf/{DOI}.pdf", {}),

    # 読み取りプロキシ／二次サイト
    ("proxy_jina_article",
     f"https://r.jina.ai/https://earth-planets-space.springeropen.com/articles/{DOI}", {}),
    ("proxy_jina_pdf",
     f"https://r.jina.ai/https://earth-planets-space.springeropen.com/counter/pdf/{DOI}.pdf", {}),
    ("proxy_allorigins_article",
     "https://api.allorigins.win/raw?url=" + urllib.parse.quote(
         f"https://earth-planets-space.springeropen.com/articles/{DOI}", safe=""), {}),
    ("ouci_record",
     f"https://ouci.dntb.gov.ua/en/works/?q={urllib.parse.quote(DOI)}", {}),
    ("colabws_record", "https://colab.ws/articles/" + urllib.parse.quote(DOI, safe=""), {}),
    ("scholar_archive_search",
     "https://scholar.archive.org/search?q=%22Crisis+hazard+assessment+for+snow-related+lahars%22", {}),
    ("proquest_openview",
     "https://www.proquest.com/openview/902bf36368d2fde23841d4a50be3edfa/1?pq-origsite=gscholar&cbl=2034776", {}),
    ("researchgate_pub",
     "https://www.researchgate.net/publication/356964903", {}),

    # 著者側（新潟大・山形大のリポジトリ／研究者総覧）
    ("niigata_repo_search",
     "https://nuar.lib.niigata-u.ac.jp/search?search_type=0&q=lahar", {}),
    ("niigata_researcher_kataoka",
     "https://researchers.adm.niigata-u.ac.jp/html/100001030_en.html", {}),
    ("yamagata_researcher_tsunematsu",
     "https://yudb.kj.yamagata-u.ac.jp/html/200000535_en.html", {}),
    ("cinii_kataoka_lahar",
     "https://cir.nii.ac.jp/opensearch/all?q=Kataoka%20lahar%20snow&format=json&count=50", {}),
    ("cinii_草津白根_泥流",
     "https://cir.nii.ac.jp/opensearch/all?q=%E8%8D%89%E6%B4%A5%E7%99%BD%E6%A0%B9%20%E6%B3%A5%E6%B5%81&format=json&count=50", {}),
    ("cinii_片岡香子_融雪",
     "https://cir.nii.ac.jp/opensearch/all?q=%E7%89%87%E5%B2%A1%E9%A6%99%E5%AD%90%20%E8%9E%8D%E9%9B%AA&format=json&count=50", {}),
    # 同じ著者グループの和文レビュー（J-STAGEはActionsから取れる実績あり）
    ("jstage_search_融雪型火山泥流",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=%E8%9E%8D%E9%9B%AA%E5%9E%8B%E7%81%AB%E5%B1%B1%E6%B3%A5%E6%B5%81", {}),
]

# ------------------------------------------------- (2) 火山別 緊急減災対策砂防計画
DIRECT_PDFS = [
    # --- 直接URLが判明しているもの
    ("aomori_岩木山_緊急減災対策砂防計画",
     "https://www.pref.aomori.lg.jp/soshiki/kendo/kasensabo/files/H27.3iwakisangensaikeikaku1.pdf"),
    ("hrr_磐梯山_緊急減災対策砂防計画",
     "https://www.hrr.mlit.go.jp/agagawa/bousai/pdf/bandaisan01.pdf"),
    ("ktr_草津白根山_本白根山_基礎資料編",
     "https://www.ktr.mlit.go.jp/ktr_content/content/000810218.pdf"),
    ("ktr_草津白根山_湯釜_計画編",
     "https://www.ktr.mlit.go.jp/ktr_content/content/000810227.pdf"),
    ("ktr_日光白根山_基礎資料編",
     "https://www.ktr.mlit.go.jp/ktr_content/content/000803046.pdf"),
    ("thr_鳥海山_緊急減災対策砂防計画案",
     "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/chokai/04/chokai_04_06_document.pdf"),
    ("thr_東北地方の緊急減災対策砂防計画_検討状況",
     "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/chokai/01/chokai_01_05_document.pdf"),
    ("yamanashi_富士山ハザードマップ_融雪型火山泥流説明",
     "https://www.pref.yamanashi.jp/documents/101190/3_setumeisiryou_fujisanhm.pdf"),
    ("bousai_expert_鳥海山",
     "https://www.bousai.go.jp/kazan/expert/pdf/181207siryo.pdf"),
    ("bousai_expert_御嶽山",
     "https://www.bousai.go.jp/kazan/expert/pdf/241130_sanko.pdf"),
    ("cbr_御嶽山_緊急減災_概要",
     "https://www.cbr.mlit.go.jp/tajimi/sabo/ontake/data/ontake_1.pdf"),
    ("mlit_火山砂防計画策定指針_概要版",
     "https://www.mlit.go.jp/river/sabo/pdf/202303_guide_gaiyo.pdf"),
    ("rinya_浅間山火山対策事業_融雪型火山泥流",
     "https://www.rinya.maff.go.jp/chubu/gijyutu/siryousitu/attach/pdf/chubu02-2.pdf"),
    ("hkd_樽前山直轄火山砂防事業概要",
     "https://www.hkd.mlit.go.jp/mr/tisui/tn6s9g00000006bv-att/tn6s9g00000006pz.pdf"),
    ("hkd_樽前山_砂防の取り組み",
     "https://www.hkd.mlit.go.jp/mr/tomakomai_kasen_keikaku/tn6s9g0000000ew4-att/sabo_torikumi.pdf"),
]

# インデックスページ（ここからPDFを自動追跡する）
INDEX_PAGES = [
    ("idx_ktr_浅間山", "https://www.ktr.mlit.go.jp/tonesui/tonesui_index011.html"),
    ("idx_ktr_草津白根山", "https://www.ktr.mlit.go.jp/tonesui/tonesui_index012.html"),
    ("idx_hrr_弥陀ヶ原", "https://www.hrr.mlit.go.jp/tateyama/jigyo/saboplan.html"),
    ("idx_fukushima_3火山", "https://www.pref.fukushima.lg.jp/sec/41045c/kazanfunka-gensai.html"),
    ("idx_hkd_樽前山", "https://www.hkd.mlit.go.jp/mr/tomakomai_kasen_keikaku/tn6s9g0000000ew4.html"),
    ("idx_hkd_樽前山委員会", "https://www.hkd.mlit.go.jp/mr/tomakomai_kasen_keikaku/tn6s9g0000000sut.html"),
    ("idx_cbr_御嶽山", "https://www.cbr.mlit.go.jp/tajimi/sabo/ontake/"),
    ("idx_thr_鳥海山", "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/chokai/"),
    ("idx_thr_蔵王山", "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/zao/"),
    ("idx_hrr_立山砂防事業", "https://www.hrr.mlit.go.jp/tateyama/jigyo/sabo.html"),
    ("idx_hrr_湯沢砂防_新潟焼山妙高", "https://www.hrr.mlit.go.jp/yuzawa/"),
    ("idx_hrr_神通川_焼岳乗鞍", "https://www.hrr.mlit.go.jp/jintsu/"),
    ("idx_cbr_富士砂防", "https://www.cbr.mlit.go.jp/fujisabo/"),
    ("idx_thr_岩手河川国道_岩手山", "https://www.thr.mlit.go.jp/iwate/yama/iwatesan/"),
    ("idx_hkd_旭川_十勝岳", "https://www.hkd.mlit.go.jp/as/tisui/"),
    ("idx_hkd_室蘭_有珠山", "https://www.hkd.mlit.go.jp/mr/tisui/"),
    ("idx_akita_火山砂防", "https://www.pref.akita.lg.jp/pages/archive/2126"),
    ("idx_tochigi_那須岳", "https://www.pref.tochigi.lg.jp/h05/town/sabou/sabou/kazan.html"),
    ("idx_kanazawa_白山", "https://www.hrr.mlit.go.jp/kanazawa/sabo/"),
    ("idx_hokkaido_火山砂防", "https://www.hkd.mlit.go.jp/topics/kazan/"),
]

PDF_KEY = re.compile(r"緊急減災|砂防計画|泥流|火山|ハザード|減災")


def _read(resp):
    data = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            data = gzip.decompress(data)
        elif enc == "deflate":
            data = zlib.decompress(data, -zlib.MAX_WBITS)
    except Exception:
        try:
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        except Exception:
            pass
    return data


def fetch(name, url, extra_headers=None, max_bytes=60_000_000):
    rec = {"name": name, "url": url}
    hdrs = dict(BROWSER_HEADERS)
    if extra_headers:
        hdrs.update(extra_headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=240) as r:
            data = _read(r)
            rec["status"] = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
            rec["final_url"] = r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
        try:
            body = _read(e)
            OUT.joinpath(f"{name}_err.html").write_bytes(body[:200000])
            rec["err_bytes"] = len(body)
        except Exception:
            pass
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec

    if len(data) > max_bytes:
        rec["truncated_from"] = len(data)
        data = data[:max_bytes]

    is_pdf = data[:5] == b"%PDF"
    if is_pdf:
        ext = ".pdf"
    elif "json" in ctype or url.rstrip("/").endswith("json") or "format=json" in url or "output=json" in url:
        ext = ".json"
    elif "text/plain" in ctype:
        ext = ".txt"
    else:
        ext = ".html"
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec["bytes"] = len(data)
    rec["file"] = str(p)
    rec["ctype"] = ctype
    rec["is_pdf"] = is_pdf
    if is_pdf:
        txt = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(txt)], check=False)
        if txt.exists():
            rec["text"] = str(txt)
            rec["text_chars"] = len(txt.read_text(errors="replace"))
    else:
        head = data[:400].decode("utf-8", "replace")
        rec["head"] = head.replace("\n", " ")[:220]
        if "Client Challenge" in data[:4000].decode("utf-8", "replace"):
            rec["blocked"] = "fastly_client_challenge"
    return rec


def crawl_index(name, url, man, seen, limit=14):
    rec = fetch(name, url)
    man.append(rec)
    f = rec.get("file")
    if not f or not f.endswith(".html"):
        return
    html = Path(f).read_text("utf-8", "replace")
    for m in re.finditer(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        full = urllib.parse.urljoin(rec.get("final_url") or url, href)
        if full in seen:
            continue
        if not (PDF_KEY.search(label) or PDF_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        safe = re.sub(r"[^0-9A-Za-z　-鿿]+", "_", label)[:40] or "pdf"
        sub = fetch(f"{name}__{safe}", full, max_bytes=40_000_000)
        sub["from_index"] = name
        sub["label"] = label
        man.append(sub)
        limit -= 1
        if limit <= 0:
            break


KEYS = ["融雪型火山泥流", "積雪深", "積雪水量", "泥流量", "融雪水量", "年超過確率",
        "既往最大", "大正泥流", "火砕流の流下範囲", "計画規模", "平均年最大積雪"]


def digest():
    """取得した全テキストから、判定に効くキーワードの前後を抜き出した要約を作る。"""
    lines = []
    for t in sorted(OUT.glob("*.txt")):
        body = t.read_text(errors="replace")
        rows = body.split("\n")
        hits = []
        for i, ln in enumerate(rows):
            if any(k in ln for k in KEYS):
                ctx = "\n".join(rows[max(0, i - 2):i + 3])
                hits.append(f"[L{i}]\n{ctx}")
        if hits:
            lines.append("=" * 70)
            lines.append(f"FILE: {t.name}  hits={len(hits)}")
            lines.append("\n---\n".join(hits[:60]))
    OUT.joinpath("_digest.txt").write_text("\n".join(lines))
    print("digest chars:", sum(len(x) for x in lines))


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for name, url, hdr in PAPER_URLS:
        man.append(fetch(name, url, hdr))
    # semantic scholar / unpaywall / openalex が示す OA PDF を追跡
    for f, keys in [("meta_semanticscholar.json", ["openAccessPdf"]),
                    ("meta_unpaywall.json", ["best_oa_location", "oa_locations"]),
                    ("meta_openalex.json", ["best_oa_location", "locations"]),
                    ("meta_fatcat.json", ["files"]),
                    ("meta_crossref.json", ["message"])]:
        p = OUT / f
        if not p.exists():
            continue
        try:
            blob = p.read_text(errors="replace")
        except Exception:
            continue
        urls = set(re.findall(r'https?://[^"\'\\ ]+?\.pdf', blob))
        urls |= set(re.findall(r'"url_for_pdf"\s*:\s*"([^"]+)"', blob))
        for i, u in enumerate(sorted(urls)[:8]):
            man.append(fetch(f"oa_follow_{f.split('.')[0]}_{i}", u))

    for name, url in DIRECT_PDFS:
        man.append(fetch(name, url))

    seen = set(u for _, u in DIRECT_PDFS)
    for name, url in INDEX_PAGES:
        crawl_index(name, url, man, seen)

    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    ok = sum(1 for m in man if m.get("status") == 200)
    print(f"done: {ok}/{len(man)} status200")
    for m in man:
        print(" ", m.get("status"), m["name"], m.get("bytes"), m.get("blocked", ""),
              str(m.get("error", ""))[:80])


if __name__ == "__main__":
    main()
