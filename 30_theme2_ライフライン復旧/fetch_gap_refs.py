#!/usr/bin/env python3
"""「所管の隙間」＝誰も実態を把握していない量 の一次資料取得スクリプト（第5ラウンド）

狙い: 会計検査院・総務省行政評価局・各省の検討会資料から
「実態を把握していない」「台帳が整備されていない」「調査が及んでいない」
「所管が明確でない」という記述を原文で押さえる。

サンドボックスからは soumu.go.jp / jbaudit.go.jp / maff.go.jp などが egress 遮断
されているため、GitHub Actions 上で取得して gap-refs ブランチにコミットする。

トリガ: trigger-fetch-gap ブランチへの push
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("gap_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

URLS = [
    # ================= 総務省 行政評価局 =================
    ("soumu_ため池防災減災調査_R6", "https://www.soumu.go.jp/main_content/000953733.pdf"),
    ("soumu_ため池防災減災調査_通知概要", "https://www.soumu.go.jp/menu_news/s-news/hyouka_240621000174807.html"),
    ("soumu_農業用ため池管理保全_中部管区R3", "https://www.soumu.go.jp/main_content/000763910.pdf"),
    ("soumu_河川管理_関東管区H30", "https://www.soumu.go.jp/main_content/000530278.pdf"),
    ("soumu_農業水利施設保全管理_H25", "https://www.soumu.go.jp/main_content/000250199.pdf"),
    ("soumu_農道林道維持管理の実態", "https://www.soumu.go.jp/main_content/000687357.pdf"),
    ("soumu_農道橋林道橋長寿命化勧告", "https://www.soumu.go.jp/main_content/000053269.pdf"),
    ("soumu_建設残土対策実態調査_R3", "https://www.soumu.go.jp/main_content/000783153.pdf"),
    ("soumu_土砂災害対策勧告", "https://www.soumu.go.jp/main_content/000487037.pdf"),
    ("soumu_農業分野災害復旧迅速化_R3", "https://www.soumu.go.jp/main_content/000783328.pdf"),
    ("soumu_国直轄河川管理_九州管区H26", "https://www.soumu.go.jp/main_content/000317896.pdf"),
    ("soumu_河川管理施設の現状", "https://www.soumu.go.jp/main_content/000145000.pdf"),
    ("soumu_太陽光発電設備導入調査_勧告R6", "https://www.soumu.go.jp/menu_news/s-news/hyouka_240326000172382.html"),
    ("soumu_行政運営改善調査_index", "https://www.soumu.go.jp/main_sosiki/hyouka/hyouka_kansi_n/index.html"),
    ("soumu_行政評価_お知らせ一覧", "https://www.soumu.go.jp/main_sosiki/hyouka/hyouka_kansi_n/76785.html"),
    ("soumu_行政評価局_新着一覧", "https://www.soumu.go.jp/main_sosiki/hyouka/snews_back.html"),
    ("soumu_上下水道地震対策現状_R6", "https://www.soumu.go.jp/main_content/000968722.pdf"),
    ("soumu_水道事業現状_R7", "https://www.soumu.go.jp/main_content/001022598.pdf"),

    # ================= 会計検査院 =================
    ("jbaudit_土砂災害対策随時報告H26", "https://report.jbaudit.go.jp/org/h26/ZUIJI2/2014-h26-Z2008-0.htm"),
    ("jbaudit_災害関連情報システム随時報告H29", "https://report.jbaudit.go.jp/org/h29/ZUIJI2/2017-h29-Z2018-0.htm"),
    ("jbaudit_R6決算検査報告_国交省", "https://www.jbaudit.go.jp/report/new/all/ch3_p1_12.html"),
    ("jbaudit_R6決算検査報告_農水省", "https://www.jbaudit.go.jp/report/new/all/ch3_p1_10.html"),
    ("jbaudit_R6決算検査報告_経産省", "https://www.jbaudit.go.jp/report/new/all/ch3_p1_11.html"),
    ("jbaudit_R6決算検査報告_環境省", "https://www.jbaudit.go.jp/report/new/all/ch3_p1_13.html"),
    ("jbaudit_検査報告目次一覧", "https://report.jbaudit.go.jp/org/houkoku-mokuji-list.htm"),
    ("jbaudit_検索_把握していない",
     "https://report.jbaudit.go.jp/search.php?SEARCH_TEXT=" + urllib.parse.quote("実態を把握していない")),
    ("jbaudit_検索_台帳整備",
     "https://report.jbaudit.go.jp/search.php?SEARCH_TEXT=" + urllib.parse.quote("台帳が整備されていない")),

    # ================= 農林水産省: ため池 =================
    ("maff_ため池を巡る状況_R6", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/hozenhou-44.pdf"),
    ("maff_ため池管理保全施策点検検証結果", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/tameike_iinkai-59.pdf"),
    ("maff_ため池を巡る状況_委員会31", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/tameike_iinkai-31.pdf"),
    ("maff_防災重点ため池都道府県別箇所数", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/koujitokusohou-35.pdf"),
    ("maff_ため池法概要", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/hozenhou-1.pdf"),
    ("maff_ため池洪水調節機能強化の手引き", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/zirei-22.pdf"),
    ("maff_ため池劣化状況評価の手引き", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/index-77.pdf"),
    ("maff_ため池都道府県別対応状況", "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/tameike_taiou.html"),
    ("maff_豪雨渇水の備え_ため池編", "https://www.maff.go.jp/j/nousin/kantai/tekiou/pdf/tameike_sankou.pdf"),
    ("maff_農地違反転用_衛星監視", "https://www.maff.go.jp/j/nousin/noukei/totiriyo/attach/pdf/ihan_tenyo-1.pdf"),

    # ================= 国土交通省 =================
    ("mlit_海岸管理のあり方_現状", "https://www.mlit.go.jp/river/shinngikai_blog/kaigankanrinoarikata/dai01kai/dai01kai_siryou2.pdf"),
    ("mlit_既存盛土調査の考え方", "https://www.mlit.go.jp/toshi/web/content/001491075.pdf"),
    ("mlit_盛土規制法の概要", "https://www.mlit.go.jp/toshi/web/content/001490955.pdf"),
    ("mlit_盛土等安全対策推進ガイドライン", "https://www.mlit.go.jp/toshi/web/content/001611604.pdf"),
    ("mlit_中小河川点検要領R6", "https://www.mlit.go.jp/river/shishin_guideline/kasen/pdf/02_chusyou_tenkenyoukou.pdf"),
    ("mlit_大規模盛土造成地経過観察マニュアル", "https://www.mlit.go.jp/toshi/content/001711369.pdf"),
    ("mlit_大規模盛土造成地防災対策検討会参考", "https://www.mlit.go.jp/toshi/web/content/001332381.pdf"),
    ("mlit_建設発生土搬出先の明確化", "https://www.mlit.go.jp/totikensangyo/const/content/001499462.pdf"),
    ("mlit_建設発生土搬出先計画制度", "https://www.mlit.go.jp/tochi_fudousan_kensetsugyo/const/tochi_fudousan_kensetsugyo_const_fr1_000001_00041.html"),
    ("mlit_砂防関係施設点検要領R7", "https://www.mlit.go.jp/river/shishin_guideline/sabo/sabo_tenkenyouryou_202504.pdf"),
    ("mlit_砂防関係施設長寿命化ガイドライン", "https://www.mlit.go.jp/river/shishin_guideline/sabo/sabo_choujumyou_guideline_202203.pdf"),
    ("nilim_衛星データ利用の現状と課題", "https://www.nilim.go.jp/lab/bcg/siryou/eiseireport/no1/1-1.pdf"),
    ("nilim_砂防施設の維持修繕技術", "https://www.nilim.go.jp/lab/bcg/siryou/tnn/tnn0516pdf/ks051606.pdf"),

    # ================= 内閣府・防災 =================
    ("bousai_孤立集落FU調査H26", "https://www.bousai.go.jp/jishin/chihou/pdf/20141022-koritsuhoukokusyo.pdf"),
    ("bousai_孤立可能性集落の推計H17", "https://www.bousai.go.jp/kohou/oshirase/h17/pdf/050629shiryou2-1.pdf"),
    ("bousai_盛土災害防止_建設発生土", "https://www.bousai.go.jp/kaigirep/kentokai/moridosaigai/pdf/siryo4.pdf"),
    ("cao_衛星データ利用拡大_R7", "https://www8.cao.go.jp/space/taskforce/rs/dai4/siryou1-9.pdf"),
    ("cao_衛星リモセンTF取組状況", "https://www8.cao.go.jp/space/comittee/01-kihon/kihon-dai24/siryou1_5.pdf"),

    # ================= 環境省・経産省（地盤沈下・鉱山） =================
    ("env_地盤沈下概況_H29", "https://www.env.go.jp/water/jiban/gaikyo/gaikyo29.pdf"),
    ("env_地盤沈下_index", "https://www.env.go.jp/water/jiban/"),
    ("env_鉱害防止施策", "https://www.env.go.jp/council/content/i_07/900427633.pdf"),
    ("jaea_鉱さいたい積場措置", "https://www.jaea.go.jp/04/zningyo/kou23-03.pdf"),

    # ================= 林野庁 =================
    ("rinya_治山施設個別施設計画マニュアル", "https://www.rinya.maff.go.jp/j/tisan/tisan/pdf/shisetukeikakumanyuaru.pdf"),
    ("rinya_治山施設長寿命化H29改定", "https://www.rinya.maff.go.jp/j/tisan/tisan/attach/pdf/con_3-48.pdf"),
    ("rinya_林道施設長寿命化マニュアル", "https://www.rinya.maff.go.jp/j/seibi/sagyoudo/attach/pdf/tyouzyumyouka-14.pdf"),
    ("rinya_治山事業", "https://www.rinya.maff.go.jp/j/tisan/tisan/con_3.html"),

    # ================= 先行事例チェック（型③） =================
    ("cinii_ため池_衛星", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 衛星") + "&format=json&count=100"),
    ("cinii_ため池_リモートセンシング", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 リモートセンシング") + "&format=json&count=100"),
    ("cinii_ため池_貯水量_推定", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 貯水量 推定") + "&format=json&count=100"),
    ("cinii_調整池_土砂堆積", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("調整池 機能 土砂堆積") + "&format=json&count=50"),
    ("cinii_砂防堰堤_堆砂_衛星", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("堆砂 衛星 推定") + "&format=json&count=50"),
    ("cinii_海岸線_汀線_衛星", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("汀線 衛星 抽出") + "&format=json&count=50"),
    ("cinii_休廃止鉱山_堆積場", "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("休廃止鉱山 堆積場") + "&format=json&count=50"),
    ("kaken_ため池_衛星", "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("ため池 衛星") + "&format=json"),
    ("kaken_ため池_リモートセンシング", "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("ため池 リモートセンシング") + "&format=json"),
    ("jstage_ため池_衛星", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("ため池 衛星")),
    ("jstage_ため池_水位_推定", "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("ため池 水位 リモートセンシング")),
    ("gpatents_ため池_衛星監視", "https://patents.google.com/xhr/query?url=" + urllib.parse.quote("q=(ため池 衛星 水位 監視)") + "&exp="),
    ("gpatents_reservoir_satellite_water_level", "https://patents.google.com/xhr/query?url=" + urllib.parse.quote("q=(small reservoir satellite water level monitoring)") + "&exp="),
    ("shintosei_衛星不適正盛土検知", "https://shintosei.metro.tokyo.lg.jp/leading-project/leading-project-leading-project-52/"),
    ("shintosei_不適正盛土検知_2025進捗", "https://shintosei.metro.tokyo.lg.jp/2025_lp52/"),
    ("sorabatake_不法盛土衛星監視", "https://sorabatake.jp/37639/"),
]

# 衛星シーン在庫（案の実データPoC成立性の事前判定）
STAC_QUERIES = [
    # 平成30年7月豪雨（2018/7/6-7）前後の 東広島・福山（ため池決壊32箇所の集中域）
    {
        "name": "s2_H30豪雨_広島東部",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [132.6, 34.2, 133.6, 34.8],
            "datetime": "2018-06-01T00:00:00Z/2018-08-15T00:00:00Z",
            "limit": 200,
        },
    },
    # 同期間の Sentinel-1（SAR: 雲を貫通するか）
    {
        "name": "s1_H30豪雨_広島東部",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-1-grd"],
            "bbox": [132.6, 34.2, 133.6, 34.8],
            "datetime": "2018-06-01T00:00:00Z/2018-08-15T00:00:00Z",
            "limit": 200,
        },
    },
    # 兵庫県（ため池数 全国1位）の通年在庫（平時スクリーニングの観測機会）
    {
        "name": "s2_兵庫_通年2024",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [134.6, 34.6, 135.3, 35.1],
            "datetime": "2024-01-01T00:00:00Z/2025-01-01T00:00:00Z",
            "limit": 400,
        },
    },
    {
        "name": "s1_兵庫_通年2024",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-1-grd"],
            "bbox": [134.6, 34.6, 135.3, 35.1],
            "datetime": "2024-01-01T00:00:00Z/2025-01-01T00:00:00Z",
            "limit": 400,
        },
    },
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
                "platform": p.get("platform"),
            })
        rows.sort(key=lambda x: x["datetime"] or "")
        rec["count"] = len(rows)
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
    ok = sum(1 for m in manifest if m.get("status") == 200 or m.get("count") is not None)
    print(f"OK {ok} / {len(manifest)}")


if __name__ == "__main__":
    main()
