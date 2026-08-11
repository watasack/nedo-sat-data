"""消雪日からの後退積算（snow reconstruction）は、計画が要る量を返すか

候補案の中核は「光学衛星の多年アーカイブから消雪日マップを作り、後退積算で
積雪水量(SWE)を復元して、火口周辺の年超過確率分布を出す」である。

ここで潰すのは型②（物理を精密に解くと信号が消える）。懸念は2つある。

  (a) reconstruction が返すのは「ある日から消雪日までの積算融雪量」であって、
      その日以降に降った雪もそこに含まれてしまう。つまり**ピーク後の降雪の分だけ
      年最大SWEを過大評価する**。日本海側の1700m級は4-5月も降るので効きうる。
  (b) 融雪モデル（degree-day）の誤差。文献値は SWE RMSE 20-50cm 級。

そして判定すべきは「誤差が絶対値として大きいか」ではなく、
**この案が答えると言っている量（年超過確率分布）に対して十分か**である。
年ごとのランダム誤差は N年で 1/sqrt(N) に落ちるが、系統誤差は落ちない。
そこを分けて評価する。

**この試算の限界（先に書く）**

節1・4・5は、復元側に「真の融雪開始日」と「真の融雪係数(DDF)」を与えている。
つまり循環しており、誤差が小さく出るのは当然である。**これらの数字を
「reconstruction は正確だ」の根拠に使ってはいけない。**

循環していないのは節2（DDFの不確かさ）と節3（信号との比較）だけである。
そこから言えることは2つ:

  - 文献のDDFの幅 3-6 mm/C/day は、そのまま **±33% の系統スケール誤差** になる。
    これは年数を増やしても落ちない。
  - ただし信号（計画1334mm vs 実測385mm ＝ 3.5倍）に対しては ±33% は致命的でない。
    DDFを外しても 385 と 1334 は取り違えない。

そして系統スケール誤差は、**1年分の地上実測があれば較正できる**。
蔵王には2023年3月のUAV実測がある。つまり「計画が過大である証拠」として使う
実測が、同時に「手法の較正データ」でもある。

節1が示した唯一の非循環な知見は、**ピーク後の降雪による汚染がこの気候では
小さい**こと（降雪の2.3%、バイアス約1%）。当初これを最大の懸念としていたが、
機構としては効いている（相関0.63）ものの量が小さい。

出力: theme2_ライフライン復旧/poc/out/t2_snow_reconstruction.json
"""
import json
import os

import numpy as np

rng = np.random.default_rng(20260809)

# ---- 蔵王山1700m級を想定した気候パラメータ ----
# 気温: 標高1700m。山形(153m)の平年から気温減率6.5K/kmで外挿すると年平均 約1.5C
T_MEAN, T_AMP, T_PEAK_DOY = 1.5, 11.0, 205        # 日平均気温の年変化
T_MELT = 0.0                                       # 融解開始温度 [C]
DDF = 4.5                                          # degree-day factor [mm/C/day]
T_SNOW = 1.0                                       # 降水の雪/雨の判別温度 [C]

# 降水: 日本海側は12-2月に極大。年降水2400mm、冬季偏重
P_ANNUAL, P_WINTER_FRAC = 2400.0, 0.55
# 水年（10月1日起点）で回す。暦年だと年末の積雪＝翌シーズン分を消雪日として拾う
WY = np.arange(1, 366)
DOY = ((WY - 1 + 273) % 365) + 1          # 水年日 -> 暦日


def air_temp(doy):
    return T_MEAN + T_AMP * np.cos(2 * np.pi * (doy - T_PEAK_DOY) / 365.0)


def precip_shape(doy):
    """冬季（12-2月）に偏った降水の季節配分"""
    w = 1.0 + P_WINTER_FRAC * 2.0 * np.cos(2 * np.pi * (doy - 15) / 365.0)
    return np.clip(w, 0.05, None)


