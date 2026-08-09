"""T2-PoC3: 冠水後の地表面が「どれだけ、いつまで」冷たいかの正直な試算

`t2_candidate_screen.py` の候補C1（冠水後の浸水域復元）は、半無限体への一定熱流束という
粗い近似で夜間冷却量の差 11.6 K / SNR 7.7 を出した。この近似には2つの嘘がある。

  1. 蒸発潜熱を無視している。湿った地面は昼に蒸発で強く冷えるので、夜の出発点が違う
  2. 乾湿でアルベドと射出率が違う（湿ると黒くなり、日射をより多く吸う）——差を縮める向き

どちらも符号が既知なので、無視した推定は上振れする。ここでは 1次元熱伝導 + 地表面熱収支を
時間発展で解き、日変化を通した実効の差を出す。あわせて、提案の核心である
**「冠水で濡れた地面」と「降雨で濡れた地面」を乾燥速度の差で分離できるか**を評価する。

出力: theme2_ライフライン復旧/poc/out/t2_wetsoil_diurnal.json
"""
import json
import os

import numpy as np

SIGMA = 5.670374e-8
RHO_CP_AIR = 1204.0        # J m^-3 K^-1
GAMMA = 0.0665             # 乾湿計定数 [kPa/K]

# ---- 地表面の型 -------------------------------------------------------------
# k [W/mK], rho_c [J/m^3K], albedo, emissivity, beta(蒸発効率 0-1)
SURFACES = {
    "乾燥裸地":        dict(k=0.30, rho_c=1.20e6, albedo=0.25, eps=0.94, beta=0.05),
    "冠水後の飽和土":  dict(k=1.60, rho_c=2.80e6, albedo=0.12, eps=0.97, beta=0.80),
    "降雨で濡れた表土": dict(k=0.55, rho_c=1.55e6, albedo=0.18, eps=0.96, beta=0.35),
    "舗装（乾）":      dict(k=0.75, rho_c=1.90e6, albedo=0.12, eps=0.95, beta=0.02),
    "舗装（湿）":      dict(k=0.95, rho_c=2.10e6, albedo=0.09, eps=0.96, beta=0.20),
}

# ---- 気象条件（台風通過後の晴天。9月・関東平野を想定）-------------------------
T_AIR_MEAN = 297.15        # 24 C
T_AIR_AMP = 4.0            # 20-28 C
T_AIR_PEAK_H = 14.0
RH = 0.70
S_MAX = 750.0              # 快晴正午の全天日射 [W/m2]
SUNRISE_H, SUNSET_H = 5.5, 18.3
EPS_SKY = 0.80             # 快晴の大気射出率（湿潤な日本の夏秋）
H_CONV = 15.0              # 対流熱伝達率 [W/m2K]（微風）
T_DEEP = 296.15            # 深部（2m）の温度


def e_sat(T_k):
    """飽和水蒸気圧 [kPa]（Tetens）"""
    t = T_k - 273.15
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def air_temp(t_h):
    return T_AIR_MEAN - T_AIR_AMP * np.cos(2 * np.pi * (t_h - T_AIR_PEAK_H) / 24.0)


def solar(t_h):
    if not (SUNRISE_H < t_h < SUNSET_H):
        return 0.0
    return S_MAX * np.sin(np.pi * (t_h - SUNRISE_H) / (SUNSET_H - SUNRISE_H))


def build_grid(depth=2.0, n=48, dz0=0.004):
    """地表近くを細かく、深部を粗く（等比）"""
    r = 1.0
    for _ in range(60):                       # dz0*(r^n - 1)/(r-1) = depth を解く
        f = dz0 * (r**n - 1) / (r - 1) - depth if abs(r - 1) > 1e-9 else dz0 * n - depth
        df = (dz0 * (n * r**(n - 1) * (r - 1) - (r**n - 1)) / (r - 1)**2) if abs(r - 1) > 1e-9 else 0.0
        r_new = r - f / df if df != 0 else r * 1.05
        r = min(max(r_new, 1.0001), 1.5)
    dz = dz0 * r ** np.arange(n)
    dz *= depth / dz.sum()
    z_c = np.cumsum(dz) - dz / 2.0
    return dz, z_c


