#!/usr/bin/env python3
"""生存4件を、閉じた急所の一次資料の数値に照らして自前計算で当て直す（差し替え検証・独立セッション）

**この計算は「衛星で足りるか」ではなく「既に座っている手段に対して負けていないか」を問う。**
一次資料（`origin/kyusho4` `origin/kyusho4b` `origin/kyusho4c` で取得）で確定した相手方の仕様を
そのまま定数に置き、同じ対象を我々の使える無償アーカイブで見たときの画素数と情報量を比べる。

| 候補 | 座っている手段（一次資料で確定） | 出典 |
|---|---|---|
| 大屋根の風災査定 | 東京海上日動×国際航業「企業向け風災リスク診断」= **地上解像度5cmの航空写真**（2023年4月〜） | PR TIMES 000000032.000086246 |
| 街区スケールの地盤沈下 | 応用地質LIANA／Synspective DInSAR／スペースデータ LAND SUBSIDENCE MAP（**Sentinel-1のInSAR時系列**、10万点超） | PR TIMES 000000181.000080352 ほか |
| S1' 造成・盛土の「いつ」 | 国交省『不法・危険盛土等への対処方策ガイドライン』表2.1 = **無償光学10m/抽出精度1,000㎡・有償光学数m/500㎡・SAR/1,000㎡** | mlit 001634495.pdf |
| 砂防堰堤の堆砂率 | 『砂防関係施設点検要領（案）』= 堆砂状況は定期点検＋平常巡視の必須事項、**UAVの垂直正画像**で撮る | mlit sabo_tenkenyouryou_202504.pdf |

乱数なし＝再現可能。結果は `poc/out/alt4_screen.json`。
"""
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 共通
# 我々が無償で使えるアーカイブ（`.claude/agents/nedo-idea-explorer.md` 物差し1の限定条件）
FREE = {
    "Landsat (30m, 1984-)":      {"gsd_m": 30.0,  "since": 1984},
    "Sentinel-2 (10m, 2015-)":   {"gsd_m": 10.0,  "since": 2015},
    "Sentinel-1 (20m, 2014-)":   {"gsd_m": 20.0,  "since": 2014},
}
YEAR_NOW = 2026


def px(area_m2, gsd_m):
    """面積 area_m2 の対象が、画素サイズ gsd_m のセンサで何画素になるか"""
    return area_m2 / (gsd_m ** 2)


results = {"note": "一次資料で確定した相手方の仕様と、無償アーカイブでの見え方の比較", "cases": {}}

# ============================================================ 1. 大屋根の風災査定
# 対象＝工場・倉庫の屋根。争点は「屋根の劣化（要修繕箇所）」で、
# 相手方（国際航業）は 5cm 航空写真で「箇所」を特定している。
INCUMBENT_ROOF_GSD = 0.05           # m（一次資料の実数）
GSI_AERIAL_GSD = 0.30               # m（G2(f) 国土地理院の空中写真アーカイブ）
roof_cases = {
    "中規模倉庫 50m x 30m":  50 * 30,
    "大型物流倉庫 200m x 100m": 200 * 100,
    "工場棟 100m x 50m":     100 * 50,
}
roof = {}
for name, a in roof_cases.items():
    row = {"area_m2": a,
           "incumbent_px_5cm": round(px(a, INCUMBENT_ROOF_GSD)),
           "gsi_aerial_px_30cm": round(px(a, GSI_AERIAL_GSD))}
    for s, d in FREE.items():
        row[f"free_px_{d['gsd_m']:.0f}m"] = round(px(a, d["gsd_m"]), 1)
    # 「箇所を特定する」には対象内に複数画素が要る。1画素しか無ければ屋根の平均しか出ない
    row["free_can_localize_at_10m"] = px(a, 10.0) >= 25       # 5x5画素を最低条件とする
    row["resolution_ratio_vs_incumbent"] = round((10.0 / INCUMBENT_ROOF_GSD) ** 2)  # 面積比
    roof[name] = row
results["cases"]["大屋根の風災査定"] = {
    "incumbent": "東京海上日動×国際航業 企業向け風災リスク診断（地上解像度5cm航空写真＋事故データ、2023年4月〜、全政令指定都市へ拡大中）",
    "incumbent_next_step_is_satellite": True,   # リリース原文「衛星データ…の活用などの可能性を検討していきます」
    "detail": roof,
    "verdict": ("相手方は同一顧客（損保）・同一対象（企業の大屋根）・同一意思決定（要修繕箇所の特定＝予防保全）で"
                "2023年4月から商用提供済み。面積比で無償光学10mは航空写真5cmの40,000分の1の情報量しか持たず、"
                "『箇所の特定』は原理的に返せない。残る差別化は『遡及』だけだが、"
                "国際航業の航空写真も国土地理院の空中写真も同じ時代を遡れる（かつ0.3m級）。"),
}

