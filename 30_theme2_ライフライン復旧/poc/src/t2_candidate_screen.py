"""T2-PoC2: 新候補案の物理スクリーニング

T2-A′（停電由来の断水推定）は「既存システムへの観測入力の供給」という位置づけでしか
新規性を主張できず、技術的な着眼に乏しかった。代案を出すにあたり、
「非自明な物理量で、いま誰も答えられない問いに答える」候補を物理で足切りする。

検証する候補:
  C1 冠水後の浸水域復元 ── 含水率上昇による熱慣性変化（夜間の冷え方の違い）
  C2 地中漏水のスクリーニング ── 漏水湿潤域の熱慣性・蒸発冷却
  C3 積雪期の暖房停止地区の抽出 ── 屋根雪の放射冷却の有無
  C4 被災PVの発電停止判定 ── 発電中/停止中のパネル温度差

あわせて、全候補に共通する制約として MWIR(HotSat-2) と TIR(Landsat/ECOSTRESS) の
常温域での感度差を計算する。地表付近の常温対象は MWIR が最も苦手な領域である。

出力: theme2_ライフライン復旧/poc/out/t2_candidate_screen.json
"""
import numpy as np
from scipy.optimize import brentq
import json, os

C1_ = 1.191042e8
C2_ = 1.4387752e4
SIGMA = 5.670374e-8

BANDS = {"MWIR(HotSat-2) 3.7-4.95um": np.linspace(3.7, 4.95, 126),
         "TIR(Landsat/ECOSTRESS) 8-12um": np.linspace(8.0, 12.0, 161)}


def planck_band(T, lam):
    T = np.atleast_1d(T).astype(float)[:, None]
    B = C1_ / (lam**5 * (np.exp(C2_/(lam*T)) - 1.0))
    out = np.trapezoid(B, lam, axis=1)
    return out if out.size > 1 else out[0]


results = {}

# ===== 共通制約: 常温域での MWIR と TIR の感度差 =====
# 同じ「地表1Kの変化」が輝度に何%の変化として現れるか（dL/L per K）。
# センサの相対放射計測精度が同じなら、この値が大きいほど有利。
# ただし絶対輝度そのものが小さいと読み出し雑音に埋まるので、輝度も併記する。
band_cmp = {}
for bname, lam in BANDS.items():
    row = {}
    for T in (270.0, 280.0, 290.0, 300.0):
        L = float(planck_band(T, lam))
        dLdT = float(planck_band(T+0.5, lam) - planck_band(T-0.5, lam))
        row[f"{T:.0f}K"] = dict(radiance=L, dL_per_K=dLdT, relative_sensitivity_pct=100*dLdT/L)
    band_cmp[bname] = row
results["band_comparison"] = band_cmp

# 常温域の輝度比（TIR は MWIR の何倍の信号を出すか）
lam_m, lam_t = BANDS["MWIR(HotSat-2) 3.7-4.95um"], BANDS["TIR(Landsat/ECOSTRESS) 8-12um"]
results["ambient_radiance_ratio_TIR_over_MWIR"] = {
    f"{T:.0f}K": float(planck_band(T, lam_t)/planck_band(T, lam_m)) for T in (270.0, 280.0, 290.0)}


# ===== C1/C2: 熱慣性による夜間冷却の違い =====
# 日没後の地表面温度低下は、半無限体への一定熱流束の解で近似できる:
#   ΔT(t) = 2*Q*sqrt(t) / (P*sqrt(pi))     P = sqrt(k*rho*c) [J m^-2 K^-1 s^-1/2]
# 含水率が上がると k も rho*c も上がるので P が増え、冷えにくくなる。
def night_cooling(P, Q, t_s):
    return 2.0*Q*np.sqrt(t_s)/(P*np.sqrt(np.pi))


