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

さらに計算の途中で PoC-1 と PoC-2 の**不整合**が出た。先に書く。

  PoC-1 はタンク屋根パッチ(+5K)を SNR 1.6「限界域」と出し、PoC-2 は同じ対象を
  「単発では原理的に SNR<1」と出していた。原因は NEdT をどこの温度で規定された値と
  読むかである。PoC-1 は実効NEdT を「センサNEdT / g」（g=dTb/dTs）で作っており、
  これは **NEdT がその画素の見かけ輝度温度で規定されている**という読み方になる。
  低ε屋根の見かけ Tb は 266-280K で、そこでの dB/dT は 300K より小さいから、
  同じ雑音等価放射輝度がより大きな ΔTb に化ける（PoC-2 が見つけた増幅）。
  **NEdT は通常ある基準温度（300K級）で規定されるので、PoC-2 側が正しく、
  PoC-1 のタンク行は楽観だった。**

  そこで本PoCは全て**放射輝度領域**で組む。
      信号   ΔL = tau * eps * (dB/dTs) * ΔTs
      雑音   NEΔL = NEdT_ref * (dB/dT)|_Tref
  これなら輝度温度の非線形を経由しないので、どこで規定された NEdT かを取り違えない。
  両方の読み方を併記して、どちらの数字かが分かるようにしてある。

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
# 2. 検出ケース別 SNR（放射輝度領域・NEdTは300K規定）
# ============================================================
# 誤差項の内訳は PoC-1 の (E) と同じ構成にし、NEdT項だけ放射輝度領域で作り直す。
# 表面温度換算の実効雑音 = NEdT_ref * dB/dT|300K / (tau * eps * dB/dTs|Ts)

def nedt_in_surface_K(nedt_ref, Ts, eps, lam):
    """センサNEdT（300K規定）を、その面の表面温度誤差に換算する"""
    return nedt_ref * dplanck_dT(T_NEDT_REF, lam) / (TAU * eps * dplanck_dT(Ts, lam))


# PoC-1 と共通の非NEdT誤差項（K, 表面温度換算）
EPS_DTB_005 = 1.9      # ε±0.05 による見かけ温度誤差（PoC-1 (B) の風化アルミ値）
E_INTRA = EPS_DTB_005 * (0.02 / 0.05)   # 資産内ε不均一 ±0.02
E_INTER = EPS_DTB_005                   # 資産間ε差 ±0.05（静的兄弟差分で支配）
PSF_MIX = 0.8          # PSF混合（パッチ境界）
LOAD_RESID = 0.5       # 負荷・構造の残差差異（静的）
ALIGN_ERODED = 0.3     # 位置合わせ（エロージョン後）
# 二重差分（兄弟差分の時間変化）の内訳
DD_LOAD = 0.3          # 負荷残差の差動成分（エポックごとにランダム）
DD_EPS_AGING = 0.3     # 兄弟資産間の放射率の差動経年 —— エポック平均で落ちない

CASES = {
    "加熱炉・高温配管系の保温不良(+15K)": dict(dTs=15.0, Ts=TS_HOT, npix=6, kind="scene"),
    "タンク屋根の劣化パッチ(+5K,100m²≈8px)": dict(dTs=5.0, Ts=TS_ROOF, npix=8, kind="scene"),
    "タンク屋根の劣化パッチ(+3K,100m²≈8px)": dict(dTs=3.0, Ts=TS_ROOF, npix=8, kind="scene"),
    "ユニット面的劣化(+1K) 静的兄弟差分": dict(dTs=1.0, Ts=TS_HOT, npix=50, kind="sib_static"),
    "ユニット面的劣化(+1K) 二重差分": dict(dTs=1.0, Ts=TS_HOT, npix=50, kind="dd"),
    "ユニット面的劣化(+0.5K) 二重差分": dict(dTs=0.5, Ts=TS_HOT, npix=50, kind="dd"),
}


def case_noise(kind, nedt_s, npix, n_epochs=1):
    """雑音を「エポック平均で落ちる項」と「落ちない項」に分けて返す (random, systematic)"""
    if kind == "scene":
        rnd = np.sqrt((nedt_s * np.sqrt(2) / np.sqrt(npix))**2)
        sysm = np.sqrt(E_INTRA**2 + PSF_MIX**2)
    elif kind == "sib_static":
        rnd = nedt_s * np.sqrt(2) / np.sqrt(npix)
        sysm = np.sqrt(E_INTER**2 + LOAD_RESID**2 + ALIGN_ERODED**2)
    elif kind == "dd":
        rnd = np.sqrt((nedt_s * 2 / np.sqrt(npix))**2 + DD_LOAD**2)
        sysm = DD_EPS_AGING
    else:
        raise ValueError(kind)
    return float(rnd / np.sqrt(n_epochs)), float(sysm)


