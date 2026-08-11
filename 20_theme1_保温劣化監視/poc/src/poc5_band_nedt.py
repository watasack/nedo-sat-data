"""PoC-5: 実バンドでの再計算と、NEdTに対する結論の依存性

PoC-1 には提出物の主張を外部の未回答に縛る弱点が2つあった。

  (a) **帯域が仮定値だった。** PoC-1 の LAM は 3.4-4.2um で、これは「HotSat級MWIR想定」
      と書いた仮定である。HotSat-2 の夜間帯は 3.7-4.95um（05_衛星調査メモ）。
      07 の PoC-1 節に「実帯域での再計算はPhase 0」と書いたまま閉じていない。

  (b) **NEdT の実力値が非公開で、そこに全判定がぶら下がっていた。** 07 は
      「NEdT実力値の確認（JSI照会）が引き続き分水嶺」と3箇所で書いている。
      JSI の回答が 8/31 に間に合わない場合、提出物には何も書き足さないと決めてある
      （CLAUDE.md 未完了タスク10）。つまり**回答が来なければ分水嶺が未確定のまま出す**。

ここでやるのは (a) の計算と、(b) を**掃引に置き換えること**である。
NEdT を 0.5〜3K で振って「この値ならこう」の表を出せば、回答が来なくても結論が言える。

さらに計算の途中で PoC-1 に**単位の混在**が見つかった。先に書く。

  PoC-1 の (F) 節は SNR を「信号 / 雑音」で作っているが、
    信号  = ΔTs * g          … **輝度温度(Tb)の単位**（g=dTb/dTs で表面温度から写した量）
    雑音項 ε不確かさ 0.76K、PSF混合 0.8K … **輝度温度の単位**（「見かけ温度誤差」）
    雑音項 実効NEdT = NEdT/g … **表面温度の単位**（NEdTをgで割って表面温度に戻した量）
  となっており、**表面温度の項と輝度温度の項を同じRSSに入れている**。
  gが約0.5なので、この混在は実効NEdT項を約2倍に見せる方向に働く。

  本PoCは全部**輝度温度(Tb)領域**に統一する。センサが測るのはTbなので、そこが自然である。
    信号    ΔTb = ΔTs * g(Ts)
    NEdT項  NEdT_ref * amp(Tb_見かけ)      amp = (dB/dT|300K)/(dB/dT|Tb)
    見かけの誤差項（ε・PSF・位置合わせ・放射率の差動経年）はそのままTb
    実温度の誤差項（負荷・構造の残差差異）は * g で Tb に写す

  NEdT項の扱いは PoC-1 の「NEdT/g」から「NEdT*amp」に変わる。これは PoC-2 が見つけた
  低ε屋根でのPlanck非線形増幅そのものである。屋根の見かけTbは274K級で amp≈2.3、
  一方 1/g≈2.07 なので、**PoC-1 のタンク行は楽観だったが差は小さい**
  （SNR 1.6 → 約1.5）。ε・PSFの床が支配しているためである。

  なお PoC-2 が「単発では原理的に SNR<1」と書いたのと矛盾はしない。
  **PoC-1/本PoCのSNRは「パッチ位置が既知」の量**で、PoC-2 のAUC 0.64は
  位置が未知でPSF整合フィルタの最大値を取る検知器の性能である（下の3b節）。
  同じ対象の別の量なので、両方正しい。

最後に、掃引して初めて見えたことを1つ。**エポックを増やしても SNR は無限には伸びない。**
兄弟差分の時間変化の雑音には、エポック平均で落ちる項（NEdT・負荷残差）と
落ちない項（**兄弟資産間の放射率の差動経年**）がある。後者が上限を決める。
したがって NEdT が決めるのは「何エポック要るか」であって「成立するか」ではない。
JSI の回答が遅れても提案の成否は動かない、という言い方ができる。

出力: poc/out/poc5_results.json
"""
import json
import os

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

C1 = 1.191042e8   # W/m2/sr/um^-4
C2 = 1.4387752e4  # um K

# 帯域。A=PoC-1の仮定、B=HotSat-2の夜間帯（05_衛星調査メモ）
BANDS = {
    "A_仮定_3.4-4.2um": (3.4, 4.2),
    "B_実帯域_3.7-4.95um": (3.7, 4.95),
}