# ============================================================ 2. 街区スケールの地盤沈下
# 争点＝着工前の街区の沈下速度。相手方は同じ Sentinel-1 InSAR を商品化済み。
BLOCK_M = 100.0                     # 街区スケール 100m 角
results["cases"]["街区スケールの地盤沈下"] = {
    "incumbent": ("応用地質 LIANA®（2024年3月に低価格定額の『LIANAメッシュ』、2025年3月に東京都・大阪府・宮城県へ展開、"
                  "2026年7月にだいち4号版）／Synspective DInSAR（2023年2月）／スカパーJSAT×ゼンリン×日本工営（2022年11月）／"
                  "スペースデータ LAND SUBSIDENCE MAP（2026年7月17日、Sentinel-1時系列・10万点超・昇降軌道突合・3D都市モデル重畳）"),
    "our_sensor_is_identical": True,
    "block_px_sentinel1_20m": round(px(BLOCK_M ** 2, 20.0), 1),
    "archive_years_sentinel1": YEAR_NOW - FREE["Sentinel-1 (20m, 2014-)"]["since"],
    "verdict": ("使うセンサ・解析手法（Sentinel-1 のInSAR時系列）・出力（mm/年の面的分布）・想定ユーザー"
                "（自治体／ライフライン事業者／地盤調査・建設コンサル）が、2026年7月17日公開の商品と一致する。"
                "差別化として残るのは『遡及＝着工前の速度』だが、これは同じアーカイブへの問い合わせ方の違いであって"
                "別の商品ではない。④『これまでにない新しいサービスであるか』を書けない。"),
}

# ============================================================ 3. S1' 造成・盛土の「いつ」
# ガイドライン表2.1 が抽出精度を面積で明示している。我々が上回れるかを面積で当てる。
GUIDE = {"無償光学(10m)": 1000.0, "有償光学(数m〜数10cm)": 500.0, "SAR(Sentinel-1)": 1000.0}  # 抽出精度[m2]
results["cases"]["S1' 造成・盛土の「いつ」"] = {
    "incumbent": ("国土交通省『不法・危険盛土等への対処方策ガイドライン』（令和5年5月）2.4節が"
                  "衛星画像解析による監視・発見の手順と表2.1（画像3種の撮影時期・頻度・解像度・抽出精度）を全国へ配布済み。"
                  "奈良県は年2回の外部委託で実施し、盛土等条例を持つ県内市町村にも提供している。"),
    "guideline_detection_threshold_m2": GUIDE,
    "guideline_prescribes_timing_method": True,   # 「あらかじめ規制区域指定直後の衛星画像を入手し…速やかに特定できるよう準備」
    "answer_becomes_a_ledger_column": True,       # 「区域指定時に工事着手していたかどうかを、台帳に整理・保存」
    "demand_for_timing_exists": True,             # 許可対象行為への該当性が区域指定の前後で変わる
    "verdict": ("『いつ』の需要は存在する（前セッションの仮説と逆）。しかし所管官庁が方法・センサ・抽出精度まで"
                "書いた手順書を全国へ配布し、実施は業務委託の形で既に回っている。"
                "我々が持ち込めるのは同じ無償光学であり、ガイドラインが自ら書いた抽出精度1,000㎡を上回らない。"),
}

# ============================================================ 4. 砂防堰堤の堆砂率
# 堆砂地は渓流内の細長い領域。幅で画素が決まる。
SEDIMENT_W = [20.0, 40.0, 80.0]     # 堆砂地の幅[m]（渓流規模の代表値）
sed = {}
for w in SEDIMENT_W:
    sed[f"幅{w:.0f}m"] = {s: round(w / d["gsd_m"], 2) for s, d in FREE.items()}
results["cases"]["砂防堰堤の堆砂率"] = {
    "incumbent": ("『砂防関係施設点検要領（案）』（令和7年4月）が堆砂状況を定期点検の必須事項とし、"
                  "透過型では『上流側の堆砂状況の確認は定期点検のみならず、平常の巡視においても確認する』と規定。"
                  "表の1列が丸ごと『UAVによる近接点検時の留意点』で、堆砂は『高度を維持して垂直正画像の連続写真や俯瞰写真』と手順まで指定。"
                  "同時に『砂防現場におけるUAV自律飛行点検マニュアル（案）』（令和7年4月）が公開されている。"),
    "cross_valley_pixels": sed,
    "verdict": ("制度が届けている（G1）うえに、届ける手段としてUAVが公式マニュアル付きで指定されている（G2(c)）。"
                "加えて堆砂地の横断幅は無償センサで1〜4画素しかなく、堆砂長からの逆算に必要な水際線の位置を返せない。"),
}

