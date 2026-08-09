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

# **年間の発注フロー**。01_検討経緯.md 8.4節「策定・改定は年1〜3件のペースで継続中」（自前確認）。
# 21座は在庫（ストック）であって年商ではない。市場の大きさを決めるのはこのフローの側である。
PLAN_REVISIONS_PER_YEAR = (1, 3)
# 自社勝率。未取得なのでレンジで扱う（実績要件を満たせるかも未確認＝13節 未解決A）
WIN_RATE_RANGE = (0.2, 0.5)

# ---------------------------------------------------------------------------
# 2. 未解決（金額に変換する係数のうち、一次情報が取れていないもの）
# ---------------------------------------------------------------------------
UNRESOLVED = [
    {"item": "火山砂防検討業務の契約金額（落札額）",
     "why": "第4バッチ fetch_bid_refs.py を実行済み（結果は origin/bid-refs）。"
            "コンサルタント業務の業務名＋契約金額が並ぶ一覧には到達できなかった"
            "（拾えたのは工事の契約金額表と、物品役務の随意契約結果のみ）。"
            "PPI/GEPSは依然として動的サイトで到達不可",
     "how": "ユーザーがPPI/GEPSで手動確認する。受注単価Pの実額はこれが唯一の根拠になる。"
            "1次審査結果公表（2026年10月下旬）までに取れなければ手動へ切り替える"},
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
    "融雪係数の地域較正と不確かさ評価（机上のみ）": 0.30,
    "成果物化と説明資料": 0.20,
}

# 実施スケジュール（12_提出版_様式4.md）のうち、上の2つに入っていない工程。
# **これを入れないと総人月が出ず、開発期間の自己負担額を賞金と比較できない。**
EFFORT_SCHEDULE_REST = {
    "2027年4月 泥流量への変換と下流の判断への影響評価": 1.0,
    "2027年5月 砂防事務所・県砂防部局・コンサルへの提示とプロトタイプ取りまとめ": 1.0,
    "2027年6月 2次審査に向けたデモとドキュメント整備": 1.0,
}
# 実施スケジュールは蔵王＋樽前・鳥海・磐梯の計4座を回す（2027年3月に3座を出力）
N_SITES_IN_SCHEDULE = 4

# **較正データの取得コスト**。上の「机上のみ」0.30人月には現地検証が1円も入っていない。
# 12_提出版_様式4.md の補強欄は「他火山では較正データが無い」と自認し、現地測量の同行を
# 依頼する計画になっている。8.5節によれば蔵王の4冬期のうちUAVが飛べたのは2冬期だけ
# （2冬期は強風・視界不良で欠測）なので、同行が成立する確率自体が高くない。
CALIBRATION_CASES = {
    "既存データを無償提供してもらえる": {"manmonths": 0.0, "outsourced_cost_yen": None},
    "現地測量に同行する（実費は別途）": {"manmonths": 0.5, "outsourced_cost_yen": None},
    "自前で測量を委託する": {"manmonths": 0.2, "outsourced_cost_yen": "未取得"},
}

