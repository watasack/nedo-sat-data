"""テーマ2 PoC: 年超過確率分布の標本不確かさを、非循環で出す

## 直す対象

`t2_snow_reconstruction.py` の節4は「年超過確率分布を作れるか（ここが本命）」と題して
**20年分のアーカイブで100年確率の誤差 0.9%** と出している。これは成り立たない。
理由は節4が循環しているからである——真値側の分位点も復元側の分位点も**同じ20標本**から
モーメント法で出しているので、**標本不確かさが定義上打ち消される**。あの0.9%は
「復元がSWEを何%外すか」しか測っておらず、「20年で100年確率が決まるか」は測っていない。

再現期間100年の値を20標本から推定したときの不確かさは、数十%の桁になる。
提出物の売りが「年超過確率分布」である以上、ここを空けたままにはできない。

さらに節4は**消雪日の観測誤差を1回も入れていない**（復元側に真の消雪日を渡している）。
`t2_meltout_accuracy.py` で実測したとおり、消雪日は流域平均でも E[G]≈40日の年に
7〜10日の誤差を持つ。年ごとに独立な誤差は**分布の分散を膨らませる**ので、
超過確率の裾を**過大**に押し上げる。向きまで含めて評価する。

## この案にとって都合の良い構造が1つある（DDFが消える）

reconstruction は SWE = Σ(融雪ポテンシャル) を融雪開始日から消雪日まで積む。
一次近似では **SWE ≒ M × (消雪日 − 融雪開始日)**（M＝期間平均の融雪速度）。
すると年超過確率分布を「平年比」で表したとき、**M も DDF も密度も約分される**。

  q(T)/q(2) = (D(T) − D0) / (D(2) − D0)

つまり `t2_snow_reconstruction.py` 節2が挙げた **DDFの幅3〜6 mm/C/day＝±33%の系統
スケール誤差は、比で表す限り分布の形には効かない**。効くのは絶対値だけである。
そして計画が実際に要求しているのは既往最大・年超過確率という**順序と比**であり、
絶対値は下流の泥流量計算に入るところで1回だけ効く。

同じ理由で、**信号対雑音は日の単位で評価できる**——
  信号 = 流域平均消雪日の年々変動（実測 標準偏差8.9日／9年）
  雑音 = 流域平均消雪日の観測誤差（実測 0.217×E[G]）
比を取るとMもDDFも消える。**この案の成否は mm ではなく日で決まる。**

ただし**信号の8.9日そのものが観測誤差を含んでいる**。9年分は E[G]≈25日の時代なので
観測誤差σ≈5.4日が乗っており、真の年々変動は sqrt(8.9²−5.4²)＝7.1日しかない。
信号対雑音はこの7.1日で評価する（8.9日で評価すると自分に甘い）。

## 出力

theme2_ライフライン復旧/poc/out/t2_return_period.json

**この試算に循環はない。** 真の分布は生成側にだけあり、推定側は毎回独立に引いた標本しか
見ていない。真値と推定を同じ標本から作っている箇所は無い。
"""
import json
import os

import numpy as np

_SRC = os.path.dirname(os.path.abspath(__file__))
_POC = os.path.dirname(_SRC)
_OUT = os.path.join(_POC, "out")

rng = np.random.default_rng(20260811)
N_BOOT = 4000

# ---------------------------------------------------------------
# 実測から取る入力（すべて他PoCの出力。ここで新しい仮定は置かない）
# ---------------------------------------------------------------
acc = json.load(open(os.path.join(_OUT, "t2_meltout_accuracy.json")))
SIG_INTERANNUAL = acc["area_mean_meltout_doy"]["標準偏差"]        # 8.9日（9年の実測）
MEAN_MELTOUT = acc["area_mean_meltout_doy"]["平均"]              # 128.1（暦日）
N_OBS_YEARS = acc["area_mean_meltout_doy"]["年数"]               # 9
ERR_COEF = acc["check_EG_over_4"]["実測係数_流域平均RMSE_0_2km2"]  # 0.217（流域平均・実測）

# 融雪開始日。8.4節の設計では fSCA の立ち下がりで観測する量。
# 平均消雪日 128.1 に対し、蔵王の融雪期間を4〜6週間として D0 を置く（下で感度を取る）
MELT_DURATION_MEAN = 30.0     # 日。平均年の融雪期間（融雪開始→消雪）
D0 = MEAN_MELTOUT - MELT_DURATION_MEAN

