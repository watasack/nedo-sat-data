"""PoC-1: MWIR放射伝達 誤差バジェット計算機
衛星熱赤外（HotSat-2級, MWIR 3.4-4.2um, 3.5m画素）でプラント保温劣化の
数℃シグナルが検出可能かを、測定方式別（絶対温度/シーン内相対/兄弟資産差分）に定量評価。
物理: L_sensor = tau*(eps*B(Ts) + (1-eps)*L_sky) + (1-tau)*B(T_atm)
"""
import numpy as np
from scipy.optimize import brentq
import json, csv, os

C1 = 1.191042e8   # W/m2/sr/um^-4 (first radiation const / pi, for spectral radiance in um)
C2 = 1.4387752e4  # um K
LAM = np.linspace(3.4, 4.2, 81)  # um, HotSat級MWIRバンド想定

def planck_band(T):
    """バンド積分放射輝度 W/m2/sr"""
    T = np.atleast_1d(T).astype(float)[:, None]
    B = C1 / (LAM**5 * (np.exp(C2/(LAM*T)) - 1.0))
    out = np.trapezoid(B, LAM, axis=1)
    return out if out.size > 1 else out[0]

def tb_from_radiance(L):
    """バンド積分輝度→輝度温度（数値反転）"""
    return brentq(lambda T: planck_band(T) - L, 150.0, 500.0, xtol=1e-4)

def sensor_radiance(Ts, eps, tau, T_sky, T_atm=285.0):
    return tau*(eps*planck_band(Ts) + (1-eps)*planck_band(T_sky)) + (1-tau)*planck_band(T_atm)

def apparent_tb(Ts, eps, tau, T_sky, T_atm=285.0):
    return tb_from_radiance(sensor_radiance(Ts, eps, tau, T_sky, T_atm))

# ---------- 前提パラメータ（出典・根拠はレポートに記載） ----------
TA   = 288.0   # 夜間外気温 15C
TAU  = 0.75    # 中緯度夏夜MWIR大気透過(0.6-0.85の中央)
SKY_CLEAR, SKY_PART, SKY_OVC = 240.0, 262.0, 280.0  # 実効天空温度
NEDT_SENSOR = [0.5, 1.0, 2.0]  # K（HotSat-2実力値は非公開、公表"<2K"より範囲設定）
EPS_CASES = {"新品アルミ外装": 0.10, "風化アルミ外装": 0.25, "経年・塗装劣化": 0.40, "塗装/錆/非金属": 0.90}

results = {}

# ---------- (A) 天空条件スイング（時系列比較の最大ノイズ源） ----------
Ts = 310.0  # 表面35C級の保温外装
sky_swing = {}
for name, eps in EPS_CASES.items():
    tb_c = apparent_tb(Ts, eps, TAU, SKY_CLEAR)
    tb_o = apparent_tb(Ts, eps, TAU, SKY_OVC)
    sky_swing[name] = dict(eps=eps, tb_clear=tb_c, tb_ovc=tb_o, swing=tb_o - tb_c)
results["sky_swing"] = sky_swing

# ---------- (B) 放射率不確かさ→見かけ温度誤差 ----------
eps_err = {}
for name, eps in EPS_CASES.items():
    d = 0.05
    tb1 = apparent_tb(Ts, max(eps-d, 0.02), TAU, SKY_CLEAR)
    tb2 = apparent_tb(Ts, min(eps+d, 0.98), TAU, SKY_CLEAR)
    eps_err[name] = dict(eps=eps, dtb_per_eps005=abs(tb2-tb1)/2)
results["eps_uncertainty"] = eps_err

# ---------- (C) 実効NEdT（感度劣化） ----------
def sensitivity_gain(Ts, eps, tau, T_sky):
    """dTb/dTs: 表面温度1K変化が輝度温度に写る割合"""
    d = 0.5
    return (apparent_tb(Ts+d, eps, tau, T_sky) - apparent_tb(Ts-d, eps, tau, T_sky)) / (2*d)

nedt_eff = {}
for name, eps in EPS_CASES.items():
    g = sensitivity_gain(Ts, eps, TAU, SKY_CLEAR)
    nedt_eff[name] = dict(eps=eps, gain=g, nedt_eff={f"{n}K": n/g for n in NEDT_SENSOR})
results["nedt_effective"] = nedt_eff

# ---------- (D) 画素内希釈（fill fraction） ----------
def diluted_tb(f, dT, eps, Ts_bg=None):
    Ts_bg = TA if Ts_bg is None else Ts_bg
    L = f*sensor_radiance(Ts_bg+dT, eps, TAU, SKY_CLEAR) + (1-f)*sensor_radiance(Ts_bg, eps, TAU, SKY_CLEAR)
    return tb_from_radiance(L) - tb_from_radiance(sensor_radiance(Ts_bg, eps, TAU, SKY_CLEAR))

dilution = {}
for label, f, dT in [("個別配管(f=0.15,ΔT=5K)", 0.15, 5.0), ("配管ラック帯(f=0.5,ΔT=5K)", 0.5, 5.0),
                     ("タンク屋根パッチ(f=1.0,ΔT=3K)", 1.0, 3.0), ("加熱炉天面(f=1.0,ΔT=15K)", 1.0, 15.0)]:
    dilution[label] = diluted_tb(f, dT, 0.30, Ts_bg=305.0)
results["dilution"] = dilution

