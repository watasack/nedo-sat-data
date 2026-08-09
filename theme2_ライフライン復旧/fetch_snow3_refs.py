#!/usr/bin/env python3
"""第7ラウンド死因潰し 第3バッチ。

(1) EPS草津白根2018論文（DOI 10.1186/s40623-021-01522-0）の本文を、
    第2バッチで落ちた経路の代わりに、検索エンジンHTML・OA集約API・機関リポジトリから取りに行く。
(2) 積雪火山の「火山噴火緊急減災対策砂防計画」の直URLを追加取得し、
    融雪型火山泥流の泥流量の設定方法（実績固定 / 火砕流流下範囲×融雪水量）を分類する。

出力先は snow_refs3/。トリガ: trigger-fetch-snow3 ブランチへの push
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

OUT = Path("snow_refs3")
DOI = "10.1186/s40623-021-01522-0"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

Q = [
    '"Crisis hazard assessment for snow-related lahars" Kusatsu-Shirane pdf',
    '"linear relationship" "SWE" altitude Kusatsu-Shirane Daisetsu Ontake Adatara Azuma',
    'Kataoka Tsunematsu Kusatsu-Shirane lahar 2021 snow water equivalent altitude pdf',
    '"s40623-021-01522-0" filetype:pdf',
]

PAPER = [
    # 検索エンジンHTML（スニペットから本文断片を拾う）
    *[(f"ddg_{i}", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q))
      for i, q in enumerate(Q)],
    *[(f"ddglite_{i}", "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(q))
      for i, q in enumerate(Q)],
    *[(f"bing_{i}", "https://www.bing.com/search?q=" + urllib.parse.quote(q))
      for i, q in enumerate(Q)],
    *[(f"mojeek_{i}", "https://www.mojeek.com/search?q=" + urllib.parse.quote(q))
      for i, q in enumerate(Q)],

    # OA集約・リポジトリ
    ("openaire", "https://api.openaire.eu/search/publications?doi=" + urllib.parse.quote(DOI)),
    ("irdb", "https://irdb.nii.ac.jp/api/opensearch?q=" + urllib.parse.quote("Kusatsu-Shirane lahar")),
    ("cinii_doi", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote(DOI) + "&format=json"),
    ("cinii_crisis", "https://cir.nii.ac.jp/opensearch/all?q=" +
     urllib.parse.quote("Crisis hazard assessment snow-related lahars") + "&format=json&count=20"),
    ("niigata_repo", "https://niigata-u.repo.nii.ac.jp/search?search_type=0&q=lahar"),
    ("niigata_repo_oai",
     "https://niigata-u.repo.nii.ac.jp/oai?verb=ListRecords&metadataPrefix=oai_dc&set=user-nhdr"),
    ("memento_timetravel",
     "http://timetravel.mementoweb.org/timemap/link/https://earth-planets-space.springeropen.com/articles/" + DOI),
    ("wayback_available",
     "http://archive.org/wayback/available?url=earth-planets-space.springeropen.com/articles/" + DOI),
    ("wayback_available_pdf",
     "http://archive.org/wayback/available?url=earth-planets-space.springeropen.com/counter/pdf/" + DOI + ".pdf"),
    # 出版社をもう一度、Accept を PDF 限定にして
    ("springer_pdf_acceptpdf", f"https://link.springer.com/content/pdf/{DOI}.pdf"),
    ("springeropen_pdf_download",
     f"https://earth-planets-space.springeropen.com/counter/pdf/{DOI}.pdf?download=true"),
]

# ---- (2) 火山別 緊急減災対策砂防計画（直URL）
VOLCANO_PDFS = [
    ("akita_秋田駒ヶ岳_緊急減災対策砂防計画",
     "https://www.thr.mlit.go.jp/yuzawa/17_sabou/kikikanri/akikoma/pdf/keikaku.pdf"),
    ("miyagi_栗駒山_緊急減災対策砂防計画_R5",
     "https://www.pref.miyagi.jp/documents/44643/keikaku1.pdf"),
    ("akita_秋田焼山_検討委員会資料",
     "https://www.pref.akita.lg.jp/uploads/public/archive_0000010024_00/"
     "%E7%AC%AC%EF%BC%95%E5%9B%9E%E6%A4%9C%E8%A8%8E%E5%A7%94%E5%93%A1%E4%BC%9A/"
     "5-03%EF%BC%8E%E3%80%90%E8%B3%87%E6%96%99%EF%BC%92%E3%80%91%E6%A4%9C%E8%A8%8E%E5%A7%94%E5%93%A1%E4%BC%9A%E8%B3%87%E6%96%99.pdf"),
    ("fuji_緊急減災_2章_現状",
     "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/2.pdf"),
    ("fuji_緊急減災_3章", "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/3.pdf"),
    ("fuji_緊急減災_4章", "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/4.pdf"),
    ("fuji_緊急減災_5章", "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/5.pdf"),
    ("fuji_緊急減災_6章", "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/6.pdf"),
    ("fuji_緊急減災_7章_緊急ハード",
     "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kinkyugensai/7.pdf"),
    ("cbr_富士砂防_富士山噴火対応ポスター",
     "https://www.cbr.mlit.go.jp/kikaku/2018kannai/pdf/pos17.pdf"),
]

VOLCANO_INDEX = [
    ("idx_aomori_八甲田山", "https://www.pref.aomori.lg.jp/soshiki/kendo/kasensabo/hakkoda-kazanfunka.html"),
    ("idx_aomori_岩木山", "https://www.pref.aomori.lg.jp/soshiki/kendo/kasensabo/iwaki-kazanfunka.html"),
    ("idx_niigata_新潟焼山", "https://www.pref.niigata.lg.jp/sec/sabo/1356905576261.html"),
    ("idx_akita_火山防災", "https://www.pref.akita.lg.jp/pages/archive/3032"),
    ("idx_cbr_富士砂防_火山砂防", "https://www.cbr.mlit.go.jp/fujisabo/bosai/bosaigaiyo/kazan-sabou.html"),
    ("idx_ktr_日光砂防_那須岳", "https://www.ktr.mlit.go.jp/nikko/"),
    ("idx_thr_湯沢_秋田駒", "https://www.thr.mlit.go.jp/yuzawa/01_kawa/kikikanri/akikoma/map.html"),
    ("idx_mlit_シリーズ日本の活火山", "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_sabo_seriesvolcano.html"),
    ("idx_mlit_火山噴火緊急減災対策検討会", "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_sabo_kazan.html"),
    ("idx_fukushima_火山防災マップ", "https://www.pref.fukushima.lg.jp/sec/16025b/kazanmap.html"),
    ("idx_hrr_金沢_白山", "https://www.hrr.mlit.go.jp/kanazawa/sabo/hakusan/index.html"),
    ("idx_hrr_神通川_焼岳", "https://www.hrr.mlit.go.jp/jintsu/kazan/index.html"),
    ("idx_hkd_旭川_十勝岳砂防", "https://www.hkd.mlit.go.jp/as/tisui/ho928l00000004oj.html"),
    ("idx_miyagi_栗駒山", "https://www.pref.miyagi.jp/soshiki/sabomizusi/kurikoma.html"),
    ("idx_miyagi_蔵王山", "https://www.pref.miyagi.jp/soshiki/sabomizusi/zaosan.html"),
    ("idx_tochigi_那須岳砂防", "https://www.pref.tochigi.lg.jp/h05/town/sabou/sabou/1216565774834.html"),
]

PDF_KEY = re.compile(r"緊急減災|砂防計画|泥流|火山|ハザード|減災|計画編|基礎")


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


def fetch(name, url, cap=50_000_000):
    rec = {"name": name, "url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=200) as r:
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
    ext = ".pdf" if pdf else (".json" if ("json" in ctype or "format=json" in url) else ".html")
    p = OUT / f"{name}{ext}"
    p.write_bytes(data)
    rec.update(bytes=len(data), file=str(p), ctype=ctype, is_pdf=pdf)
    if pdf:
        t = p.with_suffix(".txt")
        subprocess.run(["pdftotext", "-layout", str(p), str(t)], check=False)
        if t.exists():
            rec["text_chars"] = len(t.read_text(errors="replace"))
    else:
        s = data[:4000].decode("utf-8", "replace")
        if "Client Challenge" in s:
            rec["blocked"] = "fastly_client_challenge"
    return rec


def crawl(name, url, man, seen, limit=16):
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
        sub = fetch(f"{name}__{safe}", full, cap=40_000_000)
        sub.update(from_index=name, label=label)
        man.append(sub)
        limit -= 1
        if limit <= 0:
            break


KEYS = ["融雪型火山泥流", "積雪深", "積雪水量", "泥流量", "融雪水量", "年超過確率",
        "既往最大", "大正泥流", "火砕流の流下範囲", "平均年最大積雪", "泥流総量", "積雪量"]
EN_KEYS = ["snow water equivalent", "SWE", "altitude", "Daisetsu", "Adatara", "Azuma",
           "Ontake", "linear relationship", "snow survey", "lahar"]


def digest():
    out = []
    for t in sorted(OUT.glob("*.txt")):
        rows = t.read_text(errors="replace").split("\n")
        hits = [f"[L{i}]\n" + "\n".join(rows[max(0, i - 2):i + 3])
                for i, ln in enumerate(rows) if any(k in ln for k in KEYS)]
        if hits:
            out.append("=" * 70)
            out.append(f"FILE: {t.name} hits={len(hits)}")
            out.append("\n---\n".join(hits[:70]))
    OUT.joinpath("_digest_jp.txt").write_text("\n".join(out))

    out2 = []
    for h in sorted(OUT.glob("*.html")):
        s = h.read_text("utf-8", "replace")
        s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
        s = re.sub(r"<[^>]+>", " ", s)
        s = re.sub(r"\s+", " ", s)
        frag = [s[max(0, m.start() - 300):m.start() + 400]
                for m in re.finditer("|".join(EN_KEYS), s)]
        if frag:
            out2.append("=" * 70)
            out2.append(f"FILE: {h.name} hits={len(frag)}")
            out2.append("\n---\n".join(frag[:40]))
    OUT.joinpath("_digest_en.txt").write_text("\n".join(out2))


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for n, u in PAPER:
        man.append(fetch(n, u))
    # 検索結果HTMLから springeropen / pdf のリンクを拾って追跡
    pdfs = set()
    for h in OUT.glob("*.html"):
        s = h.read_text("utf-8", "replace")
        for m in re.finditer(r'https?://[^\s"\'<>]+?\.pdf', s):
            u = m.group(0).replace("&amp;", "&")
            if "40623" in u or "kusatsu" in u.lower() or "lahar" in u.lower():
                pdfs.add(u)
    for i, u in enumerate(sorted(pdfs)[:12]):
        man.append(fetch(f"paper_pdf_follow_{i}", u))

    for n, u in VOLCANO_PDFS:
        man.append(fetch(n, u))
    seen = set(u for _, u in VOLCANO_PDFS)
    for n, u in VOLCANO_INDEX:
        crawl(n, u, man, seen)

    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))
    for m in man:
        print(" ", m.get("status"), m["name"], m.get("bytes"), m.get("blocked", ""),
              str(m.get("error", ""))[:70])


if __name__ == "__main__":
    main()