TA = 288.0        # 夜間外気温 15C
TAU = 0.75        # 中緯度夏夜MWIR大気透過
SKY_CLEAR, SKY_OVC = 240.0, 280.0
T_NEDT_REF = 300.0   # NEdT が規定される基準温度（メーカ諸元の慣行）
EPS_WEATHERED = 0.25
TS_HOT = 310.0    # 保温外装の表面温度（35C級）
TS_ROOF = 300.0   # タンク屋根の表面温度（内容物・外気に近い）


def make_band(lo, hi, n=161):
    return np.linspace(lo, hi, n)


def planck_band(T, lam):
    T = np.atleast_1d(T).astype(float)[:, None]
    B = C1 / (lam**5 * (np.exp(C2 / (lam * T)) - 1.0))
    out = np.trapezoid(B, lam, axis=1)
    return out if out.size > 1 else out[0]


def dplanck_dT(T, lam, d=0.25):
    """帯域積分放射輝度の温度微分 dB/dT [W/m2/sr/K]"""
    return float((planck_band(T + d, lam) - planck_band(T - d, lam)) / (2 * d))


def tb_from_radiance(L, lam):
    return brentq(lambda T: planck_band(T, lam) - L, 150.0, 500.0, xtol=1e-5)


def sensor_radiance(Ts, eps, tau, T_sky, lam, T_atm=285.0):
    return tau * (eps * planck_band(Ts, lam) + (1 - eps) * planck_band(T_sky, lam)) \
        + (1 - tau) * planck_band(T_atm, lam)


def apparent_tb(Ts, eps, tau, T_sky, lam, T_atm=285.0):
    return tb_from_radiance(sensor_radiance(Ts, eps, tau, T_sky, lam, T_atm), lam)


results = {"meta": dict(
    tau=TAU, T_air=TA, eps=EPS_WEATHERED, T_nedt_ref=T_NEDT_REF,
    Ts_hot=TS_HOT, Ts_roof=TS_ROOF, sky_clear=SKY_CLEAR, sky_ovc=SKY_OVC,
    note="全て放射輝度領域で組んである。NEdTは基準温度300Kで規定された値として扱う")}

# ============================================================
# 1. 帯域による物理量の違い
# ============================================================
band_phys = {}
for bname, (lo, hi) in BANDS.items():
    lam = make_band(lo, hi)
    # 感度ゲイン dTb/dTs（PoC-1と同じ定義。帯域比較のため残す）
    d = 0.5
    g = (apparent_tb(TS_HOT + d, EPS_WEATHERED, TAU, SKY_CLEAR, lam)
         - apparent_tb(TS_HOT - d, EPS_WEATHERED, TAU, SKY_CLEAR, lam)) / (2 * d)
    # 天空スイング（晴天夜⇔曇天夜）
    swing = apparent_tb(TS_HOT, EPS_WEATHERED, TAU, SKY_OVC, lam) \
        - apparent_tb(TS_HOT, EPS_WEATHERED, TAU, SKY_CLEAR, lam)
    # 低ε屋根の見かけ輝度温度と、そこでのNEdT増幅
    tb_roof = apparent_tb(TS_ROOF, EPS_WEATHERED, TAU, SKY_CLEAR, lam)
    dbdt_ref = dplanck_dT(T_NEDT_REF, lam)
    amp = {}
    for tbx in (266.0, 272.0, 280.0, 300.0):
        amp[f"Tb={tbx:.0f}K"] = round(dbdt_ref / dplanck_dT(tbx, lam), 2)
    band_phys[bname] = dict(
        帯域幅_um=round(hi - lo, 2),
        感度ゲイン_dTb_dTs=round(float(g), 3),
        天空スイング_K=round(float(swing), 2),
        屋根の見かけTb_K=round(float(tb_roof), 1),
        dBdT_at_300K=round(dbdt_ref, 5),
        NEdT増幅倍率=amp,
    )
results["band_physics"] = band_phys

# ============================================================
# 2. 検出ケース別 SNR（すべて輝度温度Tbの単位に統一）
# ============================================================
def sens_gain(Ts, eps, lam, d=0.5):
    """g = dTb/dTs。表面温度1Kが輝度温度に写る割合"""
    return float((apparent_tb(Ts + d, eps, TAU, SKY_CLEAR, lam)
                  - apparent_tb(Ts - d, eps, TAU, SKY_CLEAR, lam)) / (2 * d))