# ---- 信号そのものが観測誤差で膨らんでいる ----
# SIG_INTERANNUAL=8.9日は**観測された**流域平均消雪日の標準偏差である。
# 9年分（2017-2025）はE[G]≈25日の時代なので観測誤差σ≈5.4日を含んでいる。
# 真の年々変動は sqrt(8.9^2 - 5.4^2) しかない。ここを直さずに信号として使うと、
# 信号を過大に、信号対雑音を楽観に見積もる。**両方を並記して使う。**
SIG_ERR_MODERN = 0.217 * 25.0
SIG_INTERANNUAL_RAW = SIG_INTERANNUAL
SIG_INTERANNUAL_DECONV = float(np.sqrt(max(SIG_INTERANNUAL**2 - SIG_ERR_MODERN**2, 1e-6)))

# 8.6節が数えた E[G] の水準（時代別）
EG_ERAS = {
    "IV_2017-26_Landsat+Sentinel2": 25.0,
    "III_2013-16": 40.0,
    "II_1999-2012": 40.0,
    "I_1984-98_Landsat単独": 80.0,
    "8.6節の合否ライン": 40.0,
}
RETURN_PERIODS = (2, 10, 20, 50, 100)
N_GRID = (9, 15, 20, 25, 30, 43)

results = {"meta": dict(
    信号_流域平均消雪日の年々変動_観測値_日=SIG_INTERANNUAL_RAW,
    信号_観測誤差を差し引いた真の年々変動_日=round(SIG_INTERANNUAL_DECONV, 2),
    信号の補正=("9年の実測σ8.9日はE[G]≈25日の時代の観測誤差σ5.4日を含む。"
                f"真の年々変動は{SIG_INTERANNUAL_DECONV:.1f}日。信号対雑音はこちらで評価する"),
    実測年数=N_OBS_YEARS,
    観測誤差の実測係数=f"流域平均RMSE = {ERR_COEF} × E[G]（t2_meltout_accuracy.py）",
    平均融雪期間_日=MELT_DURATION_MEAN,
    循環の有無="なし。真の分布は生成側のみ。推定は毎回独立標本から",
    ブートストラップ反復=N_BOOT,
    注="mm換算は融雪速度Mに比例するだけなので、判定は日の単位で行う")}


# ---------------------------------------------------------------
# 1. 日→mm の換算係数（報告用。判定には使わない）
# ---------------------------------------------------------------
def melt_rate_mm_per_day(doy, ddf, t_mean=1.5, t_amp=11.0, t_peak=205):
    T = t_mean + t_amp * np.cos(2 * np.pi * (doy - t_peak) / 365.0)
    return ddf * max(T, 0.0)


rate = {}
for ddf in (3.0, 4.5, 6.0):
    rate[f"DDF={ddf}"] = {f"消雪日DOY{d}": round(melt_rate_mm_per_day(d, ddf), 1)
                          for d in (110, 128, 145)}
results["day_to_mm"] = dict(
    融雪速度_mm_per_day=rate,
    含意=("1日の消雪日誤差は DDF と時期により 3〜60 mm の SWE 誤差になる。"
          "同じ係数が信号にも掛かるので、比で見る限りこの幅は判定に効かない"))


# ---------------------------------------------------------------
# 2. Gumbel の当てはめ（L-モーメント法）と分位点
# ---------------------------------------------------------------
def fit_gumbel_lmom(x):
    """L-モーメント法。小標本でモーメント法より安定"""
    xs = np.sort(np.asarray(x, float))
    n = xs.size
    l1 = xs.mean()
    i = np.arange(1, n + 1)
    l2 = (2.0 / (n * (n - 1)) * ((i - 1) * xs).sum()) - l1
    beta = l2 / np.log(2.0)
    mu = l1 - 0.5772156649 * beta
    return mu, beta


def gumbel_quantile(mu, beta, T):
    return mu - beta * np.log(-np.log(1.0 - 1.0 / T))


