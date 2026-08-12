"""テーマ2 PoC: 消雪日の精度を、実データの間引き実験で測る

## なぜ要るか

確定案は「消雪日マップ → 後退積算でSWE → 年超過確率分布」である。
消雪日の精度については 8.6節で **±E[G]/4**（E[G]=消雪日を挟む晴天観測間隔の期待値）
という前提を置き、「E[G]≤40日なら±10日」として使える年数を8火山で数えた。
`t2_snowmap_results.json` の実測は蔵王で **観測間隔の中央値20日・最悪年48日**。

しかしこの±10日という数字は**一度も実測されていない**。
`t2_snow_reconstruction.py` は復元側に**真の消雪日を与えている**（同スクリプト冒頭の
「節1・4・5は循環」）ので、消雪日の誤差はSWEの誤差に一度も伝播していない。
つまり現状のPoCは、**この案の観測量そのものの誤差を評価していない。**

## ここでやること

`snowmap-poc` ブランチの**実消雪日マップ9年分**（蔵王・火口半径3km・30mグリッド・
41,006画素）を使い、**観測日を間引いて中点則の誤差を実測する**。

  - 密な年（2019年16シーン・2023年25シーン・2024年22シーン）の消雪日マップを参照値とし、
    そこから「その画素はある日に雪か否か」を再現できる。
  - 実在する観測日の**部分集合**を取り、同じ中点則を当てて推定値を作る。
  - 参照値との差が、観測が薄い年（1984-98年のLandsat単独時代）に生じる誤差である。

**参照値自身も±（間隔）/2 の量子化を持つ**ので、これは絶対精度ではなく
「観測密度を落としたときに増える誤差」である。判定に使うのはこの相対量で足りる——
8.6節が年数を数えた基準（E[G]≤40日）がその通りに効くかを見たいのだから。

## 間引く前に分かる構造

中点則の誤差は画素ごとに独立ではない。同じ観測間隔に入った画素は**全部同じ推定値**に
なる（実データで2019年は41,006画素が46個の値しか取らない）。したがって
**画素ごとの誤差と、流域平均の誤差は別の量**である。計画が要るのは渓流別の融雪範囲
0.2〜3km²（30m画素で222〜3,278画素）の**平均**なので、そこを分けて測る。

## もう一つの推定器

中点則は「間隔のどこで融け切ったか分からないから真ん中」という無情報の推定である。
実際には**積雪面積率の時系列**が観測できていて、それは間隔の中でどこが濃いかを教える。
そこで面積減率曲線（ロジスティック）を観測点にあてはめ、間隔内の条件付き期待値を
返す推定器を作って、中点則と比べる。

出力: theme2_ライフライン復旧/poc/out/t2_meltout_accuracy.json
"""
import itertools
import json
import os
import re

import numpy as np

_SRC = os.path.dirname(os.path.abspath(__file__))
_POC = os.path.dirname(_SRC)
_DATA = os.path.join(_POC, "data", "snowmap")
_OUT = os.path.join(_POC, "out")

rng = np.random.default_rng(20260811)

PIXEL_AREA_KM2 = 0.03 * 0.03          # 30m グリッド
# 蔵王計画 表2-13/2-14 の渓流別融雪範囲
BASIN_AREA_KM2 = (0.20, 0.60, 1.50, 2.95)

results = {"meta": dict(
    データ="origin/snowmap-poc の snow_doy_YYYY.npy（蔵王・火口半径3km・UTM54N 30m・203×202）",
    参照値の性質="密な年の消雪日マップ。これ自体が観測間隔の量子化を持つので絶対真値ではない",
    測る量="観測密度を落としたときに増える誤差（8.6節が年数を数えた基準E[G]≤40日の妥当性）",
    画素面積km2=PIXEL_AREA_KM2)}


# ---------------------------------------------------------------
# 0. 実データの読み込みと、量子化構造の確認
# ---------------------------------------------------------------
snap = json.load(open(os.path.join(_POC, "out", "t2_snowmap_results.json")))
YEARS = sorted(int(y) for y in snap["years"])