def run_surface(cfg, days=5, dt=2.0, beta_series=None):
    """地表面熱収支つき1次元熱伝導を days 日ぶん回し、最終日の Ts(t) を返す。

    beta_series: t_h(通し時間 h) -> beta を返す関数。None なら cfg["beta"] 固定。
    """
    dz, z_c = build_grid()
    k, rho_c, alb, eps = cfg["k"], cfg["rho_c"], cfg["albedo"], cfg["eps"]
    T = np.full(dz.size, T_DEEP)
    n_steps = int(days * 86400 / dt)
    rec_t, rec_Ts = [], []
    # 節点間の熱コンダクタンス [W/m2K]
    dist = 0.5 * (dz[:-1] + dz[1:])
    cond = k / dist

    for step in range(n_steps):
        t_s = step * dt
        t_h_abs = t_s / 3600.0
        t_h = t_h_abs % 24.0
        Ta = air_temp(t_h)
        S = solar(t_h)
        beta = cfg["beta"] if beta_series is None else beta_series(t_h_abs)
        Ts = T[0]

        Rn = (1 - alb) * S + eps * (EPS_SKY * SIGMA * Ta**4 - SIGMA * Ts**4)
        H = H_CONV * (Ts - Ta)
        LE = beta * (H_CONV / GAMMA) * (e_sat(Ts) - RH * e_sat(Ta))
        LE = max(LE, 0.0)                      # 結露は扱わない（夜の下振れを作らないため保守的）
        G0 = Rn - H - LE                       # 土中へ入る熱流束 [W/m2]

        F = cond * (T[:-1] - T[1:])            # 節点間の下向き熱流束
        dT = np.empty_like(T)
        dT[0] = (G0 - F[0]) / (rho_c * dz[0])
        dT[1:-1] = (F[:-1] - F[1:]) / (rho_c * dz[1:-1])
        dT[-1] = 0.0                           # 深部固定
        T = T + dt * dT

        if t_s >= (days - 1) * 86400 and step % int(300 / dt) == 0:
            rec_t.append(t_h)
            rec_Ts.append(T[0])
    return np.array(rec_t), np.array(rec_Ts)


def sample(t, Ts, hour):
    return float(np.interp(hour, t, Ts))


results = {}

# ===== 1. 定常状態の乾湿コントラスト（日変化を通した実効値）=====
curves = {}
for name, cfg in SURFACES.items():
    t, Ts = run_surface(cfg)
    curves[name] = (t, Ts)

OVERPASS = {
    "深夜 01:30 (Aqua/ECOSTRESS夜)": 1.5,
    "夜明け前 04:30": 4.5,
    "午前 10:30 (Landsat 昼)": 10.5,
    "正午過ぎ 13:30 (TRISHNA/Aqua 昼)": 13.5,
    "夕 17:00": 17.0,
}
contrast = {}
for label, hour in OVERPASS.items():
    row = {}
    for name, (t, Ts) in curves.items():
        row[name] = round(sample(t, Ts, hour) - 273.15, 2)
    row["冠水後 − 乾燥裸地"] = round(row["冠水後の飽和土"] - row["乾燥裸地"], 2)
    row["冠水後 − 降雨で濡れた表土"] = round(row["冠水後の飽和土"] - row["降雨で濡れた表土"], 2)
    row["舗装 湿 − 乾"] = round(row["舗装（湿）"] - row["舗装（乾）"], 2)
    contrast[label] = row
results["diurnal_contrast_C"] = contrast

results["diurnal_range_K"] = {
    name: round(float(Ts.max() - Ts.min()), 2) for name, (t, Ts) in curves.items()}