THERMAL_INERTIA = {   # P [J m^-2 K^-1 s^-1/2]
    "乾燥砂・乾燥表土": 600.0,
    "湿潤土（冠水後）": 2000.0,
    "アスファルト舗装（乾）": 1200.0,
    "アスファルト舗装（湿）": 1600.0,
    "水面": 1550.0,
}
Q_NIGHT = 60.0   # W/m2 晴天夜の正味長波放射損失（典型値）
cooling = {}
for hours in (3.0, 6.0, 9.0):
    t = hours*3600.0
    row = {k: float(night_cooling(P, Q_NIGHT, t)) for k, P in THERMAL_INERTIA.items()}
    row["乾燥−湿潤 の差（裸地）"] = row["乾燥砂・乾燥表土"] - row["湿潤土（冠水後）"]
    row["乾−湿 の差（舗装）"] = row["アスファルト舗装（乾）"] - row["アスファルト舗装（湿）"]
    cooling[f"日没後{hours:.0f}h"] = row
results["night_cooling_by_thermal_inertia"] = cooling

# 蒸発冷却の寄与（漏水域は水が供給され続けるので蒸発が止まらない）
# 潜熱フラックス LE を地表面が負担する分の温度低下: dT = LE / (4*eps*sigma*T^3 + h)
def evap_cooling(LE, T=285.0, eps=0.96, h=10.0):
    return LE/(4*eps*SIGMA*T**3 + h)


results["evaporative_cooling"] = {
    "微湿（LE=20W/m2）": float(evap_cooling(20)),
    "湿潤（LE=60W/m2）": float(evap_cooling(60)),
    "飽和・湧出（LE=120W/m2）": float(evap_cooling(120)),
    "note": "漏水域は水が供給され続けるため蒸発が持続する。冠水後の乾いていく地面との違いはここ",
}


# ===== C3: 積雪期の屋根 ── 暖房の有無で屋根雪の表面温度が変わるか =====
# 定常の1次元熱収支を解く。屋根雪の底面は、暖房ありなら融解して0C、暖房なしなら断熱。
# 雪表面: 屋内からの伝導流入 = 放射損失 + 対流損失
def snow_surface_temp(q_roof, snow_m, k_snow, T_air, T_sky, h_conv, eps=0.99):
    """q_roof: 屋根から雪底面に入る熱流束 [W/m2]（暖房なしなら0）"""
    def balance(Ts):
        cond_in = q_roof if snow_m <= 0 else q_roof   # 定常なので雪層を通る流束は q_roof
        rad_out = eps*SIGMA*(Ts**4 - T_sky**4)
        conv_out = h_conv*(Ts - T_air)
        return cond_in - rad_out - conv_out
    return brentq(balance, 200.0, 320.0, xtol=1e-4)


T_AIR_W = 268.0    # -5C
T_SKY_W = 235.0    # 晴天夜の実効天空温度
H_CONV = 10.0      # W/m2K 微風
snow = {}
for label, U, Tin in [("暖房あり・断熱悪い住宅 (U=1.5, 室温20C)", 1.5, 293.0),
                      ("暖房あり・標準住宅 (U=0.8, 室温20C)", 0.8, 293.0),
                      ("暖房あり・高断熱住宅 (U=0.3, 室温20C)", 0.3, 293.0),
                      ("暖房なし（停電・避難後）", 0.0, 268.0)]:
    # 屋根から雪底面への熱流束。雪の熱抵抗も直列に入る（雪20cm, k=0.15）
    R_snow = 0.20/0.15
    q = 0.0 if U == 0 else (Tin - T_AIR_W)/(1.0/U + R_snow)
    Ts = snow_surface_temp(q, 0.20, 0.15, T_AIR_W, T_SKY_W, H_CONV)
    snow[label] = dict(q_roof_W_m2=float(q), snow_surface_T=float(Ts),
                       delta_vs_air=float(Ts - T_AIR_W))
base = snow["暖房なし（停電・避難後）"]["snow_surface_T"]
for k, v in snow.items():
    v["contrast_vs_unheated"] = float(v["snow_surface_T"] - base)
results["snow_roof"] = snow


# ===== C4: 太陽光パネル ── 発電中と停止中の温度差 =====
# パネルに入る日射のうち、電気に変換された分だけ熱にならない。
# 停止（系統遮断・破損）すると全量が熱になり、パネル温度が上がる。
def pv_temp(G, eta, T_air=298.0, h=20.0, eps=0.90, T_sky=270.0, alpha=0.90):
    """G: 日射 [W/m2], eta: 発電効率（停止時は0）"""
    def balance(T):
        absorbed = alpha*G - eta*G
        rad = eps*SIGMA*(T**4 - T_sky**4)
        conv = h*(T - T_air)
        return absorbed - rad - conv
    return brentq(balance, 250.0, 400.0, xtol=1e-4)