# 【2026年8月12日】.npy は火口中心 ±3km の**矩形**（203×202画素＝41,006、四隅は火口から
# 4.3km）である。融雪型火山泥流は火口起源なので、標高の低い四隅を混ぜると系統的に早い側へ
# 引っ張られる（2022年の画素中央値は矩形 117.0 → 円 144.5 日目で、9年で2番目に早い年が
# 2番目に遅い年に入れ替わる）。以後は**半径3kmの円（31,392画素）だけ**を集計する。
#   **注意: out/*.json はこのマスクを入れる前の出力である。**この環境には numpy が入らない
#   （pip がプロキシで403）ため回し直せていない。回し直したときに何がどれだけ動くかは
#   `t2_snowmap_circle.py`（素のPythonで書いてある）の出力 downstream_effect を見ること——
#   面積平均σ 8.93→8.80、信号 7.1→6.9日、SNR 1.31→1.29 で結論は動かない。
MASK_TO_CIRCLE = True
CIRCLE_R_M = 3000.0
PIXEL_M = 30.0


def load_year(y):
    a = np.load(os.path.join(_DATA, f"snow_doy_{y}.npy")).astype(float)
    if MASK_TO_CIRCLE:
        rows, cols = a.shape
        yy, xx = np.ogrid[:rows, :cols]
        out = ((yy - (rows - 1) / 2.0) ** 2 + (xx - (cols - 1) / 2.0) ** 2
               > (CIRCLE_R_M / PIXEL_M) ** 2)
        a = a.copy()
        a[out] = np.nan
    return a


def year_dates(y):
    """'2017-04-05(la)' 形式から暦日(DOY)の昇順ユニーク列を作る"""
    out = set()
    for s in snap["years"][str(y)]["dates"]:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        mo, da = int(m.group(2)), int(m.group(3))
        cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]   # 平年
        out.add(cum[mo - 1] + da)
    return np.array(sorted(out), float)


quant = {}
for y in YEARS:
    a = load_year(y)
    v = a[~np.isnan(a)]
    d = year_dates(y)
    gaps = np.diff(d)
    quant[str(y)] = dict(
        観測日数=int(d.size), 観測間隔の中央値=float(np.median(gaps)) if gaps.size else None,
        観測間隔の最大=float(gaps.max()) if gaps.size else None,
        有効画素=int(v.size), 相異なる消雪日の個数=int(np.unique(v).size),
        消雪日の中央値=round(float(np.median(v)), 1),
        消雪日のp10_p90=[round(float(np.percentile(v, 10)), 1),
                         round(float(np.percentile(v, 90)), 1)],
        消雪日の空間標準偏差=round(float(v.std()), 1),
    )
results["quantization_structure"] = quant
n_distinct = np.mean([q["相異なる消雪日の個数"] for q in quant.values()])
results["quantization_note"] = (
    f"41,006画素の消雪日が平均{n_distinct:.0f}個の値しか取らない。"
    "同一観測間隔の画素は同一の推定値になるので、画素の誤差は互いに独立ではない")


# ---------------------------------------------------------------
# 1. 年ごとの流域平均消雪日 —— 年超過確率分布の材料そのもの
# ---------------------------------------------------------------
area_mean = {}
for y in YEARS:
    a = load_year(y)
    v = a[~np.isnan(a)]
    area_mean[str(y)] = round(float(v.mean()), 1)
am = np.array(list(area_mean.values()))
results["area_mean_meltout_doy"] = dict(
    年別=area_mean, 平均=round(float(am.mean()), 1),
    標準偏差=round(float(am.std(ddof=1)), 1),
    最早_最晩=[float(am.min()), float(am.max())],
    年数=int(am.size),
    含意="この年々変動が年超過確率分布の信号である。観測誤差はこれと比べて評価する")


# ---------------------------------------------------------------
# 2. 推定器2種
# ---------------------------------------------------------------
def midpoint_estimate(truth, dates):
    """中点則。dates で雪/無雪を判定し、最後の積雪日と次の無雪日の中点を返す"""
    d = np.sort(dates)
    est = np.full(truth.shape, np.nan)
    ok = ~np.isnan(truth)
    # 画素の真の消雪日が (d[i], d[i+1]) に入るなら推定は (d[i]+d[i+1])/2
    idx = np.searchsorted(d, truth[ok], side="right") - 1
    lo = np.where(idx >= 0, d[np.clip(idx, 0, d.size - 1)], np.nan)
    hi = np.where(idx + 1 < d.size, d[np.clip(idx + 1, 0, d.size - 1)], np.nan)
    est[ok] = (lo + hi) / 2.0
    return est