# ===== 2. 乾燥の時間発展 ── 冠水域と降雨域を分離できるか =====
# 降雨は表層数cmしか濡らさないので蒸発可能水量が小さく、beta は速く落ちる。
# 冠水は土層全体が飽和するので beta は緩やかにしか落ちない。
# beta(t) = beta0 * exp(-t/tau) + beta_floor
DRYING = {
    "冠水域（飽和・排水も遅い）": dict(beta0=0.80, tau_h=140.0, floor=0.05),
    "降雨域（表層のみ）":         dict(beta0=0.45, tau_h=22.0, floor=0.05),
}
drying = {}
for name, d in DRYING.items():
    cfg = dict(SURFACES["冠水後の飽和土"])
    per_day = {}
    for day in (1, 2, 3, 5, 7):
        b = d["floor"] + (d["beta0"] - d["floor"]) * np.exp(-24.0 * day / d["tau_h"])
        # その日の熱物性も含水に応じて補間する（beta を含水の代理に使う）
        f = (b - d["floor"]) / (d["beta0"] - d["floor"])
        cfg_d = dict(
            k=0.30 + (1.60 - 0.30) * f,
            rho_c=1.20e6 + (2.80e6 - 1.20e6) * f,
            albedo=0.25 - (0.25 - 0.12) * f,
            eps=0.94 + (0.97 - 0.94) * f,
            beta=b,
        )
        t, Ts = run_surface(cfg_d)
        dry_t, dry_Ts = curves["乾燥裸地"]
        per_day[f"{day}日後"] = dict(
            beta=round(float(b), 3),
            深夜0130=round(sample(t, Ts, 1.5) - sample(dry_t, dry_Ts, 1.5), 2),
            午前1030=round(sample(t, Ts, 10.5) - sample(dry_t, dry_Ts, 10.5), 2),
            午後1330=round(sample(t, Ts, 13.5) - sample(dry_t, dry_Ts, 13.5), 2),
        )
    drying[name] = per_day
results["drying_contrast_vs_dry_bare_K"] = drying

# 分離可能性: 同じ日に見たときの「冠水域 − 降雨域」
sep = {}
for day in (1, 2, 3, 5, 7):
    a = drying["冠水域（飽和・排水も遅い）"][f"{day}日後"]
    b = drying["降雨域（表層のみ）"][f"{day}日後"]
    sep[f"{day}日後"] = {kk: round(a[kk] - b[kk], 2) for kk in ("深夜0130", "午前1030", "午後1330")}
results["flood_minus_rain_K"] = sep

# ===== 3. 交絡 ── 平時の被覆が違えば符号が変わりうる =====
# (a) 冠水で作物が枯死・倒伏すると蒸散が止まる。信号（蒸発冷却）と逆符号になりうる
# (b) 水田・湿地は平時から濡れており、冠水してもコントラストが立たない
CONFOUND = {
    "健全な植生（平時の畑地）":       dict(k=0.55, rho_c=1.60e6, albedo=0.20, eps=0.98, beta=0.60),
    "冠水→枯死・倒伏＋飽和土":       dict(k=1.60, rho_c=2.80e6, albedo=0.14, eps=0.97, beta=0.80),
    "冠水→枯死し、7日後に土も乾く":  dict(k=0.45, rho_c=1.35e6, albedo=0.22, eps=0.95, beta=0.15),
    "水田（平時から湛水）":           dict(k=1.60, rho_c=3.20e6, albedo=0.12, eps=0.98, beta=0.95),
    "水田（冠水後）":                 dict(k=1.60, rho_c=3.20e6, albedo=0.12, eps=0.98, beta=0.95),
}
conf_curves = {n: run_surface(c) for n, c in CONFOUND.items()}
confound = {}
for label, hour in (("午前 10:30 (Landsat 昼)", 10.5), ("深夜 01:30", 1.5)):
    base = sample(*conf_curves["健全な植生（平時の畑地）"], hour)
    row = {n: round(sample(*conf_curves[n], hour) - 273.15, 2) for n in CONFOUND}
    row["冠水直後 − 平時の畑地"] = round(
        sample(*conf_curves["冠水→枯死・倒伏＋飽和土"], hour) - base, 2)
    row["7日後に土も乾いた場合 − 平時の畑地"] = round(
        sample(*conf_curves["冠水→枯死し、7日後に土も乾く"], hour) - base, 2)
    row["水田 冠水後 − 平時"] = 0.0
    confound[label] = row