def snr_of(kind, dTs, Ts, npix, nedt_ref, lam, n_epochs=1):
    nedt_s = nedt_in_surface_K(nedt_ref, Ts, EPS_WEATHERED, lam)
    rnd, sysm = case_noise(kind, nedt_s, npix, n_epochs)
    return dTs / np.sqrt(rnd**2 + sysm**2)


snr_tables = {}
for bname, (lo, hi) in BANDS.items():
    lam = make_band(lo, hi)
    row = {}
    for cname, c in CASES.items():
        nep = 6 if c["kind"] == "dd" else 1
        nedt_s = nedt_in_surface_K(1.0, c["Ts"], EPS_WEATHERED, lam)
        rnd, sysm = case_noise(c["kind"], nedt_s, c["npix"], nep)
        s = c["dTs"] / np.sqrt(rnd**2 + sysm**2)
        row[cname] = dict(
            エポック数=nep,
            実効NEdT_表面K換算=round(nedt_s, 2),
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
        g = (apparent_tb(c["Ts"] + d, EPS_WEATHERED, TAU, SKY_CLEAR, lam)
             - apparent_tb(c["Ts"] - d, EPS_WEATHERED, TAU, SKY_CLEAR, lam)) / (2 * d)
        nedt_poc1 = 1.0 / g                                        # PoC-1 の実効NEdT
        nedt_new = nedt_in_surface_K(1.0, c["Ts"], EPS_WEATHERED, lam)
        row[cname] = dict(PoC1の実効NEdT_K=round(float(nedt_poc1), 2),
                          本PoCの実効NEdT_K=round(nedt_new, 2),
                          倍率=round(nedt_new / float(nedt_poc1), 2))
    compat[bname] = row
results["poc1_convention_gap"] = compat

# ============================================================
# 3. SNR→AUC の解析写像を PoC-2 のモンテカルロで検証する
# ============================================================
# 等分散ガウス2群の判別では AUC = Phi(d'/sqrt(2))。d' を SNR と同一視して良いかを
# PoC-2 の実測AUC（二重差分・6エポック）と突き合わせる。
MC_REF = {"+0.5K": 0.86, "+1.0K": 0.92, "+2.0K": 0.997}   # PoC-2 の二重差分6エポックAUC
lam_A = make_band(*BANDS["A_仮定_3.4-4.2um"])   # PoC-2 は仮定帯域・NEdT1Kで走っている
valid = {}
for label, auc_mc in MC_REF.items():
    dts = float(label.replace("K", "").replace("+", ""))
    s = snr_of("dd", dts, TS_HOT, 50, 1.0, lam_A, n_epochs=6)
    auc_an = float(norm.cdf(s / np.sqrt(2)))
    valid[label] = dict(PoC2のMC_AUC=auc_mc, 本PoCの解析SNR=round(s, 2),
                        解析AUC=round(auc_an, 3), 差=round(auc_an - auc_mc, 3))
results["auc_mapping_validation"] = dict(
    二重差分_場所が既知=valid,
    判定="+1Kと+2Kで差 0.02 以内。二重差分については解析写像を使ってよい")

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
            nedt_s = nedt_in_surface_K(nedt, c["Ts"], EPS_WEATHERED, lam)
            _, sysm = case_noise(c["kind"], nedt_s, c["npix"], 1)
            row_d = dict(AUC=aucs, **need,
                         上限AUC=round(auc_from_snr(c["dTs"] / sysm), 3))
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
    for nedt in NEDT_GRID:
        nedt_s = nedt_in_surface_K(nedt, c["Ts"], EPS_WEATHERED, lam_B)
        _, sysm = case_noise(c["kind"], nedt_s, c["npix"], 1)
        row[f"NEdT={nedt}K"] = round(auc_from_snr(c["dTs"] / sysm), 3)
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
    floor_sens[cname] = {f"差動経年={v}K": round(auc_from_snr(c["dTs"] / v), 3)
                         for v in (0.15, 0.2, 0.3, 0.5)}
results["ceiling_vs_eps_aging"] = dict(
    上限AUC=floor_sens,
    含意="天井を上げる操作は NEdT ではなく、兄弟資産の選定（同一設計・同一施工年・同一外装履歴）である")

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

print("\n=== 2b. PoC-1 の読み方との差（実効NEdTの倍率）===")
for b, row in compat.items():
    ks = [f"{cn.split('(')[0]}: ×{v['倍率']}" for cn, v in row.items()]
    print(f"  [{b}] " + ", ".join(ks))

print("\n=== 3. SNR→AUC 写像の検証（PoC-2 の二重差分6エポックMCと比較）===")
for k, v in valid.items():
    print(f"  {k}: MC={v['PoC2のMC_AUC']} vs 解析={v['解析AUC']}（SNR {v['本PoCの解析SNR']}、差 {v['差']:+.3f}）")

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