def depletion_estimate(truth, dates):
    """面積減率曲線あてはめ。間隔内の条件付き期待値を返す

    観測できるのは各観測日の積雪面積率 SCA(d)。そこにロジスティックを当て、
    間隔 (d1,d2) に入った画素へは、その間隔での分布の重心（条件付き期待値）を返す。
    中点則は SCA が間隔内で直線と仮定した場合の特殊形にあたる。
    """
    d = np.sort(dates)
    ok = ~np.isnan(truth)
    t = truth[ok]
    sca = np.array([(t > x).mean() for x in d])          # 観測される積雪面積率
    # ロジスティック SCA(x) = 1/(1+exp((x-x0)/s)) を最小二乗で当てる（格子探索＋局所詰め）
    best, bx0, bs = np.inf, float(np.median(t)), 10.0
    for x0 in np.arange(t.min() - 10, t.max() + 10, 1.0):
        for s in (3.0, 5.0, 8.0, 12.0, 18.0, 25.0):
            r = ((1.0 / (1.0 + np.exp((d - x0) / s)) - sca)**2).sum()
            if r < best:
                best, bx0, bs = r, x0, s
    for _ in range(3):                                    # 局所を詰める
        for x0 in np.linspace(bx0 - 2, bx0 + 2, 9):
            for s in np.linspace(max(bs * 0.6, 1.0), bs * 1.6, 9):
                r = ((1.0 / (1.0 + np.exp((d - x0) / s)) - sca)**2).sum()
                if r < best:
                    best, bx0, bs = r, x0, s

    def pdf(x):                                           # -dSCA/dx
        e = np.exp((x - bx0) / bs)
        return e / (bs * (1.0 + e)**2)

    est = np.full(truth.shape, np.nan)
    idx = np.searchsorted(d, t, side="right") - 1
    # 間隔ごとに条件付き期待値を1回だけ計算して配る
    cond = {}
    for i in range(-1, d.size):
        if i < 0 or i + 1 >= d.size:
            continue
        xs = np.linspace(d[i], d[i + 1], 41)
        w = pdf(xs)
        cond[i] = float((xs * w).sum() / w.sum()) if w.sum() > 0 else float((d[i] + d[i + 1]) / 2)
    vals = np.array([cond.get(int(i), np.nan) for i in idx])
    est[ok] = vals
    return est, dict(x0=round(bx0, 2), s=round(bs, 2), rss=round(float(best), 5))


# ---------------------------------------------------------------
# 3. 間引き実験
# ---------------------------------------------------------------
DENSE = [y for y in YEARS if quant[str(y)]["観測日数"] >= 10]
TARGET_N = [2, 3, 4, 6, 8]          # 残す観測日数。1984-98年のLandsat単独時代は2〜4本


def basin_means(err, shape, area_km2, n_draw=200):
    """流域（連続した正方領域）平均での誤差。実際の渓流は正方でないが規模の代表として使う"""
    side = max(int(round(np.sqrt(area_km2 / PIXEL_AREA_KM2))), 2)
    H, W = shape
    if side >= min(H, W):
        return None
    out = []
    for _ in range(n_draw):
        i = rng.integers(0, H - side)
        j = rng.integers(0, W - side)
        blk = err[i:i + side, j:j + side]
        v = blk[~np.isnan(blk)]
        if v.size >= 0.5 * side * side:
            out.append(float(v.mean()))
    return np.array(out) if out else None