results["confounders_C"] = confound

# ===== 4. 混合画素 ── 100m画素の中で、どんな地目なら信号が生き残るか =====
# 面の温度差がそのまま画素の温度差になるわけではない。屋根・舗装は水を保持しないので
# 平時と浸水後で変わらず、その被覆率のぶんだけ信号は薄まる。
# 混合は温度ではなく輝度で行う（TIRでは L ∝ T^4.5 程度なので温度平均は過小評価になる）。
C1_, C2_ = 1.191042e8, 1.4387752e4
LAM_TIR = np.linspace(8.0, 12.0, 161)


def band_radiance(T_k):
    B = C1_ / (LAM_TIR**5 * (np.exp(C2_ / (LAM_TIR * T_k)) - 1.0))
    return float(np.trapezoid(B, LAM_TIR))


def radiance_to_T(L):
    lo, hi = 200.0, 400.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if band_radiance(mid) < L:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def mix_T(parts):
    """parts: [(被覆率, 温度K), ...] → 輝度平均の等価輝度温度 [K]"""
    return radiance_to_T(sum(f * band_radiance(T) for f, T in parts))


H_OBS = 10.5
_T = {n: sample(*curves[n], H_OBS) for n in curves}
_TC = {n: sample(*conf_curves[n], H_OBS) for n in conf_curves}
# 3日後の冠水土（乾燥裸地からのコントラストを引く）
T_FLOOD_D3 = _T["乾燥裸地"] + drying["冠水域（飽和・排水も遅い）"]["3日後"]["午前1030"]
T_ROOF = _T["舗装（乾）"]              # 屋根は水を被らない。乾いた人工面の代表として舗装乾を使う

SCENES = {
    "河川敷・グラウンド・造成地（裸地100%）":
        ([(1.0, _T["乾燥裸地"])], [(1.0, T_FLOOD_D3)]),
    "インフラ施設構内（砕石敷0.7＋建屋屋根0.3）":
        ([(0.7, _T["乾燥裸地"]), (0.3, T_ROOF)],
         [(0.7, T_FLOOD_D3), (0.3, T_ROOF)]),
    "農地・作付け前の裸地":
        ([(1.0, _T["乾燥裸地"])], [(1.0, T_FLOOD_D3)]),
    "農地・作付け中（健全な植生）":
        ([(1.0, _TC["健全な植生（平時の畑地）"])],
         [(1.0, _TC["冠水→枯死・倒伏＋飽和土"])]),
    "水田（平時から湛水）":
        ([(1.0, _TC["水田（平時から湛水）"])], [(1.0, _TC["水田（冠水後）"])]),
    "郊外住宅地（屋根0.3＋舗装0.3＋庭の植生0.4）":
        ([(0.3, T_ROOF), (0.3, _T["舗装（乾）"]), (0.4, _TC["健全な植生（平時の畑地）"])],
         [(0.3, T_ROOF), (0.3, _T["舗装（乾）"]), (0.4, _TC["冠水→枯死・倒伏＋飽和土"])]),
    "稠密市街地（屋根0.4＋舗装0.4＋裸地0.2）":
        ([(0.4, T_ROOF), (0.4, _T["舗装（乾）"]), (0.2, _T["乾燥裸地"])],
         [(0.4, T_ROOF), (0.4, _T["舗装（乾）"]), (0.2, T_FLOOD_D3)]),
}
mixed = {}
for name, (pre, post) in SCENES.items():
    t_pre, t_post = mix_T(pre), mix_T(post)
    d = t_post - t_pre
    noise = float(np.sqrt(1.5**2 + (0.3 / np.sqrt(25))**2))
    mixed[name] = dict(平時=round(t_pre - 273.15, 2), 浸水3日後=round(t_post - 273.15, 2),
                       差K=round(d, 2), snr=round(abs(d) / noise, 2),
                       verdict=("有望" if abs(d) / noise >= 3 else
                                "限界域" if abs(d) / noise >= 1.5 else "不可"))