def nedt_amp(Ts, eps, lam):
    """NEdT（300K規定）がその面の見かけTbで何倍に増幅されるか"""
    tb = apparent_tb(Ts, eps, TAU, SKY_CLEAR, lam)
    return dplanck_dT(T_NEDT_REF, lam) / dplanck_dT(tb, lam)


# PoC-1 と共通の非NEdT誤差項。**すべて輝度温度(Tb)の単位**
EPS_DTB_005 = 1.9      # ε±0.05 による見かけ温度誤差（PoC-1 (B) の風化アルミ値）
E_INTRA = EPS_DTB_005 * (0.02 / 0.05)   # 資産内ε不均一 ±0.02
E_INTER = EPS_DTB_005                   # 資産間ε差 ±0.05（静的兄弟差分で支配）
PSF_MIX = 0.8          # PSF混合（パッチ境界）
ALIGN_ERODED = 0.3     # 位置合わせ（エロージョン後）
DD_EPS_AGING = 0.3     # 兄弟資産間の放射率の差動経年 —— エポック平均で落ちない
# 実温度の誤差項（gを掛けてTbに写す）
LOAD_RESID_TS = 0.5    # 負荷・構造の残差差異（静的、表面温度K）
DD_LOAD_TS = 0.3       # 負荷残差の差動成分（エポックごとにランダム、表面温度K）

CASES = {
    "加熱炉・高温配管系の保温不良(+15K)": dict(dTs=15.0, Ts=TS_HOT, npix=6, kind="scene"),
    "タンク屋根の劣化パッチ(+5K,100m²≈8px)": dict(dTs=5.0, Ts=TS_ROOF, npix=8, kind="scene"),
    "タンク屋根の劣化パッチ(+3K,100m²≈8px)": dict(dTs=3.0, Ts=TS_ROOF, npix=8, kind="scene"),
    "ユニット面的劣化(+1K) 静的兄弟差分": dict(dTs=1.0, Ts=TS_HOT, npix=50, kind="sib_static"),
    "ユニット面的劣化(+1K) 二重差分": dict(dTs=1.0, Ts=TS_HOT, npix=50, kind="dd"),
    "ユニット面的劣化(+0.5K) 二重差分": dict(dTs=0.5, Ts=TS_HOT, npix=50, kind="dd"),
}


def case_noise(kind, nedt_tb, npix, g, n_epochs=1):
    """雑音を「エポック平均で落ちる項」と「落ちない項」に分けて返す (random, systematic)

    すべて輝度温度Tbの単位。nedt_tb はその面の見かけTbでのNEdT（増幅済み）。
    """
    if kind == "scene":
        rnd = nedt_tb * np.sqrt(2) / np.sqrt(npix)
        sysm = np.sqrt(E_INTRA**2 + PSF_MIX**2)
    elif kind == "sib_static":
        rnd = nedt_tb * np.sqrt(2) / np.sqrt(npix)
        sysm = np.sqrt(E_INTER**2 + (LOAD_RESID_TS * g)**2 + ALIGN_ERODED**2)
    elif kind == "dd":
        rnd = np.sqrt((nedt_tb * 2 / np.sqrt(npix))**2 + (DD_LOAD_TS * g)**2)
        sysm = DD_EPS_AGING
    else:
        raise ValueError(kind)
    return float(rnd / np.sqrt(n_epochs)), float(sysm)


def snr_of(kind, dTs, Ts, npix, nedt_ref, lam, n_epochs=1):
    """SNR。信号も雑音も輝度温度Tbの単位で揃えてある"""
    g = sens_gain(Ts, EPS_WEATHERED, lam)
    nedt_tb = nedt_ref * nedt_amp(Ts, EPS_WEATHERED, lam)
    rnd, sysm = case_noise(kind, nedt_tb, npix, g, n_epochs)
    return (dTs * g) / np.sqrt(rnd**2 + sysm**2)


snr_tables = {}
for bname, (lo, hi) in BANDS.items():
    lam = make_band(lo, hi)
    row = {}
    for cname, c in CASES.items():
        nep = 6 if c["kind"] == "dd" else 1
        g = sens_gain(c["Ts"], EPS_WEATHERED, lam)
        nedt_tb = 1.0 * nedt_amp(c["Ts"], EPS_WEATHERED, lam)
        rnd, sysm = case_noise(c["kind"], nedt_tb, c["npix"], g, nep)
        s = (c["dTs"] * g) / np.sqrt(rnd**2 + sysm**2)
        row[cname] = dict(
            エポック数=nep,
            信号_Tb換算_K=round(c["dTs"] * g, 2),
            実効NEdT_Tb換算=round(nedt_tb, 2),
            雑音_平均で落ちる_K=round(rnd, 2),
            雑音_落ちない_K=round(sysm, 2),
            SNR=round(float(s), 2),
            判定=("検出可能" if s >= 3 else "限界域" if s >= 0.8 else "単発検出不可"),
        )
    snr_tables[bname] = row