decim = {}
for y in DENSE:
    truth = load_year(y)
    dates = year_dates(y)
    per_n = {}
    for n in TARGET_N:
        if n >= dates.size:
            continue
        # 実在日から等間隔に近い部分集合を複数取る（両端は必ず含める）
        combos = []
        if n == 2:
            combos = [np.array([dates[0], dates[-1]])]
        else:
            for _ in range(12):
                mid = rng.choice(dates[1:-1], size=n - 2, replace=False)
                combos.append(np.sort(np.concatenate([[dates[0]], mid, [dates[-1]]])))
        mid_rmse, mid_bias, dep_rmse, dep_bias, gaps_used = [], [], [], [], []
        basin_rmse = {f"{a}km2": [] for a in BASIN_AREA_KM2}
        for sub in combos:
            em = midpoint_estimate(truth, sub)
            ed, _fit = depletion_estimate(truth, sub)
            for est, R, B in ((em, mid_rmse, mid_bias), (ed, dep_rmse, dep_bias)):
                e = est - truth
                v = e[~np.isnan(e)]
                if v.size:
                    R.append(float(np.sqrt((v**2).mean())))
                    B.append(float(v.mean()))
            g = np.diff(np.sort(sub))
            gaps_used.append(float((g**2).sum() / g.sum()))     # E[G]（8.6節と同じ定義）
            e = em - truth
            for a in BASIN_AREA_KM2:
                bm = basin_means(e, truth.shape, a)
                if bm is not None:
                    basin_rmse[f"{a}km2"].append(float(np.sqrt((bm**2).mean())))
        per_n[f"{n}観測日"] = dict(
            EG_期待観測間隔=round(float(np.mean(gaps_used)), 1),
            中点則_画素RMSE_日=round(float(np.mean(mid_rmse)), 1),
            中点則_画素バイアス_日=round(float(np.mean(mid_bias)), 1),
            面積減率則_画素RMSE_日=round(float(np.mean(dep_rmse)), 1),
            面積減率則_画素バイアス_日=round(float(np.mean(dep_bias)), 1),
            中点則_流域平均RMSE_日={k: round(float(np.mean(v)), 1)
                                    for k, v in basin_rmse.items() if v},
        )
    decim[str(y)] = per_n
    print(f"[{y}] " + " | ".join(
        f"{k}: E[G]={v['EG_期待観測間隔']}d 画素RMSE={v['中点則_画素RMSE_日']}d "
        f"流域0.2km²={v['中点則_流域平均RMSE_日'].get('0.2km2')}d"
        for k, v in per_n.items()))
results["decimation"] = decim


# ---------------------------------------------------------------
# 4. 8.6節の前提（誤差 = E[G]/4）が実測と合うか
# ---------------------------------------------------------------
xs, ys_pix, ys_basin = [], [], []
for y, per_n in decim.items():
    for k, v in per_n.items():
        xs.append(v["EG_期待観測間隔"])
        ys_pix.append(v["中点則_画素RMSE_日"])
        b = v["中点則_流域平均RMSE_日"].get("0.2km2")
        if b is not None:
            ys_basin.append((v["EG_期待観測間隔"], b))
xs, ys_pix = np.array(xs), np.array(ys_pix)
slope_pix = float((xs * ys_pix).sum() / (xs**2).sum())      # 原点通過の当てはめ
bx = np.array([p[0] for p in ys_basin]); by = np.array([p[1] for p in ys_basin])
slope_basin = float((bx * by).sum() / (bx**2).sum())
results["check_EG_over_4"] = dict(
    節8_6の前提="消雪日の期待誤差 = E[G]/4（係数0.25）",
    実測係数_画素RMSE=round(slope_pix, 3),
    実測係数_流域平均RMSE_0_2km2=round(slope_basin, 3),
    判定_画素=("前提は妥当" if slope_pix <= 0.30 else "前提は楽観。画素ではE[G]/4より大きい"),
    判定_流域平均=("流域平均はE[G]/4より良い" if slope_basin < 0.25 else "流域平均でもE[G]/4を下回らない"),
    含意=("計画が要るのは渓流別融雪範囲(0.2〜3km²)の平均であって画素値ではないので、"
          "使うべきは流域平均側の係数である"))