results["mixed_pixel_day3_1030"] = mixed

# ===== 5. 足切り =====
# 雑音: テーマ1の二重差分で確立した「ベースラインとの気象条件差の正規化残差」1.5K に、
# TIR センサの NEdT（Landsat TIRS / ECOSTRESS とも 0.3K級）を画素数で割ったものを RSS。
NOISE_BASE = 1.5
NEDT = 0.3
screen = {}
for label, sig, npix, note in [
    ("冠水域 vs 乾燥裸地・午前1030（3日後）",
     drying["冠水域（飽和・排水も遅い）"]["3日後"]["午前1030"], 25,
     "Landsat 100m。農地・河川敷なら1区画で数画素は取れる"),
    ("冠水域 vs 降雨域・午前1030（3日後）",
     sep["3日後"]["午前1030"], 25,
     "**提案の核心**。降雨で濡れただけの地面を落とせるか"),
    ("冠水域 vs 降雨域・深夜0130（3日後）",
     sep["3日後"]["深夜0130"], 25,
     "夜間は熱慣性が効くが蒸発が止まるので差が縮む"),
    ("舗装面の乾湿・午前1030（濡れている間の定常値）",
     contrast["午前 10:30 (Landsat 昼)"]["舗装 湿 − 乾"], 25,
     "**この数字は使えない**。舗装は保水しないので半日〜1日で乾き、3日後には消える。"
     "市街地の可否は上の混合画素の表（稠密市街地 SNR 1.0）で判断すること"),
]:
    noise = float(np.sqrt(NOISE_BASE**2 + (NEDT / np.sqrt(npix))**2))
    screen[label] = dict(signal_K=round(abs(sig), 2), noise_K=round(noise, 2),
                         snr=round(abs(sig) / noise, 2), note=note,
                         verdict=("有望" if abs(sig) / noise >= 3 else
                                  "限界域" if abs(sig) / noise >= 1.5 else "不可"))
results["screening"] = screen

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_wetsoil_diurnal.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------- 出力 ----------
print("=== 日変化幅（地表面温度） ===")
for k, v in results["diurnal_range_K"].items():
    print(f"  {k}: {v} K")

print("\n=== 通過時刻ごとの地表面温度 [C] と乾湿コントラスト ===")
for label, row in contrast.items():
    print(f"  {label}")
    for k, v in row.items():
        mark = "  <<<" if k.startswith(("冠水後 −", "舗装 湿")) else ""
        print(f"      {k}: {v:+.2f}{mark}")

print("\n=== 冠水域・降雨域の乾燥に伴うコントラスト減衰（乾燥裸地との差 [K]） ===")
for name, per_day in drying.items():
    print(f"  {name}")
    for d, v in per_day.items():
        print(f"      {d}: beta={v['beta']:.2f}  夜{v['深夜0130']:+.1f}  "
              f"午前{v['午前1030']:+.1f}  午後{v['午後1330']:+.1f}")

print("\n=== 冠水域 − 降雨域（この差が提案の核心） [K] ===")
for d, v in sep.items():
    print(f"  {d}: 夜{v['深夜0130']:+.2f}  午前{v['午前1030']:+.2f}  午後{v['午後1330']:+.2f}")

print("\n=== 交絡（平時の被覆が違うと符号が変わりうる） [C] ===")
for label, row in confound.items():
    print(f"  {label}")
    for k, v in row.items():
        print(f"      {k}: {v:+.2f}")

print("\n=== 混合画素（100m）で、平時→浸水3日後・午前10:30 に画素温度がどう動くか ===")
for k, v in mixed.items():
    print(f"  {k}")
    print(f"      平時{v['平時']:+.2f}C → 浸水3日後{v['浸水3日後']:+.2f}C  差{v['差K']:+.2f}K  "
          f"SNR {v['snr']:.1f} → {v['verdict']}")

print("\n=== 足切り ===")
for k, v in screen.items():
    print(f"  {k}: 信号{v['signal_K']}K / 雑音{v['noise_K']}K / SNR {v['snr']} → {v['verdict']}")
    print(f"      {v['note']}")