pv = {}
for G in (400.0, 800.0):
    t_on = pv_temp(G, 0.20)
    t_off = pv_temp(G, 0.0)
    pv[f"日射{G:.0f}W/m2"] = dict(T_generating=float(t_on), T_stopped=float(t_off),
                                  contrast=float(t_off - t_on))
results["pv_panel"] = pv


# ===== 3.5m画素・雑音を踏まえた足切り =====
# TIRを使う前提での実効NEdT（Landsat TIRS 実力値 0.3K級、ECOSTRESS 0.3K級）
NEDT_TIR = 0.3
NOISE_COMMON = 1.5   # ベースライン気象条件差の正規化残差（テーマ1の二重差分の実績に準拠）
screen = {
    "C1 冠水後の浸水域復元": dict(
        signal=cooling["日没後6h"]["乾燥−湿潤 の差（裸地）"], npix=100, sensor="TIR",
        note="日没後6hの裸地。舗装面では差が小さくなるので市街地は苦しい"),
    "C2 地中漏水スクリーニング": dict(
        signal=cooling["日没後6h"]["乾−湿 の差（舗装）"] + results["evaporative_cooling"]["湿潤（LE=60W/m2）"],
        npix=2, sensor="TIR", note="漏水域は数m規模。Landsat100m/ECOSTRESS70mでは1画素未満で希釈される"),
    "C3 積雪期の暖房停止地区": dict(
        signal=snow["暖房あり・標準住宅 (U=0.8, 室温20C)"]["contrast_vs_unheated"], npix=4,
        sensor="TIR", note="住宅1棟=Landsat100mでは1画素未満。街区集約が前提"),
    "C4 被災PVの発電停止判定": dict(
        signal=pv["日射800W/m2"]["contrast"], npix=20, sensor="TIR",
        note="メガソーラーのアレイ単位なら画素数は稼げる。住宅用は不可"),
}
for k, v in screen.items():
    v["noise"] = float(np.sqrt(NOISE_COMMON**2 + (NEDT_TIR/np.sqrt(v["npix"]))**2))
    v["snr"] = float(v["signal"]/v["noise"])
    v["verdict"] = ("有望" if v["snr"] >= 3 else "限界域" if v["snr"] >= 1 else "不可")
results["screening"] = screen

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_candidate_screen.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------- 出力 ----------
print("=== 常温域での MWIR と TIR の感度差 ===")
for b, row in band_cmp.items():
    r = row["280K"]
    print(f"  {b}: 280Kで 輝度{r['radiance']:.3f} W/m2/sr、1Kあたり{r['relative_sensitivity_pct']:.1f}%変化")
print("  → TIRの輝度は MWIR の " +
      ", ".join(f"{k}:{v:.0f}倍" for k, v in results['ambient_radiance_ratio_TIR_over_MWIR'].items()))

print("\n=== 熱慣性による夜間冷却量 [K] ===")
for h, row in cooling.items():
    print(f"  {h}: " + ", ".join(f"{k}={v:.1f}" for k, v in row.items()))

print("\n=== 蒸発冷却 [K] ===")
for k, v in results["evaporative_cooling"].items():
    if k != "note":
        print(f"  {k}: {v:.2f}")

print("\n=== 積雪期の屋根雪 表面温度 ===")
for k, v in snow.items():
    print(f"  {k}: q={v['q_roof_W_m2']:.1f}W/m2, 雪面{v['snow_surface_T']-273.15:+.2f}C, "
          f"外気比{v['delta_vs_air']:+.2f}K, 暖房なし比{v['contrast_vs_unheated']:+.2f}K")

print("\n=== PVパネル 発電中 vs 停止中 ===")
for k, v in pv.items():
    print(f"  {k}: 発電中{v['T_generating']-273.15:.1f}C / 停止中{v['T_stopped']-273.15:.1f}C → 差{v['contrast']:.1f}K")

print("\n=== 足切り（TIR前提・雑音RSS） ===")
for k, v in screen.items():
    print(f"  {k}: 信号{v['signal']:.1f}K / 雑音{v['noise']:.1f}K / SNR {v['snr']:.1f} → {v['verdict']}")
    print(f"      {v['note']}")