# 誤差のうち、年内で共通な成分（流域平均に残る分）と画素ごとに散る成分の分離
split = {}
for y in DENSE[:3]:
    truth = load_year(y)
    dates = year_dates(y)
    sub = np.array([dates[0], dates[len(dates) // 2], dates[-1]])
    e = midpoint_estimate(truth, sub) - truth
    v = e[~np.isnan(e)]
    bm = basin_means(e, truth.shape, 0.60)
    split[str(y)] = dict(
        観測3日=list(map(float, sub)),
        全域平均誤差_日=round(float(v.mean()), 2),
        画素RMSE_日=round(float(np.sqrt((v**2).mean())), 1),
        流域0_6km2平均のRMSE_日=(round(float(np.sqrt((bm**2).mean())), 1) if bm is not None else None),
        空間平均で落ちた割合=(round(1 - float(np.sqrt((bm**2).mean()))
                                  / float(np.sqrt((v**2).mean())), 2) if bm is not None else None))
results["error_common_vs_random"] = dict(
    実測=split,
    機構=("中点則の誤差は同一観測間隔の画素で同一値になる。ただし真の消雪日が間隔内に"
          "散らばっている限り、その平均は打ち消し合う。打ち消しが効かないのは"
          "流域全体が1つの間隔の中で融け切る場合で、そのとき誤差は空間平均で落ちない"))

# 流域全体が1間隔で融け切る年はあるか（打ち消しが効かない条件の実測）
within = {}
for y in YEARS:
    truth = load_year(y)
    d = year_dates(y)
    v = truth[~np.isnan(truth)]
    idx = np.searchsorted(d, v, side="right") - 1
    frac_max = float(np.bincount(idx[idx >= 0]).max() / v.size) if v.size else None
    within[str(y)] = dict(最大の1間隔に入る画素の割合=round(frac_max, 3) if frac_max else None)
results["single_interval_risk"] = dict(
    年別=within,
    最悪年=max(within, key=lambda k: within[k]["最大の1間隔に入る画素の割合"] or 0),
    含意="1間隔に集中する割合が高い年は、空間平均でも誤差が落ちない。年ごとに開示すべき指標")

os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_meltout_accuracy.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------------- 出力 ----------------
print("\n=== 0. 量子化構造（実データ）===")
for y, q in quant.items():
    print(f"  {y}: 観測{q['観測日数']}日（間隔中央{q['観測間隔の中央値']}d/最大{q['観測間隔の最大']}d）"
          f" 有効{q['有効画素']}px → 相異なる消雪日 {q['相異なる消雪日の個数']}個"
          f" 空間σ={q['消雪日の空間標準偏差']}d")

print("\n=== 1. 流域平均消雪日の年々変動（年超過確率分布の信号）===")
a = results["area_mean_meltout_doy"]
print(f"  {a['年別']}")
print(f"  平均 {a['平均']} / 標準偏差 {a['標準偏差']}日 / 幅 {a['最早_最晩']} / {a['年数']}年")

print("\n=== 3. 間引き実験（中点則 対 面積減率則）===")
for y, per_n in decim.items():
    for k, v in per_n.items():
        print(f"  {y} {k}: E[G]={v['EG_期待観測間隔']:5.1f}d → "
              f"中点則 画素{v['中点則_画素RMSE_日']:4.1f}d / 面積減率則 画素{v['面積減率則_画素RMSE_日']:4.1f}d"
              f" / 中点則 流域平均 " + ", ".join(f"{kk}={vv}d" for kk, vv in
                                                v['中点則_流域平均RMSE_日'].items()))

print("\n=== 4. 8.6節の前提（E[G]/4）の検証 ===")
c = results["check_EG_over_4"]
print(f"  画素RMSE の実測係数 {c['実測係数_画素RMSE']}（前提0.25）→ {c['判定_画素']}")
print(f"  流域0.2km²平均の実測係数 {c['実測係数_流域平均RMSE_0_2km2']} → {c['判定_流域平均']}")
print("\n=== 誤差の共通成分と画素成分 ===")
for y, s in split.items():
    print(f"  {y}: 画素RMSE {s['画素RMSE_日']}d → 流域0.6km²平均 {s['流域0_6km2平均のRMSE_日']}d"
          f"（{s['空間平均で落ちた割合']*100 if s['空間平均で落ちた割合'] else 0:.0f}%低減）"
          f" 全域平均バイアス {s['全域平均誤差_日']:+.2f}d")
print("\n=== 1間隔に集中する割合（空間平均が効かない条件）===")
for y, w in within.items():
    print(f"  {y}: {w['最大の1間隔に入る画素の割合']}")
print(f"  最悪年 {results['single_interval_risk']['最悪年']}")