# 真の分布: 流域平均消雪日 ~ Gumbel（平均 MEAN_MELTOUT、標準偏差 SIG_INTERANNUAL_DECONV）
# **観測誤差を差し引いた側**を真の分布に置く。こうすると bootstrap で観測誤差を
# 足し戻したときの観測σが実測の8.9日に一致し、生成側と実データが整合する。
BETA_TRUE = SIG_INTERANNUAL_DECONV * np.sqrt(6.0) / np.pi
MU_TRUE = MEAN_MELTOUT - 0.5772156649 * BETA_TRUE
TRUE_Q = {T: gumbel_quantile(MU_TRUE, BETA_TRUE, T) for T in RETURN_PERIODS}
# 融雪期間（=SWEに比例する量）に直す
TRUE_DUR = {T: TRUE_Q[T] - D0 for T in RETURN_PERIODS}
results["true_distribution"] = dict(
    分布="Gumbel（消雪日）", mu=round(MU_TRUE, 2), beta=round(BETA_TRUE, 2),
    真の分位点_暦日={f"{T}年": round(TRUE_Q[T], 1) for T in RETURN_PERIODS},
    真の融雪期間_日={f"{T}年": round(TRUE_DUR[T], 1) for T in RETURN_PERIODS},
    真の平年比={f"{T}年": round(TRUE_DUR[T] / TRUE_DUR[2], 3) for T in RETURN_PERIODS})


def draw(n):
    u = rng.random(n)
    return MU_TRUE - BETA_TRUE * np.log(-np.log(u))


# ---------------------------------------------------------------
# 3. 標本不確かさだけ（観測誤差なし）—— 節4が測れていなかった量
# ---------------------------------------------------------------
def bootstrap(n, sig_err=0.0, deconv=False, n_boot=N_BOOT):
    """n年の標本から q(T) を推定する操作を n_boot 回繰り返す

    sig_err: 年ごとに独立な観測誤差の標準偏差（日）
    deconv : 分散デコンボリューション（観測分散から誤差分散を差し引く）を行うか
    """
    out = {T: [] for T in RETURN_PERIODS}
    ratio = {T: [] for T in RETURN_PERIODS}
    for _ in range(n_boot):
        x = draw(n)
        if sig_err > 0:
            x = x + rng.normal(0, sig_err, n)
        mu, beta = fit_gumbel_lmom(x)
        if deconv and sig_err > 0:
            # 観測標本の分散には誤差分散が乗っている。Gumbel の分散は (pi*beta)^2/6 なので
            # そこから誤差分散を引いて beta を作り直す。mu は平均を保つように再構成する。
            var_obs = (np.pi * beta)**2 / 6.0
            var_cor = max(var_obs - sig_err**2, 1e-6)
            beta_c = np.sqrt(var_cor) * np.sqrt(6.0) / np.pi
            mean_obs = mu + 0.5772156649 * beta
            mu, beta = mean_obs - 0.5772156649 * beta_c, beta_c
        for T in RETURN_PERIODS:
            q = gumbel_quantile(mu, beta, T)
            out[T].append(q - D0)                       # 融雪期間（SWEに比例）
            ratio[T].append((q - D0) / max(gumbel_quantile(mu, beta, 2) - D0, 1e-6))
    rep = {}
    for T in RETURN_PERIODS:
        a = np.array(out[T])
        r = np.array(ratio[T])
        tr = TRUE_DUR[T]
        rep[f"{T}年"] = dict(
            中央値_日=round(float(np.median(a)), 1),
            真値_日=round(tr, 1),
            中央バイアス_pct=round(100 * (float(np.median(a)) - tr) / tr, 1),
            下限90_pct=round(100 * (float(np.percentile(a, 5)) - tr) / tr, 1),
            上限90_pct=round(100 * (float(np.percentile(a, 95)) - tr) / tr, 1),
            幅90_pct=round(100 * (float(np.percentile(a, 95))
                                  - float(np.percentile(a, 5))) / tr, 1),
            平年比の中央値=round(float(np.median(r)), 3),
            平年比の真値=round(TRUE_DUR[T] / TRUE_DUR[2], 3),
            平年比の幅90_pct=round(100 * (float(np.percentile(r, 95))
                                         - float(np.percentile(r, 5)))
                                  / (TRUE_DUR[T] / TRUE_DUR[2]), 1),
        )
    return rep