def run_season(p_scale=1.0, t_offset=0.0, weather_noise=True):
    """1シーズンを日単位で回し、真のSWE時系列と消雪日を返す"""
    T = air_temp(DOY) + t_offset
    if weather_noise:
        T = T + rng.normal(0, 2.5, DOY.size)        # 総観規模の変動
    w = precip_shape(DOY)
    P = P_ANNUAL * p_scale * w / w.sum()
    if weather_noise:
        P = P * rng.gamma(1.4, 1 / 1.4, DOY.size)   # 降水の間欠性

    snowfall = np.where(T < T_SNOW, P, 0.0)
    swe = np.zeros(DOY.size)
    s = 0.0
    for i in range(DOY.size):
        s = s + snowfall[i]
        melt = min(s, DDF * max(0.0, T[i] - T_MELT))
        s = s - melt
        swe[i] = s
    # 消雪日: 「最長の連続積雪期間」の末日。単に swe>0 の最終日を取ると、
    # 融け切ったあとの孤立した降雪日を拾って消雪日が後ろへ引っ張られる
    # （実運用でも積雪面積率の時系列で連続期間を切り出す）。
    on = swe > 0
    best_len, best_end, cur = 0, 0, 0
    for i, v in enumerate(on):
        cur = cur + 1 if v else 0
        if cur > best_len:
            best_len, best_end = cur, i
    sdd = best_end + 1 if best_len > 0 else 0
    onset = int(np.argmax(swe[max(best_end - best_len, 0):best_end + 1])) \
        + max(best_end - best_len, 0) if best_len else 0
    return dict(T=T, snowfall=snowfall, swe=swe, sdd=sdd, onset=onset)


def reconstruct(season, ddf_used=DDF, t_bias=0.0):
    """消雪日から融雪開始日まで後退積算する。

    実際の手法は「積雪面積率が1を割った日＝融雪開始日」までしか遡らない。
    水年初日まで遡ると、雪が無い秋の正の度日まで融雪として積んでしまう。
    融雪開始日は、単一地点では真のピーク日で近似する（面的には fSCA の
    立ち下がりで観測できる量）。
    """
    T = season["T"] + t_bias
    sdd = season["sdd"]
    if sdd == 0:
        return np.zeros(WY.size), 0.0
    melt_pot = ddf_used * np.clip(T - T_MELT, 0, None)
    onset = int(season["onset"])                    # 融雪開始日（fSCAの立ち下がり）
    rec = np.zeros(WY.size)
    acc = 0.0
    for i in range(sdd - 1, onset - 1, -1):
        acc = acc + melt_pot[i]
        rec[i] = acc
    return rec, float(rec[onset])


results = {}

# ===== 1. 単年での過大評価バイアス（ピーク後の降雪の混入）=====
N_YEARS = 60
true_max, rec_max, sdds, post_peak = [], [], [], []
for _ in range(N_YEARS):
    s = run_season(p_scale=float(rng.lognormal(0, 0.30)))   # 年々変動 CV約0.31
    r, rmax = reconstruct(s)
    true_max.append(float(s["swe"][s["onset"]]))
    rec_max.append(rmax)
    sdds.append(s["sdd"])
    # ピーク日以降に降った雪の割合。これが過大評価の機構そのもの
    ipk = int(s["onset"])
    post_peak.append(float(s["snowfall"][ipk:].sum() / max(s["snowfall"].sum(), 1e-9)))
true_max, rec_max = np.array(true_max), np.array(rec_max)
post_peak = np.array(post_peak)
ratio = rec_max / true_max

results["single_year_bias"] = dict(
    真の年最大SWE_平均_mm=round(float(true_max.mean()), 1),
    真の年最大SWE_CV=round(float(true_max.std() / true_max.mean()), 3),
    復元の年最大SWE_平均_mm=round(float(rec_max.mean()), 1),
    比_復元_割る_真_平均=round(float(ratio.mean()), 3),
    比_標準偏差=round(float(ratio.std()), 3),
    系統バイアス_mm=round(float((rec_max - true_max).mean()), 1),
    ランダム誤差_RMSE_mm=round(float(np.sqrt((((rec_max - true_max)
                                            - (rec_max - true_max).mean())**2).mean())), 1),
    消雪日_平均_暦日=round(float(np.mean([((d - 1 + 273) % 365) + 1 for d in sdds])), 1),
    ピーク後に降る雪の割合_平均=round(float(post_peak.mean()), 3),
    ピーク後降雪割合と過大評価比の相関=round(float(np.corrcoef(post_peak, ratio)[0, 1]), 3),
)

# ===== 2. 融雪モデル誤差の寄与 =====
# DDF は文献で 3-6 mm/C/day の幅がある。使う値を外すとどうなるか。
ddf_sens = {}
s_ref = run_season(p_scale=1.0)
_, base = reconstruct(s_ref, ddf_used=DDF)
for ddf in (3.0, 3.75, 4.5, 5.25, 6.0):
    _, v = reconstruct(s_ref, ddf_used=ddf)
    ddf_sens[f"DDF={ddf:.2f}"] = dict(復元SWE_mm=round(v, 1),
                                      基準比=round(v / base, 3))
results["ddf_sensitivity"] = ddf_sens