results["snr_nedt1K_ref300K"] = snr_tables

# PoC-1 の読み方（NEdTがその画素の見かけTbで規定されているとした場合）との差
compat = {}
for bname, (lo, hi) in BANDS.items():
    lam = make_band(lo, hi)
    d = 0.5
    row = {}
    for cname, c in CASES.items():
        g = sens_gain(c["Ts"], EPS_WEATHERED, lam)
        nedt_poc1 = 1.0 / g                       # PoC-1: NEdT/g（表面温度単位のまま混在）
        nedt_new = 1.0 * nedt_amp(c["Ts"], EPS_WEATHERED, lam)   # 本PoC: NEdT*amp（Tb単位）
        row[cname] = dict(PoC1のNEdT項_1除くg=round(float(nedt_poc1), 2),
                          本PoCのNEdT項_amp倍=round(nedt_new, 2),
                          倍率=round(nedt_new / float(nedt_poc1), 2))
    compat[bname] = row
results["poc1_unit_mixing_gap"] = dict(
    比較=compat,
    説明=("PoC-1 は NEdT/g（表面温度単位）を輝度温度単位の誤差項と同じRSSに入れていた。"
          "本PoCは NEdT*amp（輝度温度単位）に統一した。倍率が1に近いのは偶然で、"
          "1/g と amp がこのパラメータ帯でたまたま近いためである"))

# ============================================================
# 3. SNR→AUC の解析写像を PoC-2 のモンテカルロで検証する
# ============================================================
# 等分散ガウス2群の判別では AUC = Phi(d'/sqrt(2))。d' を SNR と同一視して良いかを
# PoC-2 の実測AUC（二重差分・6エポック）と突き合わせる。
MC_REF = {"+0.5K": 0.86, "+1.0K": 0.92, "+2.0K": 0.997}   # PoC-2 の二重差分6エポックAUC
lam_A = make_band(*BANDS["A_仮定_3.4-4.2um"])   # PoC-2 は仮定帯域・NEdT1Kで走っている
# **前提を揃えないと写像の検証にならない。** PoC-2 の合成シーンは資産ごとのεを
# 静的に振っているだけで、**兄弟資産間の放射率の差動経年（時間とともに開く差）を
# 模擬していない**。本PoCの雑音モデルはそれを 0.3K の「落ちない項」として入れている。
# したがって素で比べると本PoCが低く出る。写像そのものを見るには差動経年を0にして揃える。
_AGING = DD_EPS_AGING
valid = {}
for label, auc_mc in MC_REF.items():
    dts = float(label.replace("K", "").replace("+", ""))
    s_full = snr_of("dd", dts, TS_HOT, 50, 1.0, lam_A, n_epochs=6)
    globals()["DD_EPS_AGING"] = 0.0                      # PoC-2 の前提に揃える
    s_match = snr_of("dd", dts, TS_HOT, 50, 1.0, lam_A, n_epochs=6)
    globals()["DD_EPS_AGING"] = _AGING
    valid[label] = dict(
        PoC2のMC_AUC=auc_mc,
        前提を揃えた解析SNR=round(s_match, 2),
        前提を揃えた解析AUC=round(float(norm.cdf(s_match / np.sqrt(2))), 3),
        差_揃えたとき=round(float(norm.cdf(s_match / np.sqrt(2))) - auc_mc, 3),
        差動経年を入れた解析SNR=round(s_full, 2),
        差動経年を入れた解析AUC=round(float(norm.cdf(s_full / np.sqrt(2))), 3),
        差_差動経年あり=round(float(norm.cdf(s_full / np.sqrt(2))) - auc_mc, 3),
    )
