#!/usr/bin/env python3
"""潮風害（塩害）×衛星の一次情報取得スクリプト（第5案の検証用）

GitHub Actions ランナー上で実行する想定。サンドボックスからは criepi.denken.or.jp /
link.springer.com / jma-net.go.jp などが egress 遮断されているため、
制限のない Actions で取得して salt-refs ブランチに置く。

加えて、Sentinel-2 / Landsat のシーン在庫を STAC API に直接問い合わせる
（「台風24号直後に晴天シーンが実在するか」を事実として決着させるため）。
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("salt_refs2")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

URLS = [
    # --- 電力中央研究所: 海塩粒子輸送シミュレーション（塩分付着量推定）シリーズ ---
    ("criepi_SS22016_その9_微地形", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=SS22016"),
    ("criepi_N19005_その8_砕波帯", "https://criepi.denken.or.jp/jp/kenkikaku/report/detail/N19005.html"),
    ("criepi_N10012_その5_海域の広さ", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=N10012"),
    ("criepi_N17003_鉄塔鋼管内部腐食", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=N17003"),
    ("criepi_H16004_がいし塩雪害", "https://www.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=H16004"),
    ("criepi_V17001_塩雪害気象条件", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=V17001"),
    ("criepi_検索_塩分付着", "https://criepi.denken.or.jp/hokokusho/pb/reportList?searchWord=" + urllib.parse.quote("塩分付着")),
    ("criepi_検索_塩害", "https://criepi.denken.or.jp/hokokusho/pb/reportList?searchWord=" + urllib.parse.quote("塩害")),
    ("criepi_検索_潮風害", "https://criepi.denken.or.jp/hokokusho/pb/reportList?searchWord=" + urllib.parse.quote("潮風害")),
    ("criepi_検索_リモートセンシング", "https://criepi.denken.or.jp/hokokusho/pb/reportList?searchWord=" + urllib.parse.quote("リモートセンシング")),
    # --- 気象庁: 台風24号の地方気象速報（時刻の一次情報） ---
    ("jma_choshi_台風24号千葉速報", "https://www.jma-net.go.jp/choshi/sokuhou/2018_24_taifuu.pdf"),
    ("jma_tokyo_台風24号管区速報", "https://www.jma-net.go.jp/tokyo/sub_index/bosai/disaster/ty1824/ty1824_kanku.pdf"),
    # --- 消防庁・内閣府: 台風24号被害報 ---
    ("fdma_台風24号第8報", "https://www.fdma.go.jp/disaster/info/assets/post1078.pdf"),
    ("bousai_台風24号被害状況", "https://www.bousai.go.jp/updates/h30typhoon24/pdf/h30typhoon24_14.pdf"),
    # --- 経産省 電力安全小委: 平成30年の電気事故（塩害停電の公式記録があるか） ---
    ("meti_denryoku_anzen_h30事故", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/pdf/018_03_00.pdf"),
    ("meti_denryoku_anzen_index", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/index.html"),
    # --- 東京電力PG: 停電・塩害関連 ---
    ("tepco_press_2018_10", "https://www.tepco.co.jp/pg/newsroom/press/2018.html"),
    # --- 論文: 衛星による塩害評価（先行事例の核） ---
    ("springer_salinity_crops_japan", "https://link.springer.com/article/10.1007/s11069-014-1465-0"),
    ("springer_salinity_crops_japan_ris", "https://citation-needed.springer.com/v2/references/10.1007/s11069-014-1465-0?format=refman&flavour=citation"),
    # --- J-STAGE / CiNii 検索: 潮風害・塩害のリモセン先行 ---
    ("jstage_search_潮風害", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("潮風害")),
    ("jstage_search_潮風害リモセン", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("潮風害 リモートセンシング")),
    ("jstage_search_塩害衛星", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("塩害 衛星画像")),
    ("cinii_潮風害", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("潮風害") + "&format=json&count=100"),
    ("cinii_潮風害リモセン", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("潮風害 リモートセンシング") + "&format=json&count=50"),
    ("cinii_飛来塩分", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("飛来塩分") + "&format=json&count=100"),
    ("cinii_がいし_塩分付着", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("がいし 塩分付着量") + "&format=json&count=100"),
    # --- 山本晴彦の潮風害シリーズ（褐変の時間スケールの一次情報） ---
    ("jstage_yamamoto_2006b", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("山本晴彦 潮風害 水稲")),
    ("jsnds_37_4_index", "https://www.jsnds.org/ssk/ssk_37_4.html"),
    # --- 特許 ---
    ("gpatents_塩害予測衛星", "https://patents.google.com/xhr/query?url=" + urllib.parse.quote("q=(塩害 予測 衛星画像)") + "&exp="),
    ("gpatents_がいし汚損監視", "https://patents.google.com/xhr/query?url=" + urllib.parse.quote("q=(がいし 汚損 監視 遠隔)") + "&exp="),
    ("gpatents_salt_contamination_insulator", "https://patents.google.com/xhr/query?url=" + urllib.parse.quote("q=(insulator contamination satellite prediction)") + "&exp="),
    # --- 鉄道総研: 塩害・がいし ---
    ("rtri_search_塩害", "https://www.rtri.or.jp/search/?q=" + urllib.parse.quote("塩害")),
    # --- 各電力の技術開発（塩害・洗浄） ---
    ("chuden_技術開発", "https://www.chuden.co.jp/energy/ene_research/"),
    ("tepco_研究所", "https://www.tepco.co.jp/rd/index-j.html"),
    # --- 気象研究/農業: 潮風害の被害発現時間 ---
    ("naro_潮風害", "https://www.naro.go.jp/search/index.html?q=" + urllib.parse.quote("潮風害")),
    ("chiba_農林_塩害対策", "https://www.pref.chiba.lg.jp/lab-nourin/index.html"),
]

# STAC で衛星シーンの在庫を直接確認する
STAC_QUERIES = [
    # 台風24号（2018/9/30-10/1 通過）直後の関東沿岸 Sentinel-2
    {
        "name": "s2_台風24号後_千葉",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [139.7, 35.0, 140.9, 36.1],
            "datetime": "2018-09-20T00:00:00Z/2018-10-25T00:00:00Z",
            "limit": 100,
        },
    },
    # 静岡・浜松側
    {
        "name": "s2_台風24号後_静岡西部",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [137.5, 34.5, 138.6, 35.2],
            "datetime": "2018-09-20T00:00:00Z/2018-10-25T00:00:00Z",
            "limit": 100,
        },
    },
    # 令和元年台風15号（2019/9/9 房総上陸）
    {
        "name": "s2_台風15号後_千葉",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [139.7, 34.9, 140.9, 36.0],
            "datetime": "2019-09-01T00:00:00Z/2019-10-10T00:00:00Z",
            "limit": 100,
        },
    },
    # Landsat 8 の同時期（比較用）
    {
        "name": "l8_台風24号後_千葉",
        "url": "https://landsatlook.usgs.gov/stac-server/search",
        "body": {
            "collections": ["landsat-c2l2-sr"],
            "bbox": [139.7, 35.0, 140.9, 36.1],
            "datetime": "2018-09-20T00:00:00Z/2018-10-25T00:00:00Z",
            "limit": 100,
        },
    },
]



URLS = [
    ("criepi_SS25001_Sentinel2倒木推定", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=SS25001"),
    ("criepi_N15007_その7_日本域飛来海塩", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=N15007"),
    ("criepi_N11011_海塩濃度予測", "https://criepi.denken.or.jp/hokokusho/pb/reportDetail?reportNoUkCode=N11011"),
    ("criepi_研究報告検索_衛星", "https://criepi.denken.or.jp/result/report/?q=" + urllib.parse.quote("衛星")),
    ("jma_災害時自然現象報告書2018台風24", "https://ds.data.jma.go.jp/stats/data/bosai/report/2018/20181011/20181011.html"),
    ("jma_東京管区速報_台風24", "https://www.data.jma.go.jp/stats/data/bosai/report/2018/20181011/pdf/2018_5_tokyo_1.pdf"),
    ("jstage_カンキツ潮風害防止技術", "https://www.jstage.jst.go.jp/article/agrmet1943/29/1/29_1_41/_pdf"),
    ("jstage_風倒木と電柱損壊_再取得", "https://www.jstage.jst.go.jp/article/jfsc/131/0/131_176/_pdf/-char/ja"),
    ("jstage_search_潮風害予測", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("潮風害 予測 モデル")),
    ("jstage_search_飛来塩分衛星", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("飛来塩分 衛星")),
    ("cinii_塩害_衛星", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("塩害 衛星") + "&format=json&count=100"),
    ("cinii_潮風害_衛星", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("潮風害 衛星画像") + "&format=json&count=100"),
    ("cinii_海塩_リモートセンシング", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("海塩 リモートセンシング") + "&format=json&count=100"),
    ("kaken_潮風害", "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("潮風害") + "&format=json"),
    ("kaken_塩害_衛星", "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("塩害 衛星") + "&format=json"),
    ("chiba_台風24号農林水産被害", "https://www.pref.chiba.lg.jp/annou/press/2018/documents/1015-2.pdf"),
    ("shizuoka_台風24号被害", "https://www.pref.shizuoka.jp/kurashikankyo/shobobosai/bosai/1006331/1006338/index.html"),
    ("tepco_teiden_rireki", "https://teideninfo.tepco.co.jp/day/teiden/index-j.html"),
    ("chuden_塩害", "https://www.chuden.co.jp/search/?q=" + urllib.parse.quote("塩害")),
    ("denken_年報_塩害", "https://criepi.denken.or.jp/result/event/lecture/"),
]

STAC_QUERIES = []


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
            subprocess.run(["pdftotext", "-layout", str(p), str(txt)], check=True)
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
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        feats = d.get("features", [])
        rows = []
        for f in feats:
            p = f.get("properties", {})
            rows.append({
                "id": f.get("id"),
                "datetime": p.get("datetime"),
                "cloud": p.get("eo:cloud_cover"),
                "tile": p.get("grid:code") or p.get("landsat:wrs_path"),
            })
        rows.sort(key=lambda x: (x["datetime"] or ""))
        OUT.joinpath(f"{q['name']}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1))
        rec["n"] = len(rows)
        rec["file"] = f"salt_refs/{q['name']}.json"
    except Exception as e:
        rec["error"] = repr(e)
    return rec


def main():
    OUT.mkdir(exist_ok=True)
    man = [fetch(n, u) for n, u in URLS]
    man += [stac(q) for q in STAC_QUERIES]
    OUT.joinpath("manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1))
    for r in man:
        print(r.get("status", r.get("n", "-")), r["name"], r.get("error", ""))


if __name__ == "__main__":
    main()