# **受注獲得原価**。簡易公募型プロポーザルは技術提案書の作成工数がかかり、勝率が1/2なら
# 1件受注あたりの実効原価は「作業1.0人月＋提案工数÷勝率」になる。
EFFORT_PROPOSAL = 0.5      # 技術提案書1本あたりの人月（未取得。レンジ扱いの起点）

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

    # ---- 年間の市場フロー（V-1）。「21座一巡」は在庫。年商はこちらで決まる ----
    flow = []
    for rev in PLAN_REVISIONS_PER_YEAR:
        for p in UNIT_PRICE_RANGE:
            flow.append({
                "plan_revisions_per_year": rev,
                "unit_price_yen": p,
                "market_flow_yen_per_year": round(rev * p),
                "SOM_low_yen_per_year": round(rev * p * WIN_RATE_RANGE[0]),
                "SOM_high_yen_per_year": round(rev * p * WIN_RATE_RANGE[1]),
            })

    # 上限（SAM）: 積雪火山21座が1回ずつ発注した場合の一巡分（ストック。年商ではない）
    sam = [{"unit_price_yen": p, "SAM_one_cycle_yen": round(N_VOLCANO_SNOW * p),
            "years_to_one_cycle_at_flow": [round(N_VOLCANO_SNOW / r, 1)
                                           for r in PLAN_REVISIONS_PER_YEAR]}
           for p in UNIT_PRICE_RANGE]

    # ---- 初回7人月の回収（V-3）と累計粗利率 ----
    payback, cumulative = [], []
    for rate in LABOR_RATE_RANGE_MANMONTH:
        c_add = m_add * rate
        for p in UNIT_PRICE_RANGE:
            margin = p - c_add
            payback.append({
                "labor_rate_yen_per_manmonth": rate, "unit_price_yen": p,
                "sites_to_recover_initial": (round(m_first * rate / margin, 1)
                                             if margin > 0 else None),
            })
            for n in (1, 3, 5, 10, N_VOLCANO_SNOW):
                rev_n, cost_n = n * p, m_first * rate + n * c_add
                cumulative.append({
                    "labor_rate_yen_per_manmonth": rate, "unit_price_yen": p, "sites": n,
                    "cumulative_margin": round((rev_n - cost_n) / rev_n, 3),
                })

    # ---- 受注獲得原価を織り込んだ実効粗利（V-12） ----
    effective = []
    for rate in LABOR_RATE_RANGE_MANMONTH:
        for win in WIN_RATE_RANGE:
            eff_mm = m_add + EFFORT_PROPOSAL / win   # 1件受注あたりの実効人月
            for p in UNIT_PRICE_RANGE:
                effective.append({
                    "labor_rate_yen_per_manmonth": rate, "win_rate": win,
                    "unit_price_yen": p,
                    "effective_manmonths_per_win": round(eff_mm, 2),
                    "effective_margin": round((p - eff_mm * rate) / p, 3),
                })

    # ---- 開発期間の自己負担（V-3）。要項V(1)「費用は各自でご負担ください」 ----
    m_rest = sum(EFFORT_SCHEDULE_REST.values())
    m_schedule = m_first + (N_SITES_IN_SCHEDULE - 1) * m_add + m_rest
    self_funding = [{"labor_rate_yen_per_manmonth": r,
                     "total_manmonths": round(m_schedule, 2),
                     "self_funded_cost_yen": round(m_schedule * r),
                     "vs_prize_1st_20M": round(m_schedule * r / 2.0e7, 2),
                     "vs_prize_2nd_10M": round(m_schedule * r / 1.0e7, 2)}
                    for r in LABOR_RATE_RANGE_MANMONTH]

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
        "per_volcano_mean": {
            "_span": "1984〜2026の43融雪期の総和であって1年あたりではない",
            "melt_scenes_all_years": round(mean_scenes),
            "clipped_GB_all_years": round(mean_gb, 2),
            "melt_scenes_per_year": round(mean_scenes / 43, 1),
            "clipped_MB_per_year": round(mean_gb * 1000 / 43, 1),
        },
        "portfolio_21_sites": {"total_clipped_GB": round(mean_gb * N_VOLCANO_SNOW, 1),
                               "total_melt_scenes": round(mean_scenes * N_VOLCANO_SNOW)},
        "effort_manmonths": {
            "first_site_breakdown": EFFORT_FIRST_SITE, "first_site_total": round(m_first, 2),
            "additional_site_breakdown": EFFORT_ADDITIONAL_SITE,
            "additional_site_total": round(m_add, 2),
            "marginal_ratio": round(m_add / m_first, 3),
            "_caveat": "additional_site_total には現地検証のコストが入っていない。"
                       "calibration_cases を必ず併せて読むこと。"
                       "「1座1人月」を単独で引用してはいけない。",
            "schedule_rest_breakdown": EFFORT_SCHEDULE_REST,
            "schedule_total_manmonths": round(m_schedule, 2),
            "schedule_sites": N_SITES_IN_SCHEDULE,
        },
        "calibration_cases": CALIBRATION_CASES,
        "sensitivity_gross_profit": sens,
        "market_flow_per_year": flow,
        "SAM_one_cycle": sam,
        "payback_sites": payback,
        "cumulative_margin": cumulative,
        "effective_margin_with_bizdev": effective,
        "development_self_funding": self_funding,
        "UNRESOLVED": UNRESOLVED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))

    print(f"AOI {AOI_SIDE_KM}km角 = {AOI_SIDE_KM**2:.0f} km²")
    print(f"  Landsat {px['landsat']:,}px/band  {mb['landsat']:.2f} MB/scene")
    print(f"  Sentinel-2 {px['sentinel2']:,}px/band  {mb['sentinel2']:.2f} MB/scene")
    print(f"融雪期(122日)の処理対象: 1座平均 {mean_scenes:,.0f} シーン / {mean_gb:.2f} GB"
          f"（43融雪期の総和。1年あたりは {mean_scenes/43:.1f} シーン / "
          f"{mean_gb*1000/43:.0f} MB）")
    print(f"21座合計: {mean_gb*N_VOLCANO_SNOW:,.0f} GB")
    print(f"工数: 初回 {m_first:.2f} 人月 → 2座目以降 {m_add:.2f} 人月 "
          f"（増分比 {m_add/m_first:.1%}、ただし現地検証は未計上）")
    print(f"実施スケジュール全体（{N_SITES_IN_SCHEDULE}座）: {m_schedule:.1f} 人月 "
          f"→ 自己負担 {m_schedule*LABOR_RATE_RANGE_MANMONTH[0]/1e4:,.0f}〜"
          f"{m_schedule*LABOR_RATE_RANGE_MANMONTH[-1]/1e4:,.0f} 万円"
          f"（1位賞金2,000万円の "
          f"{m_schedule*LABOR_RATE_RANGE_MANMONTH[0]/2e7:.2f}〜"
          f"{m_schedule*LABOR_RATE_RANGE_MANMONTH[-1]/2e7:.2f} 倍）")
    print(f"年間フロー: 改定 年{PLAN_REVISIONS_PER_YEAR[0]}〜{PLAN_REVISIONS_PER_YEAR[1]}件 × "
          f"P {UNIT_PRICE_RANGE[0]/1e4:,.0f}〜{UNIT_PRICE_RANGE[-1]/1e4:,.0f} 万円 = "
          f"市場全体で年 {PLAN_REVISIONS_PER_YEAR[0]*UNIT_PRICE_RANGE[0]/1e4:,.0f}〜"
          f"{PLAN_REVISIONS_PER_YEAR[1]*UNIT_PRICE_RANGE[-1]/1e4:,.0f} 万円")
    print(f"未解決 {len(UNRESOLVED)} 件（金額の係数）→ {OUT}")


if __name__ == "__main__":
    main()
