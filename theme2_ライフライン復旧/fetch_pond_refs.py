#!/usr/bin/env python3
"""農業用ため池「満杯度・管理放棄」案の殺し材料 一次資料取得スクリプト

狙い（優先順）:
  1. 型⑤ — ため池決壊の主因が水位かどうか（H30豪雨32か所の決壊要因の一次調査）
  2. 型③ — 先行研究（国内: 四国ため池DB改良 / 海外: small reservoir monitoring）
  3. 型② — ため池の規模分布（Sentinel-2 10m で何画素取れるか）
  4. 観測機会 — ため池密集地の Sentinel-2 雲量つきシーン在庫（STAC）

サンドボックスからは naro.go.jp / jstage / maff.go.jp などが egress 遮断されるため、
GitHub Actions 上で取得して pond-refs ブランチにコミットする。

トリガ: trigger-fetch-pond ブランチへの push
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("pond_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

URLS = [
    # ========== 型⑤: 決壊の要因（一次調査報告） ==========
    ("naro_H30ため池被災調査_広島01",
     "https://www.naro.go.jp/disaster/nishinihon201807/files/tameike_report_hiroshima01.pdf"),
    ("naro_H30ため池被災調査_広島02",
     "https://www.naro.go.jp/disaster/nishinihon201807/files/tameike_report_hiroshima02.pdf"),
    ("naro_H30ため池被災調査_岡山01",
     "https://www.naro.go.jp/disaster/nishinihon201807/files/tameike_report_okayama01.pdf"),
    ("naro_H30西日本豪雨_index",
     "https://www.naro.go.jp/disaster/nishinihon201807/index.html"),
    ("bousai_ため池対策の進め方_32件",
     "https://www.bousai.go.jp/fusuigai/suigai_dosyaworking/pdf/dai2kai/siryo1-3.pdf"),
    ("bousai_H30豪雨概要_WG1",
     "https://www.bousai.go.jp/fusuigai/suigai_dosyaworking/pdf/dai1kai/siryo2.pdf"),
    ("jstage_H30豪雨ため池決壊要因分析",
     "https://www.jstage.jst.go.jp/article/jjsidre/88/6/88_491/_article/-char/ja/"),
    ("landslide_福山ため池決壊速報",
     "https://japan.landslide-soc.org/branch/kansai/saigai/180801fukuyama_wang.pdf"),
    ("maff_H30豪雨等を踏まえた今後のため池対策の進め方",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/index-40.pdf"),

    # ========== 制度: 点検・優先順位の決まり方 ==========
    ("maff_ため池劣化状況評価等の手引き_1",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/tameike_hyouka-1.pdf"),
    ("maff_ため池管理保全法_index",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/tameike_kanri.html"),
    ("maff_ため池top",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/index.html"),
    ("maff_ため池データベース_公表",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/tameike_db.html"),
    ("naro_ため池防災支援システム",
     "https://www.naro.go.jp/laboratory/nire/contents/tameike/index.html"),
    ("naro_ため池水位管理情報システム",
     "https://www.naro.go.jp/publicity_report/press/laboratory/nire/158247.html"),

    # ========== 型②: 規模分布（何画素取れるか） ==========
    ("maff_ため池一斉点検結果",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/index-1.pdf"),
    ("hyogo_ためいけっとDB", "https://web.pref.hyogo.lg.jp/nk11/tameike.html"),
    ("hyogo_ため池監視システム導入マニュアル",
     "https://web.pref.hyogo.lg.jp/nk11/documents/manyuaru.pdf"),
    ("kagawa_ため池", "https://www.pref.kagawa.lg.jp/nochi/tameike/index.html"),
    ("hiroshima_ため池", "https://www.pref.hiroshima.lg.jp/soshiki/89/tameike.html"),

    # ========== 型③: 国内先行 ==========
    ("jstage_四国ため池DB改良_Sentinel2",
     "https://www.jstage.jst.go.jp/article/jshwr/38/0/38_112/_article/-char/ja/"),
    ("jstage_search_ため池_決壊_要因",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey="
     + urllib.parse.quote("ため池 決壊 要因")),
    ("jstage_search_ため池_水域面積_衛星",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey="
     + urllib.parse.quote("ため池 水域面積 衛星")),
    ("cinii_ため池_NDWI",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 NDWI")
     + "&format=json&count=50"),
    ("cinii_ため池_管理放棄",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 管理放棄")
     + "&format=json&count=50"),
    ("cinii_ため池_廃止",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 廃止 現状")
     + "&format=json&count=50"),
    ("cinii_ため池_決壊",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 決壊")
     + "&format=json&count=100"),
    ("cinii_水位_Sentinel",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("貯水池 水面積 衛星 時系列")
     + "&format=json&count=50"),
    ("cinii_渡部哲史", "https://cir.nii.ac.jp/opensearch/all?q="
     + urllib.parse.quote("渡部哲史 ため池") + "&format=json&count=50"),
    ("kaken_ため池_衛星_ja",
     "https://kaken.nii.ac.jp/ja/search/?qm=" + urllib.parse.quote("ため池 衛星")),
    ("kaken_ため池_リモセン_ja",
     "https://kaken.nii.ac.jp/ja/search/?qm=" + urllib.parse.quote("ため池 リモートセンシング")),

    # ========== 型③/④: 海外先行（small reservoir monitoring） ==========
    ("plos_indian_ungauged_small_reservoirs",
     "https://journals.plos.org/water/article?id=10.1371%2Fjournal.pwat.0000260"),
    ("crossref_small_reservoir_sentinel",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("small reservoir surface water area Sentinel monitoring")
     + "&rows=40&select=title,author,container-title,issued,DOI,abstract"),
    ("crossref_farm_pond_remote_sensing",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("farm pond tank water spread area remote sensing India")
     + "&rows=40&select=title,author,container-title,issued,DOI,abstract"),
    ("crossref_area_volume_small_water_bodies",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("area volume relationship small water bodies satellite storage estimation")
     + "&rows=40&select=title,author,container-title,issued,DOI,abstract"),
    ("crossref_dam_failure_risk_remote_sensing",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("earthen dam embankment failure risk InSAR remote sensing monitoring")
     + "&rows=40&select=title,author,container-title,issued,DOI,abstract"),
    ("crossref_sentinel2_small_water_body_minimum_size",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("minimum detectable size small water bodies Sentinel-2 mixed pixel water fraction")
     + "&rows=40&select=title,author,container-title,issued,DOI,abstract"),
    ("crossref_reservoir_abandonment_monitoring",
     "https://api.crossref.org/works?query.bibliographic="
     + urllib.parse.quote("abandoned reservoir pond detection satellite time series water occurrence")
     + "&rows=30&select=title,author,container-title,issued,DOI,abstract"),

    # ========== 特許（民間サービスの有無） ==========
    ("gpatents_tameike_kanri",
     "https://patents.google.com/xhr/query?url="
     + urllib.parse.quote("q=(ため池 水面 面積 衛星 判定)") + "&exp="),
    ("gpatents_reservoir_storage_satellite",
     "https://patents.google.com/xhr/query?url="
     + urllib.parse.quote("q=(reservoir storage estimation satellite water surface area)") + "&exp="),
]

# 観測機会: ため池密集地の Sentinel-2 在庫と雲量（平時トレンドが年何点作れるか）
_S2 = "sentinel-2-l2a"
_S1 = "sentinel-1-grd"
_URL = "https://earth-search.aws.element84.com/v1/search"


def _q(name, coll, bbox, start="2023-01-01T00:00:00Z", end="2025-01-01T00:00:00Z"):
    return {
        "name": name,
        "url": _URL,
        "body": {"collections": [coll], "bbox": bbox, "datetime": f"{start}/{end}",
                 "limit": 500},
    }


STAC_QUERIES = [
    # 東広島（H30豪雨で決壊が集中）
    _q("s2_東広島_2023-2024", _S2, [132.6, 34.3, 132.9, 34.6]),
    # 香川県（讃岐平野・ため池密度全国最大級）
    _q("s2_香川_2023-2024", _S2, [133.9, 34.15, 134.2, 34.35]),
    # 兵庫東播磨（ため池数 全国1位）
    _q("s2_東播磨_2023-2024", _S2, [134.8, 34.7, 135.1, 34.95]),
    # 大阪南部（泉南・和泉）
    _q("s2_大阪南部_2023-2024", _S2, [135.3, 34.3, 135.6, 34.5]),
    # SAR 側（雲に依存しない代替）
    _q("s1_東播磨_2023-2024", _S1, [134.8, 34.7, 135.1, 34.95]),
]


def fetch(name, url):
    rec = {"name": name, "url": url}
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/json,*/*",
                "Accept-Language": "ja,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
            rec["status"] = r.status
            ctype = r.headers.get("Content-Type", "")
        ext = ".pdf" if url.lower().endswith(".pdf") or "pdf" in ctype else (
            ".json" if "json" in ctype or "format=json" in url else ".html")
        p = OUT / f"{name}{ext}"
        p.write_bytes(data)
        rec["bytes"] = len(data)
        rec["file"] = str(p)
        if ext == ".pdf":
            txt = p.with_suffix(".txt")
            subprocess.run(["pdftotext", "-layout", str(p), str(txt)], check=False)
            if txt.exists():
                rec["text"] = str(txt)
                rec["text_chars"] = len(txt.read_text(errors="replace"))
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
        try:
            OUT.joinpath(f"{name}_err.html").write_bytes(e.read())
        except Exception:
            pass
    except Exception as e:
        rec["error"] = repr(e)
    return rec


def stac(q):
    rec = {"name": q["name"], "url": q["url"], "kind": "stac"}
    try:
        req = urllib.request.Request(
            q["url"],
            data=json.dumps(q["body"]).encode(),
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
        feats = d.get("features", [])
        rows = []
        for f in feats:
            p = f.get("properties", {})
            rows.append({
                "id": f.get("id"),
                "datetime": p.get("datetime"),
                "cloud": p.get("eo:cloud_cover"),
                "platform": p.get("platform"),
            })
        rows.sort(key=lambda x: x["datetime"] or "")
        rec["count"] = len(rows)
        for th in (10, 20, 40):
            rec[f"cloud_lt_{th}"] = sum(
                1 for x in rows if isinstance(x["cloud"], (int, float)) and x["cloud"] < th)
        p = OUT / f"stac_{q['name']}.json"
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        rec["file"] = str(p)
    except Exception as e:
        rec["error"] = repr(e)
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url in URLS:
        r = fetch(name, url)
        print(json.dumps(r, ensure_ascii=False))
        manifest.append(r)
    for q in STAC_QUERIES:
        r = stac(q)
        print(json.dumps(r, ensure_ascii=False))
        manifest.append(r)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1))
    ok = sum(1 for m in manifest
             if m.get("status") == 200 or m.get("count") is not None)
    print(f"OK {ok} / {len(manifest)}")


if __name__ == "__main__":
    main()