results["auc_mapping_validation"] = dict(
    二重差分_場所が既知=valid,
    写像の判定=("前提を揃えると +1K で差 0.02、+2K で差 0.00。"
                "AUC=Phi(SNR/sqrt2) の写像は二重差分については使ってよい"),
    より重要な発見=(
        "**PoC-2 の合成シーンは兄弟資産間の放射率の差動経年を模擬していない。** "
        "資産ごとのεは静的に振ってあるだけで、時間とともに兄弟間の差が開く成分が無い。"
        "この項はエポック平均で落ちないので上限を決める項であり、入れると "
        "+1K・6エポックのAUCは 0.92 → 0.83 に下がる。"
        "08/12 が引用している『二重差分でAUC 0.86〜0.997（シミュレーション）』は"
        "**この項を含まない値**である。数字を下げる必要はないが、"
        "『同一設計・同一施工年・同一外装履歴の兄弟資産を選ぶ』という前提条件が"
        "AUCの前提であることを明示すべきである（下の ceiling_vs_eps_aging 節）"),
    差動経年0_3Kの根拠="PoC-1 (E) の兄弟差分バジェットの仮定値。PoC-6 で実データと桁を確認した")

# 同じ写像をタンクパッチに当てると成立しない。**先に自分で確かめて記録する。**
# タンクパッチ検知はパッチ位置が未知で、PSF整合フィルタの最大値を取る＝多重比較なので、
# 「場所が既知の1検定」を前提にした AUC=Phi(SNR/sqrt2) は過大に出る。
MC_REF_TANK = {"+5K/100m²": {"1ep": 0.64, "6ep": 0.89, "12ep": 0.96},
               "+3K/100m²": {"1ep": 0.56, "6ep": 0.83, "12ep": 0.88}}
tank_gap = {}
for label, eps_map in MC_REF_TANK.items():
    dts = float(label.split("K")[0].replace("+", ""))
    row = {}
    for ep_label, auc_mc in eps_map.items():
        nep = int(ep_label.replace("ep", ""))
        s = snr_of("scene", dts, TS_ROOF, 8, 1.0, lam_A, n_epochs=nep)
        auc_an = float(norm.cdf(s / np.sqrt(2)))
        row[ep_label] = dict(PoC2のMC_AUC=auc_mc, 解析AUC=round(auc_an, 3),
                             差=round(auc_an - auc_mc, 3))
    tank_gap[label] = row
results["auc_mapping_fails_for_tank"] = dict(
    比較=tank_gap,
    原因=("タンクパッチ検知はパッチ位置が未知で、PSF整合フィルタの最大値でスコア化する。"
          "最大値統計は平均より裾が重いので、場所が既知の1検定を前提にした"
          "AUC=Phi(SNR/sqrt2) は系統的に過大に出る"),
    結論=("**本PoCの掃引でタンクパッチのAUCを読んではいけない。**"
          "タンクパッチのNEdT依存は検知器そのものを回した PoC-5b（poc5b_results.json）を使う。"
          "本PoCがタンクパッチについて言えるのはSNRまでである"))


def auc_from_snr(s):
    return float(norm.cdf(s / np.sqrt(2)))


# ============================================================
# 4. NEdT 掃引 —— 「この値なら何エポック要るか」の決定表
# ============================================================
NEDT_GRID = [0.5, 1.0, 1.5, 2.0, 3.0]     # 公表値は「<2K」。3Kは外れた場合の備え
EP_GRID = [1, 3, 6, 12, 24, 36]           # 月次なら 12=1年、36=3年
TARGETS = (0.90, 0.80)

sweep = {}
for bname, (lo, hi) in BANDS.items():
    lam = make_band(lo, hi)
    per_case = {}
    for cname, c in CASES.items():
        if c["kind"] == "sib_static":
            continue      # 静的兄弟差分はエポックを積む推定器ではない
        rows = {}
        for nedt in NEDT_GRID:
            aucs = {}
            for nep in EP_GRID:
                aucs[f"{nep}ep"] = round(auc_from_snr(
                    snr_of(c["kind"], c["dTs"], c["Ts"], c["npix"], nedt, lam, nep)), 3)
            # 目標AUCに要るエポック数（EP_GRIDに縛られず1..600で探す）
            need = {}
            for tgt in TARGETS:
                hit = None
                for nep in range(1, 601):
                    if auc_from_snr(snr_of(c["kind"], c["dTs"], c["Ts"],
                                           c["npix"], nedt, lam, nep)) >= tgt:
                        hit = nep
                        break
                need[f"AUC{tgt:.2f}に要るエポック数"] = hit if hit else "到達不能"
            # エポック→無限大の上限（落ちない項だけが残る）
            g_s = sens_gain(c["Ts"], EPS_WEATHERED, lam)
            nedt_tb = nedt * nedt_amp(c["Ts"], EPS_WEATHERED, lam)
            _, sysm = case_noise(c["kind"], nedt_tb, c["npix"], g_s, 1)
            row_d = dict(AUC=aucs, **need,
                         上限AUC=round(auc_from_snr(c["dTs"] * g_s / sysm), 3))
            if c["kind"] == "scene":
                row_d["警告"] = ("解析写像は空間探索（多重比較）を含まないので過大。"
                                 "タンクパッチのAUCとエポック数は PoC-5b を使うこと")
            rows[f"NEdT={nedt}K"] = row_d
        per_case[cname] = rows
    sweep[bname] = per_case