sampling_only = {f"{n}年": bootstrap(n) for n in N_GRID}
results["sampling_uncertainty_only"] = sampling_only
print("=== 3. 標本不確かさだけ（観測誤差なし）: 90%区間の幅（真値に対する%）===")
print("      年数 " + "".join(f"{T:>4}年 " for T in RETURN_PERIODS))
for k, rep in sampling_only.items():
    print(f"  {k:>6} " + "".join(f"{rep[f'{T}年']['幅90_pct']:>5.0f}% " for T in RETURN_PERIODS))


# ---------------------------------------------------------------
# 4. 観測誤差を入れる（節4が入れていなかった項）
# ---------------------------------------------------------------
# 観測誤差は流域平均の消雪日誤差。融雪開始日も同じ精度で観測するなら独立2端点で sqrt(2) 倍。
ENDPOINTS = {"消雪日のみ": 1.0, "消雪日+融雪開始日": np.sqrt(2.0)}
with_err = {}
for era, eg in EG_ERAS.items():
    sig_err_base = ERR_COEF * eg
    for ep_label, ep_mult in ENDPOINTS.items():
        s = sig_err_base * ep_mult
        key = f"{era} (E[G]={eg:.0f}d, σ誤差={s:.1f}d, {ep_label})"
        with_err[key] = dict(
            信号対雑音=round(SIG_INTERANNUAL / s, 2),
            誤差なし_20年=sampling_only["20年"],
            誤差あり_20年=bootstrap(20, sig_err=s),
            誤差あり_20年_デコンボリューション後=bootstrap(20, sig_err=s, deconv=True),
        )
results["with_observation_error"] = {
    k: {kk: vv for kk, vv in v.items() if kk != "誤差なし_20年"}
    for k, v in with_err.items()}

print("\n=== 4. 観測誤差を入れたとき（20年標本）===")
print("  時代 / 信号対雑音 / 20年確率の中央バイアス（補正なし→デコンボリューション後）")
for k, v in with_err.items():
    a = v["誤差あり_20年"]["20年"]["中央バイアス_pct"]
    b = v["誤差あり_20年_デコンボリューション後"]["20年"]["中央バイアス_pct"]
    print(f"  {k}: SNR={v['信号対雑音']} → {a:+.1f}% → {b:+.1f}%")


# ---------------------------------------------------------------
# 5. 信号対雑音そのもの —— この案の成否は日で決まる
# ---------------------------------------------------------------
snr_tab = {}
for era, eg in EG_ERAS.items():
    s1 = ERR_COEF * eg
    snr_tab[era] = dict(
        EG_日=eg, 流域平均の観測誤差_日=round(s1, 1),
        信号_真の年々変動_日=round(SIG_INTERANNUAL_DECONV, 1),
        SNR_消雪日のみ=round(SIG_INTERANNUAL_DECONV / s1, 2),
        SNR_両端点=round(SIG_INTERANNUAL_DECONV / (s1 * np.sqrt(2)), 2),
        観測分散が全分散に占める割合=round(s1**2 / (s1**2 + SIG_INTERANNUAL_DECONV**2), 3),
        参考_未補正の観測σ8_9日で見たSNR=round(SIG_INTERANNUAL_RAW / s1, 2),
    )
results["snr_in_days"] = dict(
    時代別=snr_tab,
    含意=("8.6節は「±10日精度（E[G]≤40日）で使える年数」で年数を数えたが、"
          "年超過確率分布に効くのは絶対精度ではなく**年々変動に対する比**である。"
          "E[G]=40日では観測誤差が年々変動と同程度になり、その年は分布の形に"
          "ほとんど寄与しない。年数の数え方を E[G]≤40 から改める必要がある"))

print("\n=== 5. 信号対雑音（日の単位。DDFもMも約分される）===")
for era, v in snr_tab.items():
    print(f"  {era}: E[G]={v['EG_日']}d → 観測誤差{v['流域平均の観測誤差_日']}d vs 真の年々変動{v['信号_真の年々変動_日']}d"
          f" → SNR {v['SNR_消雪日のみ']}（両端点 {v['SNR_両端点']}）"
          f" 観測分散の占有 {v['観測分散が全分散に占める割合']*100:.0f}%")


