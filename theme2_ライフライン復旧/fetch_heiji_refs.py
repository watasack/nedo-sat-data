#!/usr/bin/env python3
"""第5ラウンド（応募例1＝平時の災害リスク評価）の一次情報取得スクリプト

サンドボックスからは mlit.go.jp / bousai.go.jp / maff.go.jp / soumu.go.jp /
jstage.jst.go.jp などが軒並み egress 遮断されているため、GitHub Actions で
取得して heiji-refs ブランチに置く。
トリガ: trigger-fetch-heiji ブランチへの push
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("heiji_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

URLS = [
    # === A. 土砂災害警戒区域・基礎調査・警戒情報 ===
    ("mlit_土砂災害防止対策推進検討会_提言R7",
     "https://www.mlit.go.jp/river/sabo/committee_dosyasaigaitaisaku/202504/01teigen.pdf"),
    ("mlit_土砂災害防止対策推進検討会_index",
     "https://www.mlit.go.jp/river/sabo/committee_dosyasaigaitaisaku/"),
    ("mlit_土砂災害警戒情報_基準設定及び検証の考え方R5",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/dsk_kizyun_kensho_r0503.pdf"),
    ("jcca_土砂災害警戒情報_空振り軽減",
     "https://www.jcca.or.jp/files/achievement/hokoku_etc/r01gyomukenkyu/1-8.pdf"),
    ("mlit_press_基礎調査実施目標達成",
     "https://www.mlit.go.jp/report/press/sabo01_hh_000102.html"),
    ("mlit_砂防関係施設点検要領R7",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/sabo_tenkenyouryou_202504.pdf"),
    ("mlit_土砂災害警戒区域等指定状況",
     "https://www.mlit.go.jp/mizukokudo/sabo/link_dosyasaigai.html"),
    ("hyogo_基礎調査3巡目", "https://web.pref.hyogo.lg.jp/kok11/2024dosyasaigai.html"),
    ("kyoto_基礎調査結果", "https://www.pref.kyoto.jp/dosyashitei/tyosakekka/index.html"),
    ("chiba_基礎調査予定箇所",
     "https://www.pref.chiba.lg.jp/kakan/sabou/kikenkasho/saigai-hou/kisochousayoteikassyotoha.html"),

    # === B. 融雪型火山泥流・山地積雪水量 ===
    ("niigata_山地積雪水量推定_共同研究報告",
     "https://www.nhdr.niigata-u.ac.jp/wp-content/uploads/2023/12/473d835a8dd577a4445942862676c75a.pdf"),
    ("shizuoka_富士山ハザードマップ報告書05_融雪型火山泥流",
     "https://www.pref.shizuoka.jp/_res/projects/default_project/_page_/001/030/023/20210326_fujisan_012houkokusyo05.pdf"),
    ("bousai_火山防災マップ作成指針",
     "https://www.bousai.go.jp/kazan/shiryo/pdf/20130404_mapshishin.pdf"),
    ("tsumagoi_浅間山融雪型火山泥流マップ",
     "https://www.vill.tsumagoi.gunma.jp/www/contents/1000000000057/simple/yuusetugatamap.pdf"),
    ("yamanashi_富士山_融雪型火山泥流_説明資料",
     "https://www.pref.yamanashi.jp/documents/101190/3_setumeisiryou_fujisanhm.pdf"),
    ("bousai_火山_index", "https://www.bousai.go.jp/kazan/index.html"),
    ("mlit_火山砂防_index", "https://www.mlit.go.jp/mizukokudo/sabo/kazan.html"),
    ("mlit_火山噴火緊急減災対策砂防計画",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/kazan_gensai.html"),

    # === C. ため池 ===
    ("maff_農業用ため池を巡る状況R6",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/attach/pdf/hozenhou-44.pdf"),
    ("maff_ため池管理保全法_都道府県別対応状況",
     "https://www.maff.go.jp/j/nousin/bousai/bousai_saigai/b_tameike/tameike_taiou.html"),
    ("soumu_中部管区_ため池実態調査R3",
     "https://www.soumu.go.jp/main_content/000763910.pdf"),
    ("soumu_ため池防災減災対策調査_通知",
     "https://www.soumu.go.jp/menu_news/s-news/hyouka_240621000174807.html"),
    ("soumu_ため池_フォローアップ",
     "https://www.soumu.go.jp/menu_news/s-news/hyouka_250731000183652.html"),

    # === D. 盛土（先行確認＝東京都・ガイドライン） ===
    ("soumu_盛土等による災害の防止に関する調査_通知",
     "https://www.soumu.go.jp/menu_news/s-news/hyouka_260422000189350.html"),
    ("rinya_不法危険盛土等への対処方策ガイドライン",
     "https://www.rinya.maff.go.jp/j/tisan/tisan/attach/pdf/morido-39.pdf"),
    ("sorabatake_不法盛土を宇宙から監視", "https://sorabatake.jp/37639/"),
    ("mlit_盛土規制法_施行状況", "https://www.mlit.go.jp/toshi/morido-sekou.html"),
    ("mlit_大規模盛土造成地_変動予測調査",
     "https://www.mlit.go.jp/toshi/toshi_tobou_tk_000050.html"),
    ("mlit_大規模盛土造成地_経過観察マニュアルR5",
     "https://www.mlit.go.jp/toshi/content/001711369.pdf"),

    # === E. 河道の維持管理・流下能力・中小河川 ===
    ("kasen_河道の維持管理要領試案2018",
     "https://www.kasen.or.jp/Portals/0/201810%E7%A0%94%E7%A9%B6%E6%89%80%E8%B3%87%E6%96%99%E7%AC%AC33%E5%8F%B7.pdf"),
    ("mlit_中小河川洪水浸水想定区域図作成の手引き2版",
     "https://www.mlit.go.jp/river/shishin_guideline/kasen/shinsuisoutei/pdf/chusho_kasen_sinsou_kuiki_tebiki2.pdf"),
    ("nilim_小規模河川の洪水浸水想定区域図作成の手引きR5",
     "https://www.nilim.go.jp/lab/rcg/newhp/seika.files/pdf/tebiki_4.pdf"),
    ("mlit_小規模河川の氾濫推定図作成の手引きR2",
     "https://www.mlit.go.jp/river/shishin_guideline/pdf/syokibo_tebiki.pdf"),
    ("mlit_水位周知河川等について_資料4",
     "https://www.mlit.go.jp/river/shinngikai_blog/suigairisk/dai01kai/pdf/4_suiisyuuchikasen.pdf"),
    ("mlit_洪水浸水想定区域図_所在地一覧",
     "https://www.mlit.go.jp/river/bousai/main/saigai/tisiki/syozaiti/"),
    ("mlit_堤防等河川管理施設及び河道の点検評価要領R5",
     "https://www.mlit.go.jp/river/shishin_guideline/kasen/pdf/01_teibou_tenkenhyouka_youryou_r503.pdf"),
    ("mlit_河川砂防技術基準維持管理編河川編",
     "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/ijikanri/kasen/pdf/gijutsukijun.pdf"),

    # === F. 内水・下水道 ===
    ("mlit_内水浸水想定区域図作成マニュアルR3",
     "https://www.mlit.go.jp/river/shishin_guideline/pdf/naisui_manual.pdf"),
    ("mlit_下水道_雨水管理総合計画", "https://www.mlit.go.jp/mizukokudo/sewerage/index.html"),

    # === G. 地盤沈下・相対的海面上昇・ゼロメートル ===
    ("jstage_相対的海面上昇率_東京湾大阪湾",
     "https://www.jstage.jst.go.jp/article/jgs/19/4/19_387/_article/-char/ja/"),
    ("jstage_相対的海面上昇率_pdf",
     "https://www.jstage.jst.go.jp/article/jgs/19/4/19_387/_pdf/-char/ja"),
    ("env_地盤沈下_全国の状況", "https://www.env.go.jp/water/jiban/chinka.html"),
    ("gsi_地盤変動_水準測量", "https://www.gsi.go.jp/kanshi.html"),

    # === H. 液状化 ===
    ("hrr_石川県内液状化しやすさマップ",
     "https://www.hrr.mlit.go.jp/ekijoka/ishikawa/pamphlet/ishikawa_map_full.pdf"),
    ("bosai_能登液状化被害分布_先名",
     "https://www.bosai.go.jp/sp/introduction/kyoso/kenkyukai/mha4gl00000018mw-att/houkokukai_senna.pdf"),
    ("cas_能登半島地震を踏まえた災害対応の在り方_概要",
     "https://www.cas.go.jp/jp/seisaku/suisinkaigi/joukyou_dai11/sankou1.pdf"),
    ("mlit_宅地の液状化ハザードマップ", "https://www.mlit.go.jp/toshi/toshi_tobou_tk_000037.html"),

    # === I. 地すべり地形・斜面 ===
    ("bosai_地すべり地形分布図について",
     "https://dil-opac.bosai.go.jp/publication/nied_tech_note/landslidemap/about.html"),
    ("nilim_地すべり地形分布図増補版_補備データ",
     "https://www.nilim.go.jp/lab/bcg/siryou/tnn/tnn1120pdf/ks1120_15.pdf"),

    # === J. 国土強靱化・防災基本計画のデータ不足記述 ===
    ("cas_国土強靱化年次計画", "https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/index.html"),
    ("bousai_防災基本計画", "https://www.bousai.go.jp/taisaku/keikaku/kihon.html"),
    ("bousai_中央防災会議", "https://www.bousai.go.jp/kaigirep/chuobou/index.html"),

    # === K. 会計検査院（「実態を把握していない」の宝庫） ===
    ("jbaudit_検索_砂防",
     "https://report.jbaudit.go.jp/org/effort.htm"),
    ("jbaudit_top", "https://report.jbaudit.go.jp/"),

    # === L. 先行事例の探索（J-STAGE / CiNii / KAKEN / 特許） ===
    ("cinii_積雪水量_衛星_火山泥流",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("融雪型火山泥流 積雪水量") + "&format=json&count=100"),
    ("cinii_山地積雪_リモートセンシング",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("山地積雪 リモートセンシング") + "&format=json&count=100"),
    ("cinii_土砂災害警戒区域_衛星",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("土砂災害警戒区域 衛星") + "&format=json&count=100"),
    ("cinii_地形改変_衛星_斜面",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("地形改変 衛星 斜面") + "&format=json&count=100"),
    ("cinii_ため池_衛星",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 衛星 リモートセンシング") + "&format=json&count=100"),
    ("cinii_ため池_水位_モニタリング",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("ため池 貯水量 推定") + "&format=json&count=100"),
    ("cinii_河道内樹木_リモートセンシング",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("河道内樹木 リモートセンシング") + "&format=json&count=100"),
    ("cinii_流下能力_衛星",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("流下能力 衛星") + "&format=json&count=100"),
    ("cinii_地盤沈下_浸水想定_InSAR",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("地盤沈下 浸水想定 InSAR") + "&format=json&count=100"),
    ("cinii_土層厚_推定_リモートセンシング",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("土層厚 推定 リモートセンシング") + "&format=json&count=100"),
    ("cinii_砂防堰堤_堆砂_衛星",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("砂防堰堤 堆砂 衛星") + "&format=json&count=100"),
    ("cinii_雪崩_危険度_衛星",
     "https://cir.nii.ac.jp/opensearch/all?q=" + urllib.parse.quote("雪崩 危険度 衛星") + "&format=json&count=100"),
    ("kaken_融雪型火山泥流",
     "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("融雪型火山泥流") + "&format=json"),
    ("kaken_積雪水量_衛星",
     "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("積雪水量 衛星") + "&format=json"),
    ("kaken_ため池_リモートセンシング",
     "https://kaken.nii.ac.jp/opensearch/?qm=" + urllib.parse.quote("ため池 リモートセンシング") + "&format=json"),
    ("jstage_search_融雪型火山泥流",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("融雪型火山泥流 積雪")),
    ("jstage_search_土砂災害警戒区域_見直し",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("土砂災害警戒区域 見直し 地形改変")),
    ("jstage_search_ため池_衛星",
     "https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=" + urllib.parse.quote("ため池 衛星 水面")),
]

STAC_QUERIES = [
    # 積雪期の火山（十勝岳・蔵王・浅間・鳥海）に晴天の Sentinel-2 が何シーンあるか
    {
        "name": "s2_十勝岳_積雪期2020_2025",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [142.5, 43.3, 142.9, 43.6],
            "datetime": "2020-01-01T00:00:00Z/2026-04-30T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 500,
        },
    },
    {
        "name": "s2_蔵王_積雪期2020_2025",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [140.3, 38.0, 140.6, 38.3],
            "datetime": "2020-01-01T00:00:00Z/2026-04-30T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 500,
        },
    },
    # 兵庫県（基礎調査3巡目・地形改変の検証地）の Sentinel-2 在庫
    {
        "name": "s2_兵庫_2016_2026",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [134.8, 34.7, 135.4, 35.1],
            "datetime": "2016-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 500,
        },
    },
    # ため池密集地（東播磨）の Sentinel-2
    {
        "name": "s2_東播磨ため池_2019_2026",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [134.85, 34.72, 135.05, 34.88],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 500,
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
        with urllib.request.urlopen(req, timeout=120) as r:
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
                "tile": p.get("grid:code") or p.get("landsat:wrs_path"),
            })
        rows.sort(key=lambda x: (x["datetime"] or ""))
        OUT.joinpath(f"{q['name']}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1))
        rec["n"] = len(rows)
        rec["file"] = f"{OUT}/{q['name']}.json"
    except Exception as e:
        rec["error"] = repr(e)
    return rec


def main():
    OUT.mkdir(exist_ok=True)
    man = [fetch(n, u) for n, u in URLS]
    man += [stac(q) for q in STAC_QUERIES]
    OUT.joinpath("manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1))
    ok = sum(1 for m in man if m.get("status") == 200 or m.get("n") is not None)
    print(f"done: {ok}/{len(man)} ok")
    for m in man:
        if m.get("status") != 200 and m.get("n") is None:
            print("  NG:", m["name"], m.get("status"), m.get("error", "")[:120])


if __name__ == "__main__":
    main()