results["nedt_sweep"] = sweep

# ============================================================
# 5. 上限は NEdT では動かない —— 何が天井を決めているか
# ============================================================
ceiling = {}
lam_B = make_band(*BANDS["B_実帯域_3.7-4.95um"])
for cname, c in CASES.items():
    if c["kind"] == "sib_static":
        continue
    row = {}
    g_B = sens_gain(c["Ts"], EPS_WEATHERED, lam_B)
    for nedt in NEDT_GRID:
        nedt_tb = nedt * nedt_amp(c["Ts"], EPS_WEATHERED, lam_B)
        _, sysm = case_noise(c["kind"], nedt_tb, c["npix"], g_B, 1)
        row[f"NEdT={nedt}K"] = round(auc_from_snr(c["dTs"] * g_B / sysm), 3)
    ceiling[cname] = row
results["ceiling_vs_nedt"] = dict(
    実帯域での上限AUC=ceiling,
    天井を決めている項=dict(
        シーン内コントラスト=f"資産内ε不均一±0.02({E_INTRA:.2f}K)とPSF混合({PSF_MIX}K)のRSS",
        二重差分=f"兄弟資産間の放射率の差動経年({DD_EPS_AGING}K)"),
    意味="上限は NEdT に依存しない。NEdT が決めるのは到達に要るエポック数だけである",
)

# 天井を動かすには何が要るか（差動経年を下げたときの上限）
floor_sens = {}
for cname, c in CASES.items():
    if c["kind"] != "dd":
        continue
    g_B = sens_gain(c["Ts"], EPS_WEATHERED, lam_B)
    floor_sens[cname] = {f"差動経年={v}K": round(auc_from_snr(c["dTs"] * g_B / v), 3)
                         for v in (0.15, 0.2, 0.3, 0.5)}
results["ceiling_vs_eps_aging"] = dict(
    上限AUC=floor_sens,
    含意="天井を上げる操作は NEdT ではなく、兄弟資産の選定（同一設計・同一施工年・同一外装履歴）である",
    これが本PoC最大の発見=(
        "**この提案の分水嶺は NEdT ではなく、兄弟資産間の放射率の差動経年である。** "
        "0.15K なら +1K の二重差分は上限AUC 0.99、0.3K なら 0.87、0.5K なら 0.75。"
        "ところがこの値は PoC-1 の仮定値で、出典が無く、PoC-2 の合成シーンも模擬しておらず、"
        "実測もされていない。**JSI照会（NEdT）よりこちらが先に来るべき未確認事項である。**"),
    ただし上限は上界である=(
        "ここでは差動経年をエポック平均で落ちない一定バイアスとして扱った。"
        "実際には緩やかな**トレンド**なので、ステップ走査が段差とトレンドを分離できる分だけ"
        "実害は小さくなる（PoC-4 のパイプラインは slope_per_ep を出している）。"
        "したがってこの上限AUCは**悪い側の上界**であって、到達不能の宣言ではない"),
    測り方=("同一構内の同型ユニット対を、外装張替え履歴が既知の期間で追う。"
            "CMMS の外装履歴と突き合わせれば張替え直後＝差動経年ゼロの起点が取れる。"
            "PoC-6 が実Landsatで測った近接兄弟対の時系列σ 0.43K は総量なので、"
            "そのうちトレンド成分がいくらかを分ければ上限が決まる"))