# ---------------------------------------------------------------
# 6. E[G] の合否ラインを引き直す
# ---------------------------------------------------------------
# 「観測分散が全分散の20%以下」を新しい合否ラインとして、必要な E[G] を解く
targets = {}
for frac in (0.10, 0.20, 0.30, 0.50):
    s_allow = SIG_INTERANNUAL_DECONV * np.sqrt(frac / (1 - frac))
    targets[f"観測分散を全分散の{frac:.0%}以下に抑える"] = dict(
        許容される流域平均誤差_日=round(s_allow, 1),
        必要なEG_日=round(s_allow / ERR_COEF, 1),
        必要なEG_両端点_日=round(s_allow / (ERR_COEF * np.sqrt(2)), 1))
results["revised_EG_criterion"] = dict(
    表=targets,
    旧基準="E[G]≤40日（画素の消雪日精度±10日から）",
    基準に使った信号=f"真の年々変動 {SIG_INTERANNUAL_DECONV:.1f}日（観測σ8.9日から観測誤差を差し引いたもの）",
    注="この線は蔵王の年々変動8.9日に対するもの。年々変動が大きい火山では緩む")
print(f"\n=== 6. E[G] の合否ラインの引き直し（蔵王の真の年々変動 {SIG_INTERANNUAL_DECONV:.1f}日に対して）===")
for k, v in targets.items():
    print(f"  {k}: 許容誤差 {v['許容される流域平均誤差_日']}d → 必要E[G] {v['必要なEG_日']}d"
          f"（両端点なら {v['必要なEG_両端点_日']}d）")


# ---------------------------------------------------------------
# 7. 何年あれば何年確率まで言えるか（誤差込み・デコンボリューション後）
# ---------------------------------------------------------------
sig_modern = ERR_COEF * EG_ERAS["IV_2017-26_Landsat+Sentinel2"]
adequacy = {}
for n in N_GRID:
    rep = bootstrap(n, sig_err=sig_modern, deconv=True)
    adequacy[f"{n}年"] = {f"{T}年確率": dict(
        幅90_pct=rep[f"{T}年"]["幅90_pct"],
        中央バイアス_pct=rep[f"{T}年"]["中央バイアス_pct"],
        平年比の幅90_pct=rep[f"{T}年"]["平年比の幅90_pct"],
        判定=("使える" if abs(rep[f"{T}年"]["幅90_pct"]) <= 30 else
              "限界域" if abs(rep[f"{T}年"]["幅90_pct"]) <= 60 else "外挿として開示"))
        for T in RETURN_PERIODS}
results["adequacy_by_years"] = dict(
    観測誤差=f"σ={sig_modern:.1f}日（E[G]=25日・現代の観測密度）",
    表=adequacy,
    判定線="90%区間の幅が真値の30%以内なら使える、60%以内なら限界域")
print("\n=== 7. 年数 × 再現期間（現代の観測密度・デコンボリューション後）: 90%区間の幅 ===")
print("      年数 " + "".join(f"{T:>7}年 " for T in RETURN_PERIODS))
for k, row in adequacy.items():
    print(f"  {k:>6} " + "".join(f"{row[f'{T}年確率']['幅90_pct']:>7.0f}% " for T in RETURN_PERIODS))
print("  （平年比で表した場合の幅）")
for k, row in adequacy.items():
    print(f"  {k:>6} " + "".join(f"{row[f'{T}年確率']['平年比の幅90_pct']:>7.0f}% " for T in RETURN_PERIODS))


# ---------------------------------------------------------------
# 7b. デコンボリューションは σ誤差 を知っている前提に乗っている
# ---------------------------------------------------------------
# 実務では σ誤差 は E[G] から実測係数 0.217 で推定する。この推定を外したらどうなるか。
# 外し方は2方向あって、**過大に見積もる方が危ない**（引きすぎて裾を過小にする＝危険側）。
mis = {}
for f in (0.5, 0.7, 1.0, 1.3, 1.5):
    used = sig_modern * f
    out = {T: [] for T in RETURN_PERIODS}
    for _ in range(1500):
        x = draw(20) + rng.normal(0, sig_modern, 20)     # 真の誤差は sig_modern
        mu, beta = fit_gumbel_lmom(x)
        var_obs = (np.pi * beta)**2 / 6.0
        var_cor = max(var_obs - used**2, 1e-6)           # 引くのは誤って見積もった値
        beta_c = np.sqrt(var_cor) * np.sqrt(6.0) / np.pi
        mu = (mu + 0.5772156649 * beta) - 0.5772156649 * beta_c
        for T in RETURN_PERIODS:
            out[T].append(gumbel_quantile(mu, beta_c, T) - D0)
    mis[f"σ誤差を{f:.0%}に見積もる（真は{sig_modern:.1f}日→使うのは{used:.1f}日）"] = {
        f"{T}年の中央バイアス_pct": round(100 * (float(np.median(out[T])) - TRUE_DUR[T])
                                         / TRUE_DUR[T], 1) for T in RETURN_PERIODS}