# ============================================================ 5. 今回の応募に間に合うかの時間計算
# 実測の基準: git log で 46.4時間 / 146コミット / 提案書2件 / PoC 4本（15_事業計画の裏付け.md）
DAYS = {
    "今日→事務局照会の実質期限(8/12)": 2,
    "今日→事務局照会の最終期限(8/24正午)": 14,
    "今日→本文凍結(8/24)": 14,
    "今日→推奨提出日(8/28)": 18,
    "今日→締切(8/31正午)": 21,
}
# 差し替えに必要な作業（現行2案が実際に費やした工程を、同じ順序で並べたもの）
SWAP_TASKS = {
    "①〜⑤の500字5設問の起草": 2,
    "図表3点の作成": 1,
    "事務局視点レビュー（受理・様式）を最低3周": 3,
    "審査員・投資家・ベンチマークの3レビューと反映": 3,
    "③を埋めるPoC（新センサ。下で分解）": None,
    "事務局照会の設問の作り直しと送付": 1,
}
# ③のPoC所要（センサ別。現行テーマ1のPoCは熱赤外で、可視反射率にもInSARにも流用できない）
POC_DAYS = {
    "可視反射率（大屋根・盛土）: Sentinel-2の取得と時系列化": 3,
    "InSAR（街区沈下）: SLC取得＋干渉処理＋時系列解析の環境構築": 8,
    "InSAR: 較正（水準点との突合）": 5,
}
results["schedule"] = {
    "days_remaining": DAYS,
    "swap_tasks_days": SWAP_TASKS,
    "poc_days_by_sensor": POC_DAYS,
    "note": ("この環境からの外部取得は GitHub Actions 迂回でしか通らず、1巡あたりの往復に実測で数分〜十数分かかる。"
             "Sentinel-1 の SLC は1シーン数GBで、Actions のランナー上で干渉処理まで回す構成は本リポジトリに前例が無い。"),
}
results["schedule"]["verdict_A"] = (
    "①〜⑤の起草だけなら2日で書けるので『21日では交換できない』は誤りのままである（前セッションの自己批判は正しい）。"
    "律速は③で、可視反射率でも3日、InSARでは13日かかる。"
    "しかし本当の障害は日数ではなく、**4件とも急所が閉じた結果として死んでいる**ことである。"
)

(OUT / "alt4_screen.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------------------------------------------------------- 表示
print("=== 1. 大屋根の風災査定: 相手方5cm航空写真に対する無償光学の画素数 ===")
for k, v in roof.items():
    print(f"  {k:<22} 面積{v['area_m2']:>7,}m²  5cm航空写真 {v['incumbent_px_5cm']:>10,}px  "
          f"Sentinel-2(10m) {v['free_px_10m']:>7.1f}px  Landsat(30m) {v['free_px_30m']:>5.1f}px")
print(f"  → 面積比で無償光学10mは航空写真5cmの {roof['工場棟 100m x 50m']['resolution_ratio_vs_incumbent']:,} 分の1")

print("\n=== 2. 街区沈下: 使うセンサが相手方と同一 ===")
c = results["cases"]["街区スケールの地盤沈下"]
print(f"  街区100m角 = Sentinel-1(20m)で {c['block_px_sentinel1_20m']}画素 / アーカイブ {c['archive_years_sentinel1']}年")
print("  → 相手方4社が同じ Sentinel-1 InSAR 時系列で商品化済み")

print("\n=== 3. S1': ガイドラインが自ら書いた抽出精度 ===")
for k, v in GUIDE.items():
    print(f"  {k:<24} 抽出精度 {v:>7,.0f} m²")

print("\n=== 4. 砂防堆砂地: 横断幅の画素数 ===")
for k, v in sed.items():
    print(f"  {k:<8} " + "  ".join(f"{s.split(' ')[0]}={n:.2f}px" for s, n in v.items()))

print("\n=== 5. 残り日数と、差し替えに要する工程 ===")
for k, v in DAYS.items():
    print(f"  {k:<34} {v:>3} 日")
print("  差し替えの工程（③のPoCを除く合計）: "
      f"{sum(v for v in SWAP_TASKS.values() if v):>2} 日")
for k, v in POC_DAYS.items():
    print(f"    ③のPoC  {k:<52} {v:>2} 日")
print(f"\n{results['schedule']['verdict_A']}")