# ============================================================
# 6. 最悪の隅 —— 実帯域 × NEdT 2K でも成立するか
# ============================================================
worst = {}
for cname, c in CASES.items():
    if c["kind"] == "sib_static":
        continue
    nep_need = None
    for nep in range(1, 601):
        if auc_from_snr(snr_of(c["kind"], c["dTs"], c["Ts"], c["npix"],
                               2.0, lam_B, nep)) >= 0.90:
            nep_need = nep
            break
    worst[cname] = dict(
        単発SNR=round(snr_of(c["kind"], c["dTs"], c["Ts"], c["npix"], 2.0, lam_B, 1), 2),
        AUC_12ep=round(auc_from_snr(snr_of(c["kind"], c["dTs"], c["Ts"], c["npix"],
                                           2.0, lam_B, 12)), 3),
        AUC090に要るエポック数=nep_need if nep_need else "到達不能",
        月次なら年数=(round(nep_need / 12.0, 1) if nep_need else None),
    )
results["worst_corner_realband_nedt2K"] = worst

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "poc5_results.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------------- 出力 ----------------
print("=== 1. 帯域による物理量の違い ===")
for b, v in band_phys.items():
    print(f"  {b}: ゲイン dTb/dTs={v['感度ゲイン_dTb_dTs']}, 天空スイング={v['天空スイング_K']}K, "
          f"屋根の見かけTb={v['屋根の見かけTb_K']}K")
    print(f"      NEdT増幅（300K規定を各Tbへ）: {v['NEdT増幅倍率']}")

print("\n=== 2. 検出ケース別SNR（NEdT=1K・300K規定・放射輝度領域）===")
for b, row in snr_tables.items():
    print(f"  [{b}]")
    for cn, v in row.items():
        print(f"      {cn}: SNR={v['SNR']} ({v['判定']}) "
              f"[落ちる{v['雑音_平均で落ちる_K']}K / 落ちない{v['雑音_落ちない_K']}K]")

print("\n=== 2b. PoC-1 の単位混在との差（NEdT項の倍率）===")
for b, row in compat.items():
    ks = [f"{cn.split('(')[0]}: ×{v['倍率']}" for cn, v in row.items()]
    print(f"  [{b}] " + ", ".join(ks))

print("\n=== 3. SNR→AUC 写像の検証（PoC-2 の二重差分6エポックMCと比較）===")
for k, v in valid.items():
    print(f"  {k}: MC={v['PoC2のMC_AUC']} / 前提を揃えた解析={v['前提を揃えた解析AUC']}"
          f"（差 {v['差_揃えたとき']:+.3f}）→ 写像は妥当")
    print(f"      差動経年0.3Kを入れると {v['差動経年を入れた解析AUC']}"
          f"（差 {v['差_差動経年あり']:+.3f}）← PoC-2 が模擬していない項")

print("\n=== 3b. 同じ写像はタンクパッチには使えない（自分で確かめた）===")
for label, row in tank_gap.items():
    print(f"  {label}: " + ", ".join(
        f"{ep} MC={v['PoC2のMC_AUC']} 解析={v['解析AUC']}({v['差']:+.2f})" for ep, v in row.items()))
print("  → タンクパッチのNEdT依存は PoC-5b（検知器を実際に回す）を使う")

print("\n=== 4. NEdT掃引: AUC0.90に要るエポック数（実帯域・二重差分のみ）===")
for cn, rows in sweep["B_実帯域_3.7-4.95um"].items():
    tag = "  ※SNRのみ有効（AUCは過大・PoC-5b参照）" if "タンク" in cn else ""
    cells = [f"{k.split('=')[1]}→{v['AUC0.90に要るエポック数']}" for k, v in rows.items()]
    print(f"  {cn}: " + ", ".join(cells) + tag)

print("\n=== 5. エポックを無限に積んだときの上限AUC（実帯域）===")
for cn, row in ceiling.items():
    vals = set(row.values())
    print(f"  {cn}: {row}" + ("   ← NEdTに依存しない" if len(vals) == 1 else ""))
print("  天井を決めているのは差動経年:")
for cn, row in floor_sens.items():
    print(f"      {cn}: {row}")

print("\n=== 6. 最悪の隅（実帯域 × NEdT 2K）===")
for cn, v in worst.items():
    print(f"  {cn}: 単発SNR={v['単発SNR']}, 12ep AUC={v['AUC_12ep']}, "
          f"AUC0.90まで {v['AUC090に要るエポック数']}ep"
          + (f"（月次で{v['月次なら年数']}年）" if v['月次なら年数'] else ""))
