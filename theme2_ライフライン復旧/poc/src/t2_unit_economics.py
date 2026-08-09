#!/usr/bin/env python3
"""テーマ2 事業計画の裏付け ── ユニットエコノミクスの自前計算。

**この計算の役割**: 2次審査で投資家・銀行・コンサルの審査委員から飛ぶ
「マネタイズは」「ビジネス的なインパクトはどれほどか」「経済における定量的価値は」
に、推測値ではなく計算で答えるための骨格を作る。

**推測値を置かない設計にしてある**（`../CLAUDE.md` の書き方の約束、および
`01_検討経緯.md` 8.7節「規模感を書くなら手動確認が要る。推測値は書かないこと」）:

  - 物量（シーン数・画素数・データ量・CPU時間）は **STACの実測値から計算する**
  - 金額に変換する係数（人月単価・受注単価）は **1点に固定せず、レンジに対する感度表を出す**
  - 未取得の一次情報は `UNRESOLVED` に明示して結果JSONに載せる

入力の出典:
  - シーン数: `origin/sdd-analysis:theme2_ライフライン復旧/sdd_out/analysis.json`
    （火口中心・半径3kmのbboxでSTACを全件集計した実測。1984-2026）
  - 対象座数: 火山噴火緊急減災対策砂防計画 29火山／うち積雪火山21座（01_検討経緯.md 8.7節）
  - 融雪範囲: 蔵王計画 表2-13/2-14 の渓流別 0.20〜2.95 km²（同 8.6節）

出力: `../out/t2_unit_economics.json`（所要1秒未満・乱数なし＝バイト単位で再現）
実行: python3 poc/src/t2_unit_economics.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out" / "t2_unit_economics.json"

# ---------------------------------------------------------------------------
# 1. 実測値（origin/sdd-analysis の analysis.json より。半径3km bbox・全期間の総シーン数）
# ---------------------------------------------------------------------------
SCENES = {  # 火山: (Sentinel-2 全シーン数, Landsat 全シーン数, Landsat初観測)
    "樽前山":       (820, 3816, "1984-04-17"),
    "鳥海山":       (813, 2651, "1984-04-17"),
    "磐梯山":       (835, 2580, "1984-04-17"),
    "富士山":       (845, 2825, "1984-06-04"),
    "草津白根山":   (1690, 1813, "1984-06-04"),
    "浅間山":       (1692, 1389, "1984-06-04"),
    "蔵王山":       (827, 2573, "1984-04-26"),
    "十勝岳":       (1656, 1476, "1984-04-26"),
}

# 融雪期 4/1〜7/31 = 122日／年。この窓のシーンだけを処理する
MELT_WINDOW_FRACTION = 122 / 365.0

# AOI: 火口中心・半径3km → 一辺6kmの正方bbox
AOI_SIDE_KM = 6.0
# 使うバンド: NDSI に green と SWIR1、雲・雪判別に QA_PIXEL、地形補正に NIR の計4面
BANDS = 4
BYTES_PER_PIXEL = 2  # uint16

RES_M = {"landsat": 30.0, "sentinel2": 10.0}

# 対象母集団
N_VOLCANO_PLAN = 29        # 火山噴火緊急減災対策砂防計画の対象火山
N_VOLCANO_SNOW = 21        # うち積雪火山
N_VOLCANO_WARNING = 50     # 火山災害警戒地域の火山
N_MUNICIPALITY = 179       # 同 市町村

# ---------------------------------------------------------------------------
# 2. 未解決（金額に変換する係数のうち、一次情報が取れていないもの）
# ---------------------------------------------------------------------------
UNRESOLVED = [
    {"item": "火山砂防検討業務の契約金額（落札額）",
     "why": "入札情報サービス(PPI)とGEPSが動的サイトで到達不可。第4バッチ fetch_bid_refs.py で"
            "静的公開の契約結果一覧PDFを取得中",
     "how": "取れなければユーザーがPPI/GEPSで手動確認する。受注単価Pの実額はこれが唯一の根拠になる"},
    {"item": "国土交通省「設計業務等技術者単価」（年度公示）",
     "why": "未取得。人月単価の公的な根拠になる",
     "how": "国交省の公示PDFを取得する。取れるまでは人月単価はレンジで扱う"},
    {"item": "クラウド費の実見積",
     "why": "各社の公表単価はあるが見積は未取得",
     "how": "物量（GB・CPU時間）まで計算してあるので、見積が出た時点で掛けるだけでよい"},
]

# ---------------------------------------------------------------------------
# 3. 工数の内訳（作業分解。1座あたりの初回構築と、2座目以降の増分）
#    実施スケジュール（12_提出版_様式4.md）の月別項目をそのまま人月に割り付けた
# ---------------------------------------------------------------------------
EFFORT_FIRST_SITE = {          # 初回1座（＝共通基盤の構築を含む）
    "アーカイブ取得と前処理の自動化": 1.5,
    "消雪日マップ生成（雲雪判別・地形陰影・欠測補間）": 2.0,
    "後退積算による積雪水量復元と融雪係数の較正": 1.5,
    "現地測量との突合と検証": 1.0,
    "年超過確率分布の算定と成果物化（数表・分布図）": 1.0,
}
EFFORT_ADDITIONAL_SITE = {     # 2座目以降（基盤は再利用できる。残るのは座に固有の作業）
    "AOIと渓流区分の設定": 0.15,
    "処理実行と品質確認（雲・陰影の座ごとの癖）": 0.35,
    "融雪係数の地域較正と不確かさ評価": 0.30,
    "成果物化と説明資料": 0.20,
}

# 感度表に使うレンジ（1点に固定しない。**これは仮定であって推定ではない**）
LABOR_RATE_RANGE_MANMONTH = [1.0e6, 1.5e6, 2.0e6]      # 円/人月
UNIT_PRICE_RANGE = [3.0e6, 5.0e6, 1.0e7, 2.0e7]        # 円/件（受注単価P）
FIXED_COST_ANNUAL = 0.0  # 既存事業内で回す前提。別会社化する場合はここに固定費を入れる


def data_volume():
    """1座あたりの処理データ量とシーン数を実測シーン数から計算する。"""
    px = {k: int(round((AOI_SIDE_KM * 1000.0 / r) ** 2)) for k, r in RES_M.items()}
    mb_per_scene = {k: px[k] * BANDS * BYTES_PER_PIXEL / 1e6 for k in px}

    rows = []
    for v, (n_s2, n_ls, first) in SCENES.items():
        s2 = n_s2 * MELT_WINDOW_FRACTION
        ls = n_ls * MELT_WINDOW_FRACTION
        gb = (s2 * mb_per_scene["sentinel2"] + ls * mb_per_scene["landsat"]) / 1e3
        rows.append({"volcano": v, "landsat_first": first,
                     "melt_scenes_sentinel2": round(s2), "melt_scenes_landsat": round(ls),
                     "melt_scenes_total": round(s2 + ls), "clipped_GB": round(gb, 2)})
    rows.sort(key=lambda r: -r["clipped_GB"])
    return px, mb_per_scene, rows


def main():
    px, mb, rows = data_volume()

    mean_gb = sum(r["clipped_GB"] for r in rows) / len(rows)
    mean_scenes = sum(r["melt_scenes_total"] for r in rows) / len(rows)

    m_first = sum(EFFORT_FIRST_SITE.values())
    m_add = sum(EFFORT_ADDITIONAL_SITE.values())

    # 感度表: 人月単価 × 受注単価 に対する 1座あたり粗利と粗利率（2座目以降＝定常状態）
    sens = []
    for rate in LABOR_RATE_RANGE_MANMONTH:
        cost_add = m_add * rate
        for p in UNIT_PRICE_RANGE:
            sens.append({
                "labor_rate_yen_per_manmonth": rate,
                "unit_price_yen": p,
                "cost_per_additional_site_yen": round(cost_add),
                "gross_profit_yen": round(p - cost_add),
                "gross_margin": round((p - cost_add) / p, 3),
            })

    # 座数展開シナリオ（積雪火山21座を何年で取るか）に対する年商レンジ
    rollout = []
    for sites_per_year in (2, 4, 7):
        for p in UNIT_PRICE_RANGE:
            rollout.append({
                "sites_per_year": sites_per_year,
                "unit_price_yen": p,
                "annual_revenue_yen": round(sites_per_year * p),
                "years_to_cover_21": round(N_VOLCANO_SNOW / sites_per_year, 1),
            })

    # 上限（SAM）: 積雪火山21座が同時に1回ずつ発注した場合の一巡分
    sam = [{"unit_price_yen": p, "SAM_one_cycle_yen": round(N_VOLCANO_SNOW * p)}
           for p in UNIT_PRICE_RANGE]

    res = {
        "_note": "金額の係数は1点に固定していない。UNRESOLVED が閉じるまで、"
                 "この結果から『年商◯円』という単一の数字を引用してはいけない。"
                 "引用してよいのは物量（シーン数・GB・人月）と、感度表そのものである。",
        "sources": {
            "scene_counts": "origin/sdd-analysis:theme2_ライフライン復旧/sdd_out/analysis.json"
                            "（火口中心・半径3kmのbboxでSTAC全件集計）",
            "site_counts": "01_検討経緯.md 8.7節（緊急減災対策砂防計画29火山・うち積雪21座、"
                           "火山災害警戒地域50火山179市町村）",
        },
        "aoi": {"side_km": AOI_SIDE_KM, "area_km2": AOI_SIDE_KM ** 2,
                "pixels_per_band": px, "MB_per_scene": {k: round(v, 2) for k, v in mb.items()},
                "bands": BANDS, "melt_window_days": 122},
        "per_volcano": rows,
        "per_volcano_mean": {"melt_scenes": round(mean_scenes), "clipped_GB": round(mean_gb, 2)},
        "portfolio_21_sites": {"total_clipped_GB": round(mean_gb * N_VOLCANO_SNOW, 1),
                               "total_melt_scenes": round(mean_scenes * N_VOLCANO_SNOW)},
        "effort_manmonths": {
            "first_site_breakdown": EFFORT_FIRST_SITE, "first_site_total": round(m_first, 2),
            "additional_site_breakdown": EFFORT_ADDITIONAL_SITE,
            "additional_site_total": round(m_add, 2),
            "marginal_ratio": round(m_add / m_first, 3),
        },
        "sensitivity_gross_profit": sens,
        "rollout_scenarios": rollout,
        "SAM_one_cycle": sam,
        "UNRESOLVED": UNRESOLVED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))

    print(f"AOI {AOI_SIDE_KM}km角 = {AOI_SIDE_KM**2:.0f} km²")
    print(f"  Landsat {px['landsat']:,}px/band  {mb['landsat']:.2f} MB/scene")
    print(f"  Sentinel-2 {px['sentinel2']:,}px/band  {mb['sentinel2']:.2f} MB/scene")
    print(f"融雪期(122日)の処理対象: 1座平均 {mean_scenes:,.0f} シーン / {mean_gb:.2f} GB")
    print(f"21座合計: {mean_gb*N_VOLCANO_SNOW:,.0f} GB")
    print(f"工数: 初回 {m_first:.2f} 人月 → 2座目以降 {m_add:.2f} 人月 "
          f"（増分比 {m_add/m_first:.1%}）")
    print(f"未解決 {len(UNRESOLVED)} 件（金額の係数）→ {OUT}")


if __name__ == "__main__":
    main()