results["deconvolution_robustness"] = dict(
    表=mis,
    危険側="σ誤差を過大に見積もると分散を引きすぎ、超過確率の裾を過小に出す（防災上の危険側）",
    運用="σ誤差は年ごとにE[G]から算出できるので、過大側に倒さない値（下限側）を使う")
print("\n=== 7b. デコンボリューションのσ誤差の誤りに対する頑健性（20年標本）===")
for k, row in mis.items():
    print(f"  {k}: " + ", ".join(f"{kk.replace('の中央バイアス_pct','')}={vv:+.1f}%"
                                 for kk, vv in row.items()))


# ---------------------------------------------------------------
# 8. 現行手法（低標高観測所からの標高外挿）と比べてどうか
# ---------------------------------------------------------------
# 蔵王計画は標高38.9〜525mの6観測所から y=0.2139x+8.5516 で約1,220mへ外挿し、
# 単一の平年値を使っている。UAV実測 1.1m に対し計画値 3.81m ＝ 3.46倍。
PLAN_DEPTH_M, OBS_DEPTH_M = 3.81, 1.1
plan_bias_pct = 100 * (PLAN_DEPTH_M - OBS_DEPTH_M) / OBS_DEPTH_M
w20 = adequacy["20年"]["20年確率"]["幅90_pct"]
results["vs_current_practice"] = dict(
    現行手法="標高38.9〜525mの気象庁6観測所からの回帰外挿（約1,220m）。単一の平年値",
    計画値_m=PLAN_DEPTH_M, UAV実測_m=OBS_DEPTH_M,
    現行手法の食い違い_pct=round(plan_bias_pct, 0),
    本手法の20年20年確率の90p区間幅_pct=w20,
    比較=("現行手法の食い違いは点推定の**バイアス**で、区間が付いていないので"
          f"検証もできない（{plan_bias_pct:.0f}%）。本手法は区間が付く（±{w20/2:.0f}%）。"
          "勝っているのは精度ではなく**不確かさが定量化できること**である"),
    自白="本手法の区間幅も再現期間50年以上では大きい。100年確率は外挿として開示する")
print("\n=== 8. 現行手法との比較 ===")
v = results["vs_current_practice"]
print(f"  現行（標高外挿・単一平年値）: 計画{PLAN_DEPTH_M}m 対 UAV実測{OBS_DEPTH_M}m "
      f"＝ 食い違い {v['現行手法の食い違い_pct']:.0f}%（区間なし）")
print(f"  本手法（20年・20年確率）: 90%区間の幅 {w20:.0f}%（＝±{w20/2:.0f}%）")

# 感度: 平均融雪期間 D0 の置き方（比の話なのでここだけが絶対値に効く）
sens = {}
for dur in (20.0, 30.0, 45.0):
    d0 = MEAN_MELTOUT - dur
    sens[f"平均融雪期間{dur:.0f}日"] = {
        f"{T}年の平年比": round((TRUE_Q[T] - d0) / (TRUE_Q[2] - d0), 3)
        for T in RETURN_PERIODS}
results["sensitivity_to_melt_duration"] = dict(
    表=sens,
    注=("平年比は平均融雪期間の置き方に依存する。これは観測できる量"
        "（fSCAの立ち下がりから消雪まで）なので、仮定ではなく実測に置き換えられる。"
        "現状9年分の消雪日マップしか無いため、ここは未実測の1点である"))
print("\n=== 感度: 平均融雪期間の置き方（平年比への影響）===")
for k, row in sens.items():
    print(f"  {k}: " + ", ".join(f"{kk}={vv}" for kk, vv in row.items()))

os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_return_period.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)
print("\n→ theme2_ライフライン復旧/poc/out/t2_return_period.json")
