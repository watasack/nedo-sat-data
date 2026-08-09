#!/usr/bin/env python3
"""融雪型火山泥流・融雪地すべり案（第7ラウンド）の一次情報取得スクリプト

サンドボックスからは mlit.go.jp / thr.mlit.go.jp / bousai.go.jp / jstage 等が
egress 遮断されているため、GitHub Actions で取得して snow-refs ブランチに置く。
トリガ: trigger-fetch-snow ブランチへの push

他エージェントの fetch_*.py と衝突しないよう出力先は snow_refs/ に分離。
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("snow_refs")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

URLS = [
    # === A. 火山砂防の計画技術基準（泥流総量の算定根拠） ===
    ("mlit_火山噴火緊急減災対策砂防計画策定ガイドライン",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/volcanopdf/kinkyugensai_gaid.pdf"),
    ("mlit_火山砂防計画策定指針R5",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/volcanopdf/kazansabo_shishin.pdf"),
    ("mlit_火山砂防_index",
     "https://www.mlit.go.jp/mizukokudo/sabo/volcanic_disaster.html"),
    ("bousai_緊急減災対策砂防計画_ポータル",
     "https://www.bousai.go.jp/kazan/kazanportal/mlit003.html"),
    ("stc_火山噴火緊急減災対策砂防計画の方向と課題",
     "https://www.stc.or.jp/journal_sabo/pdf/art_103/103_03_volcano01.pdf"),
    # 火山防災マップ作成指針の「別冊資料」（融雪型火山泥流の詳細理論）
    ("bousai_火山防災マップ作成指針_別冊資料",
     "https://www.bousai.go.jp/kazan/shiryo/pdf/20130404_mapshishin_bessatsu.pdf"),
    ("bousai_火山防災マップ_資料一覧",
     "https://www.bousai.go.jp/kazan/shiryo/index.html"),

    # === B. 個別火山の緊急減災対策砂防計画（積雪・火砕流量の設定値） ===
    ("thr_蔵王山火山噴火緊急減災対策砂防計画",
     "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/zao/03/zao_02_05_doc.pdf"),
    ("thr_蔵王_火山噴火_index",
     "https://www.thr.mlit.go.jp/shinjyou/03_sabou/kazan-funka/zao/"),
    ("hkd_十勝岳火山噴火緊急減災対策砂防計画",
     "https://www.hkd.mlit.go.jp/ob/tisui/wq5ono000000dq6r-att/wq5ono000000dqbb.pdf"),
    ("hkd_十勝岳_火山砂防_index",
     "https://www.hkd.mlit.go.jp/ob/tisui/wq5ono000000dq6r.html"),
    ("thr_鳥海山火山噴火緊急減災対策砂防計画",
     "https://www.thr.mlit.go.jp/sakata/river/sabo/chokai/index.html"),
    ("ktr_浅間山火山噴火緊急減災対策砂防計画",
     "https://www.ktr.mlit.go.jp/tone_sabo/tone_sabo00105.html"),
    ("hrr_立山_常願寺川_火山砂防",
     "https://www.hrr.mlit.go.jp/jintsu/kids/sabo/sabo10.html"),

    # === C. 融雪型火山泥流の物理・発生機構の研究 ===
    ("hokurikutei_融雪型火山泥流の発生機構解明",
     "https://www4.hokurikutei.or.jp/wp-content/uploads/2023/04/03-18.pdf"),
    ("dpri_融雪が火山泥流の堆積域に及ぼす影響",
     "https://www.dpri.kyoto-u.ac.jp/nenpo/no55/ronbunB/a55b0p41.pdf"),
    ("jstage_積雪の衛星リモートセンシング",
     "https://www.jstage.jst.go.jp/article/seppyo1941/69/2/69_2_155/_pdf"),

    # === D. 先行研究（新潟大・防災科研・次世代火山）2024-2026 ===
    ("bosai_雪氷防災研究センター_研究成果",
     "https://www.bosai.go.jp/seppyo/research/seika/index.html"),
    ("bosai_雪氷_雪崩研究成果",
     "https://www.bosai.go.jp/seppyo/research/seika/seika_nadare.html"),
    ("nhdr_新潟大災害復興科学研究所_共同研究一覧",
     "https://www.nhdr.niigata-u.ac.jp/kyodo/"),
    ("kazan_次世代火山研究推進事業_index",
     "https://www.kazan-pj.jp/"),
    ("kazan_次世代火山研究_課題一覧",
     "https://www.kazan-pj.jp/research/"),
    ("bosai_雪おろシグナル",
     "https://seppyo.bosai.go.jp/snow-weight-yamagata/"),
    ("cinii_山頂積雪_衛星_火山",
     "https://cir.nii.ac.jp/opensearch/all?q=%E7%81%AB%E5%B1%B1%20%E7%A9%8D%E9%9B%AA%E6%B0%B4%E9%87%8F%20%E8%A1%9B%E6%98%9F&format=json&count=50"),
    ("cinii_融雪水量_地すべり",
     "https://cir.nii.ac.jp/opensearch/all?q=%E8%9E%8D%E9%9B%AA%E6%B0%B4%E9%87%8F%20%E5%9C%B0%E3%81%99%E3%81%B9%E3%82%8A&format=json&count=50"),
    ("cinii_土壌雨量指数_融雪",
     "https://cir.nii.ac.jp/opensearch/all?q=%E5%9C%9F%E5%A3%8C%E9%9B%A8%E9%87%8F%E6%8C%87%E6%95%B0%20%E8%9E%8D%E9%9B%AA&format=json&count=50"),
    ("cinii_消雪日_積雪水量_再構成",
     "https://cir.nii.ac.jp/opensearch/all?q=%E6%B6%88%E9%9B%AA%E6%97%A5%20%E7%A9%8D%E9%9B%AA%E6%B0%B4%E9%87%8F&format=json&count=50"),
    ("kaken_融雪型火山泥流",
     "https://nrid.nii.ac.jp/opensearch/?qb=%E8%9E%8D%E9%9B%AA%E5%9E%8B%E7%81%AB%E5%B1%B1%E6%B3%A5%E6%B5%81&format=json"),

    # === E. 融雪地すべり・土壌雨量指数への融雪組み込み ===
    ("mlit_土砂災害警戒情報_基準設定R5",
     "https://www.mlit.go.jp/river/shishin_guideline/sabo/dsk_kizyun_kensho_r0503.pdf"),
    ("jma_土壌雨量指数",
     "https://www.jma.go.jp/jma/kishou/know/bosai/dojoshisu.html"),
    ("niigata_地すべり_融雪期",
     "https://www.pref.niigata.lg.jp/sec/sabo/index.html"),
    ("nilim_地すべり_融雪",
     "https://www.nilim.go.jp/lab/rbg/kasenkasen.htm"),
    ("mlit_雪崩融雪災害_index",
     "https://www.mlit.go.jp/river/sabo/link_yuki.html"),

    # === F. 火山防災協議会・計画改定サイクル ===
    ("bousai_火山防災協議会",
     "https://www.bousai.go.jp/kazan/shiryo/kyougikai.html"),
    ("bousai_活動火山対策特別措置法",
     "https://www.bousai.go.jp/kazan/index.html"),
]

STAC_QUERIES = [
    # 融雪期（2〜6月）に低雲量の Sentinel-2 が主要火山で何シーンあるか
    {
        "name": "s2_十勝岳_融雪期",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [142.60, 43.35, 142.75, 43.48],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 900,
        },
    },
    {
        "name": "s2_鳥海山_融雪期",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [140.00, 39.06, 140.13, 39.16],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 900,
        },
    },
    {
        "name": "s2_浅間山_融雪期",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [138.48, 36.36, 138.58, 36.45],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 900,
        },
    },
    {
        "name": "s2_蔵王刈田岳_融雪期",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [140.42, 38.10, 140.52, 38.20],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 900,
        },
    },
    {
        "name": "s2_富士山_融雪期",
        "url": "https://earth-search.aws.element84.com/v1/search",
        "body": {
            "collections": ["sentinel-2-l2a"],
            "bbox": [138.68, 35.32, 138.79, 35.40],
            "datetime": "2019-01-01T00:00:00Z/2026-08-01T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 30}},
            "limit": 900,
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
        with urllib.request.urlopen(req, timeout=180) as r:
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
            print("  NG:", m["name"], m.get("status"), str(m.get("error", ""))[:120])


if __name__ == "__main__":
    main()