# ===== 3. 判定その1: 計画値と実測値の食い違いを検出できるか =====
# 蔵王計画 3.81m × 密度0.35 = 1334 mm SWE、UAV実測 1.1m × 0.35 = 385 mm SWE
PLAN_SWE, OBS_SWE = 3.81 * 350.0, 1.1 * 350.0
signal = PLAN_SWE - OBS_SWE
noise_single = float(np.sqrt(results["single_year_bias"]["ランダム誤差_RMSE_mm"]**2
                            + (0.15 * OBS_SWE)**2))   # DDF不確かさ15%ぶんを加算
results["detect_plan_vs_obs"] = dict(
    計画のSWE_mm=round(PLAN_SWE, 1), 実測のSWE_mm=round(OBS_SWE, 1),
    信号_mm=round(signal, 1), 単年の雑音_mm=round(noise_single, 1),
    SNR=round(signal / noise_single, 2),
    判定="検出できる" if signal / noise_single >= 3 else
         "限界域" if signal / noise_single >= 1.5 else "不可")

# ===== 4. 判定その2: 年超過確率分布を作れるか（ここが本命）=====
# ランダム誤差は N年で 1/sqrt(N) に落ちるが、系統バイアスは落ちない。
# 分布のパラメータ（平均・標準偏差）と、そこから出る再現期待値への影響を見る。
def gumbel_quantile(mean, std, T_years):
    """モーメント法のGumbel。beta = std*sqrt(6)/pi, mu = mean - 0.5772*beta"""
    beta = std * np.sqrt(6.0) / np.pi
    mu = mean - 0.5772 * beta
    return mu - beta * np.log(-np.log(1.0 - 1.0 / T_years))


quant = {}
for n in (20, 40, 60):
    idx = slice(0, n)
    t_m, t_s = true_max[idx].mean(), true_max[idx].std(ddof=1)
    r_m, r_s = rec_max[idx].mean(), rec_max[idx].std(ddof=1)
    row = {}
    for T_y in (2, 10, 100):
        qt, qr = gumbel_quantile(t_m, t_s, T_y), gumbel_quantile(r_m, r_s, T_y)
        row[f"{T_y}年確率"] = dict(真_mm=round(float(qt), 1), 復元_mm=round(float(qr), 1),
                                  誤差_pct=round(100 * (qr - qt) / qt, 1))
    quant[f"{n}年分のアーカイブ"] = row
results["quantile_estimation"] = quant

# ===== 5. 系統バイアスを較正できる場合 =====
# UAV実測やLP測量が1年でもあれば、その年でバイアスを較正できる。
bias_factor = float((rec_max / true_max).mean())
cal = {}
for n in (20, 40):
    idx = slice(0, n)
    t_m, t_s = true_max[idx].mean(), true_max[idx].std(ddof=1)
    r_m, r_s = (rec_max[idx] / bias_factor).mean(), (rec_max[idx] / bias_factor).std(ddof=1)
    row = {}
    for T_y in (2, 10, 100):
        qt, qr = gumbel_quantile(t_m, t_s, T_y), gumbel_quantile(r_m, r_s, T_y)
        row[f"{T_y}年確率"] = dict(誤差_pct=round(100 * (qr - qt) / qt, 1))
    cal[f"{n}年分・バイアス較正あり"] = row
results["quantile_after_calibration"] = cal
results["bias_factor"] = round(bias_factor, 3)

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_snow_reconstruction.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------- 出力 ----------
b = results["single_year_bias"]
print("=== 1. 単年の復元バイアス（ピーク後の降雪が混入する分）===")
for k, v in b.items():
    print(f"  {k}: {v}")

print("\n=== 2. 融雪モデル(DDF)の不確かさ ===")
for k, v in ddf_sens.items():
    print(f"  {k}: 復元SWE {v['復元SWE_mm']} mm（基準比 {v['基準比']}）")

print("\n=== 3. 計画値 vs UAV実測 の食い違いを単年で検出できるか ===")
d = results["detect_plan_vs_obs"]
print(f"  計画 {d['計画のSWE_mm']} mm / 実測 {d['実測のSWE_mm']} mm")
print(f"  信号 {d['信号_mm']} mm / 雑音 {d['単年の雑音_mm']} mm → SNR {d['SNR']} → {d['判定']}")

print("\n=== 4. 年超過確率分布の推定誤差（バイアス較正なし）===")
for n, row in quant.items():
    print(f"  {n}")
    for T_y, v in row.items():
        print(f"      {T_y}: 真 {v['真_mm']} mm / 復元 {v['復元_mm']} mm → {v['誤差_pct']:+.1f}%")

print(f"\n=== 5. バイアス係数 {results['bias_factor']} で較正した場合 ===")
for n, row in cal.items():
    print(f"  {n}: " + ", ".join(f"{T_y} {v['誤差_pct']:+.1f}%" for T_y, v in row.items()))