# ---------- (E) 測定方式別 誤差バジェット ----------
# 対象ケース: 風化アルミ外装 eps=0.25、集約はユニットあたりN=50画素
eps0 = 0.25
g = sensitivity_gain(Ts, eps0, TAU, SKY_CLEAR)
nedt1 = 1.0/g                      # センサNEdT=1K時の実効値
Npix = 50
budget = {
  "絶対温度（撮像間差分）": {
    "ε不確かさ(±0.05)": eps_err["風化アルミ外装"]["dtb_per_eps005"],
    "天空条件変動(晴⇔曇)": abs(sky_swing["風化アルミ外装"]["swing"]),
    "大気透過残差(τ±0.05)": abs(apparent_tb(Ts, eps0, 0.80, SKY_CLEAR) - apparent_tb(Ts, eps0, 0.70, SKY_CLEAR))/2,
    "実効NEdT(センサ1K)": nedt1,
    "位置合わせ残差(境界画素)": 2.0,
  },
  "シーン内相対比較（同一資産内）": {
    "資産内ε不均一(±0.02)": eps_err["風化アルミ外装"]["dtb_per_eps005"]*(0.02/0.05),
    "実効NEdT×√2(画素対)": nedt1*np.sqrt(2),
    "PSF混合(パッチ境界)": 0.8,
    # 天空・大気・平均εは共通モードで相殺
  },
  "兄弟資産差分（ユニット集約N=50px）": {
    "資産間ε差(±0.05)": eps_err["風化アルミ外装"]["dtb_per_eps005"],
    "実効NEdT×√2/√N": nedt1*np.sqrt(2)/np.sqrt(Npix),
    "負荷・構造の残差差異": 0.5,
    "位置合わせ(エロージョン後)": 0.3,
  },
}
tot = {}
for mode, comps in budget.items():
    v = np.array(list(comps.values()))
    tot[mode] = dict(components=comps, rss=float(np.sqrt((v**2).sum())), worst=float(v.sum()))
results["budget"] = tot
results["signals"] = {"タンク屋根パッチ(+3K,f=1)": 3.0*g,  # 輝度温度に写る量
                      "ユニット面的劣化(+1K)": 1.0*g,
                      "加熱炉保温不良(+15K)": 15.0*g}
results["meta"] = dict(Ts=Ts, Ta=TA, tau=TAU, eps_ref=eps0, gain_ref=g, Npix=Npix,
                       note="gain=dTb/dTs: 表面1Kが輝度温度に写る割合")

# ---------- (F) 検出ケース別SNR（適切な推定器・画素集約を適用） ----------
# シーン内コントラスト: パッチ画素集約でNEdTは/√Np、ε資産内不均一±0.02、PSF混合
def scene_contrast_noise(n_patch):
    e = eps_err["風化アルミ外装"]["dtb_per_eps005"]*(0.02/0.05)
    return float(np.sqrt(e**2 + (nedt1*np.sqrt(2)/np.sqrt(n_patch))**2 + 0.8**2))
# 兄弟差分（静的）: 資産間ε差が支配的
sib_static = tot["兄弟資産差分（ユニット集約N=50px）"]["rss"]
# 兄弟差分の時間変化（二重差分）: 静的ε差は時間相殺、残るは差動ε経年0.3K/期+NEdT項+負荷残差差0.3K
dd_noise = float(np.sqrt(0.3**2 + (nedt1*2/np.sqrt(Npix))**2 + 0.3**2))
cases = {
  "加熱炉・高温配管系の保温不良(+15K)": dict(signal=15.0*g, noise=scene_contrast_noise(6), estimator="シーン内コントラスト(6px集約)"),
  "タンク屋根の劣化パッチ(+3K,100m²≈8px)": dict(signal=3.0*g, noise=scene_contrast_noise(8), estimator="シーン内コントラスト(8px集約)"),
  "タンク屋根の劣化パッチ(+5K)": dict(signal=5.0*g, noise=scene_contrast_noise(8), estimator="シーン内コントラスト(8px集約)"),
  "ユニット面的劣化(+1K) 対双子資産": dict(signal=1.0*g, noise=sib_static, estimator="兄弟差分(静的,単発)"),
  "ユニット面的劣化(+1K) 二重差分×6エポック": dict(signal=1.0*g, noise=dd_noise/np.sqrt(6), estimator="兄弟差分の時間変化(6エポック平均)"),
  "個別配管CUIスポット(f=0.15,+5K)": dict(signal=abs(dilution["個別配管(f=0.15,ΔT=5K)"]), noise=scene_contrast_noise(2), estimator="シーン内コントラスト(2px)"),
}
for c in cases.values():
    c["snr"] = c["signal"]/c["noise"]
    c["verdict"] = "検出可能" if c["snr"] >= 3 else ("限界域(要NEdT実力値)" if c["snr"] >= 0.8 else "単発検出不可")
results["detection_cases"] = cases
for name, c in cases.items():
    print(f"[SNR] {name}: sig={c['signal']:.2f}K noise={c['noise']:.2f}K SNR={c['snr']:.2f} → {c['verdict']} ({c['estimator']})")

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "poc1_results.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---- コンソール要約 ----
print(f"感度ゲイン dTb/dTs @eps={eps0}, tau={TAU}: {g:.3f} → 表面3K差は輝度温度{3*g:.2f}Kに写る")
for name, d in sky_swing.items():
    print(f"[天空スイング] {name}(ε={d['eps']}): 晴→曇で見かけ {d['swing']:+.2f} K")
for mode, t in tot.items():
    print(f"[バジェット] {mode}: RSS={t['rss']:.2f} K, worst={t['worst']:.2f} K")
for sig, v in results["signals"].items():
    print(f"[信号] {sig}: 輝度温度換算 {v:.2f} K")
for label, v in dilution.items():
    print(f"[希釈] {label}: 見かけ {v:+.2f} K")
