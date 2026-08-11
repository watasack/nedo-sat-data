"""T2-PoC1: ライフラインノードの「稼働/停止」判別可能性の物理試算

問い: HotSat-2級（MWIR 3.7-4.95um, 3.5m画素, NEdT<2K）で、発災後にライフライン設備の
稼働/停止を設備単位で判別できるか。判別できる設備とできない設備の境界はどこか。

テーマ1（poc/src/poc1_error_budget.py）との違い:
  テーマ1 = 平時の経年劣化トレンド（数K・多エポック積算が使える）
  テーマ2 = 発災後の稼働/停止（大振幅・単発判定が要る・時間制約がある）
したがって評価軸は「コントラストSNR」だけでなく「停止から検知までの熱時定数」を含む。

物理: L_sensor = tau*(eps*B(Ts) + (1-eps)*L_sky) + (1-tau)*B(T_atm)
出力: theme2_ライフライン復旧/poc/out/t2_node_signature.json
"""
import numpy as np
from scipy.optimize import brentq
import json, os

C1 = 1.191042e8   # W/m2/sr/um^-4
C2 = 1.4387752e4  # um K
LAM = np.linspace(3.7, 4.95, 126)  # um, HotSat-2 実帯域（テーマ1は3.4-4.2の仮定帯域だった）


def planck_band(T):
    T = np.atleast_1d(T).astype(float)[:, None]
    B = C1 / (LAM**5 * (np.exp(C2/(LAM*T)) - 1.0))
    out = np.trapezoid(B, LAM, axis=1)
    return out if out.size > 1 else out[0]


def tb_from_radiance(L):
    return brentq(lambda T: planck_band(T) - L, 150.0, 900.0, xtol=1e-4)


def sensor_radiance(Ts, eps, tau, T_sky, T_atm=285.0):
    return tau*(eps*planck_band(Ts) + (1-eps)*planck_band(T_sky)) + (1-tau)*planck_band(T_atm)


def apparent_tb(Ts, eps, tau, T_sky, T_atm=285.0):
    return tb_from_radiance(sensor_radiance(Ts, eps, tau, T_sky, T_atm))


# ---------- 共通前提（冬季夜間の発災を想定。断水・停電の被害が最も深刻な季節） ----------
TA_WINTER = 278.0   # 冬季夜間外気温 5C
TAU = 0.75          # 中緯度MWIR大気透過（テーマ1と同じ中央値）
SKY_CLEAR = 240.0
NEDT_AT_300K = 2.0  # HotSat-2 公表値 "<2K"。実力値は未公開（09_JSI照会文案.md で照会中）

results = {"meta": dict(band_um=[float(LAM[0]), float(LAM[-1])], T_ambient=TA_WINTER,
                        tau=TAU, T_sky=SKY_CLEAR, nedt_at_300K=NEDT_AT_300K,
                        note="冬季夜間・晴天。放射輝度はバンド積分、輝度温度は数値反転")}


def nedt_at(Tb):
    """NEdTは輝度で定義される。参照300KでのNEdTを輝度換算し、対象輝度温度での等価温度差に直す。
    MWIRは高温側で放射輝度が急峻なので、高温対象ほど輝度温度としてのNEdTは小さくなる。"""
    dL = planck_band(300.0 + NEDT_AT_300K/2) - planck_band(300.0 - NEDT_AT_300K/2)
    dTb = tb_from_radiance(planck_band(Tb) + dL/2) - tb_from_radiance(planck_band(Tb) - dL/2)
    return float(dTb)


# ---------- ライフラインノードのカタログ ----------
# ---------- 熱時定数（停止から何時間で「停止」と分かるか） ----------
# tau = C / (dQ/dT)、dQ/dT は定常運転時の放熱量を温度上昇で割った実効熱コンダクタンス。
# ノードのカタログより先に置く——カタログの tau_h はここから引くため（数値の二重管理を避ける）。
def cooling_tau_hours(mass_kg, c_JkgK, P_loss_W, dT_K):
    C = mass_kg*c_JkgK
    G = P_loss_W/dT_K
    return C/G/3600.0


tau_calc = {
    "変電所 100MVA変圧器": dict(
        tau_h=cooling_tau_hours(mass_kg=6.0e4, c_JkgK=1400, P_loss_W=3.0e5, dT_K=50),
        assume="油+鉄心 60t、実効比熱1400 J/kgK、全損失300kW（効率99.7%の半負荷相当）、油温上昇50K"),
    "清掃工場 ボイラ棟": dict(
        tau_h=cooling_tau_hours(mass_kg=1.5e6, c_JkgK=700, P_loss_W=5.0e6, dT_K=70),
        assume="炉体・耐火物・鉄骨 1500t、実効比熱700 J/kgK、外皮からの放熱5MW相当、外皮温度上昇70K"),
    "地域熱供給プラント 温水系": dict(
        tau_h=cooling_tau_hours(mass_kg=3.0e5, c_JkgK=3000, P_loss_W=2.0e6, dT_K=40),
        assume="蓄熱槽+配管の保有水 300t相当、実効比熱3000 J/kgK、放熱2MW、温度上昇40K"),
    "下水処理場 曝気槽1池": dict(
        tau_h=cooling_tau_hours(mass_kg=6.0e6, c_JkgK=4180, P_loss_W=1.5e6, dT_K=13),
        assume="30x50x4m=6000m3、水の比熱4180 J/kgK、水面1500m2から蒸発+対流で約1kW/m2、水温差13K"),
    "浄水場 沈殿池": dict(
        tau_h=cooling_tau_hours(mass_kg=4.0e6, c_JkgK=4180, P_loss_W=4.0e5, dT_K=3),
        assume="4000m3、水温は外気に対し数K差しかなく、そもそも稼働で駆動されていない"),
    "配水池 5000m3": dict(
        tau_h=cooling_tau_hours(mass_kg=5.0e6, c_JkgK=4180, P_loss_W=2.0e5, dT_K=5),
        assume="覆蓋つき5000m3、覆蓋経由の放熱のみ"),
    "ポンプ場 電動機建屋": dict(
        tau_h=cooling_tau_hours(mass_kg=2.0e5, c_JkgK=900, P_loss_W=5.0e4, dT_K=2),
        assume="建屋躯体200t、比熱900 J/kgK、電動機損失50kW、屋根面温度上昇2K"),
}
for _v in tau_calc.values():
    _v["tau_h"] = float(_v["tau_h"])

# ---------- ライフラインノードのカタログ ----------
# f    : 3.5m画素で見た「熱源が占める面積割合」×対象画素数の実効値（鉛直視での投影）
# T_on : 稼働時の熱源表面温度 [K]
# T_off: 停止し熱平衡に達した後の表面温度 [K]（≒外気温＋日射残熱。夜間なので外気温近傍）
# npix : 判定に使える画素数（3.5m画素）
# eps  : 熱源表面の放射率
# tau_key: 熱時定数の根拠（上の tau_calc のキー）
NODES = {
    "変電所（変圧器タンク天面）": dict(
        f=1.0, T_on=328.0, T_off=280.0, npix=8, eps=0.90, tau_key="変電所 100MVA変圧器",
        why="油入変圧器の頂部油温は定格負荷で55-70Cに達する（JEC-2200 の温度上昇限度: 頂部油温上昇55K）。"
             "タンク天面は塗装鋼でε高い。5x8m級のタンクは3.5m画素で約8画素"),
    "清掃工場（ボイラ棟屋根・煙突）": dict(
        f=0.35, T_on=353.0, T_off=280.0, npix=12, eps=0.92, tau_key="清掃工場 ボイラ棟",
        why="ごみ焼却炉の炉壁・ボイラ棟は稼働時に外皮が50-90Cとなる。煙突排ガスは150-250C。"
            "屋根面の一部が高温なので f<1"),
    "地域熱供給プラント（冷却塔・ボイラ煙道）": dict(
        f=0.5, T_on=318.0, T_off=279.0, npix=10, eps=0.90, tau_key="地域熱供給プラント 温水系",
        why="冷却塔の排気・温水配管ヘッダが稼働時に35-50C。停止で外気温に落ちる"),
    "下水処理場（曝気槽水面）": dict(
        f=1.0, T_on=291.0, T_off=288.0, npix=120, eps=0.98, tau_key="下水処理場 曝気槽1池",
        why="下水は冬季でも15-20Cで外気より高いが、これは『稼働の証拠ではなく下水そのものの温度』。"
            "曝気の有無による水面温度差は数K以下。しかも水塊の熱容量で時定数が長い"),
    "浄水場（沈殿池・ろ過池水面）": dict(
        f=1.0, T_on=280.5, T_off=280.0, npix=100, eps=0.98, tau_key="浄水場 沈殿池",
        why="原水温はほぼ気温・河川水温に従う。稼働/停止で水面温度はほとんど変わらない"),
    "配水池（覆蓋上面）": dict(
        f=1.0, T_on=279.0, T_off=279.0, npix=60, eps=0.92, tau_key="配水池 5000m3",
        why="覆蓋があり水面が見えない。中の水位・流量は熱として外に出ない"),
    "ポンプ場（電動機建屋屋根）": dict(
        f=0.3, T_on=281.0, T_off=279.0, npix=6, eps=0.92, tau_key="ポンプ場 電動機建屋",
        why="ポンプ電動機の損失熱は建屋内で拡散し、屋根面の温度上昇は数K以下"),
}
for _p in NODES.values():
    _p["tau_h"] = round(tau_calc[_p["tau_key"]]["tau_h"], 1)
results["cooling_tau"] = tau_calc


def mixed_tb(f, T_hot, T_bg, eps):
    """画素内に高温部が割合fで混在するときの見かけ輝度温度"""
    L = f*sensor_radiance(T_hot, eps, TAU, SKY_CLEAR) + (1-f)*sensor_radiance(T_bg, eps, TAU, SKY_CLEAR)
    return tb_from_radiance(L)


# ---------- 判定: 稼働 vs 停止のコントラストと雑音 ----------
# 発災後の判定は「平時ベースラインとの差」で行う。共通モード（大気・天空・季節）は
# シーン内の非対象面（周辺の裸地・建物屋根）で正規化して落とす。残る雑音は次の3つ。
NOISE_BASELINE = 1.5   # K. ベースラインとの気象条件差の正規化残差（テーマ1の二重差分の実績に準拠）
NOISE_LOAD = None      # ノードごとに与える（平常運転でも負荷で振れる分）
LOAD_SWING = {         # 平常運転時の負荷変動が見かけ輝度温度に与える振れ幅 [K]
    "変電所（変圧器タンク天面）": 6.0,      # 深夜軽負荷と日中ピークで頂部油温は10-20K振れる→夜間同士なら小さい
    "清掃工場（ボイラ棟屋根・煙突）": 4.0,  # 全連続炉は安定。定期補修停止がある
    "地域熱供給プラント（冷却塔・ボイラ煙道）": 5.0,  # 季節・時刻で負荷が大きく動く
    "下水処理場（曝気槽水面）": 1.5,
    "浄水場（沈殿池・ろ過池水面）": 1.0,
    "配水池（覆蓋上面）": 1.0,
    "ポンプ場（電動機建屋屋根）": 1.0,
}

detect = {}
for name, p in NODES.items():
    tb_on = mixed_tb(p["f"], p["T_on"], TA_WINTER, p["eps"])
    tb_off = mixed_tb(p["f"], p["T_off"], TA_WINTER, p["eps"])
    contrast = tb_on - tb_off
    nedt = nedt_at(tb_on)
    noise = float(np.sqrt(NOISE_BASELINE**2 + LOAD_SWING[name]**2 + (nedt/np.sqrt(p["npix"]))**2))
    snr = contrast/noise
    if snr >= 5:
        verdict = "単発で判別可能"
    elif snr >= 3:
        verdict = "判別可能（条件付き）"
    elif snr >= 1:
        verdict = "限界域"
    else:
        verdict = "判別不可"
    detect[name] = dict(tb_on=float(tb_on), tb_off=float(tb_off), contrast=float(contrast),
                        nedt_at_target=nedt, noise=noise, snr=float(snr), verdict=verdict,
                        tau_h=p["tau_h"], npix=p["npix"], why=p["why"])
results["detection"] = detect

# ---------- 発災後72時間の運用に乗るか ----------
# 「停止から検知可能になるまで」= 停止判定に必要なコントラスト低下（ここでは初期差の63%＝1τ）に要する時間
ops = {}
for name, d in detect.items():
    t = d["tau_h"]
    if d["snr"] < 1:
        ops[name] = "×（コントラスト不足。時定数以前の問題）"
    elif t <= 6:
        ops[name] = f"○（{t}h で停止が熱に現れる。72h運用・日2回撮像に乗る）"
    elif t <= 24:
        ops[name] = f"△（{t}h。初日の判定には間に合わない）"
    else:
        ops[name] = f"×（{t}h。停止しても数日温かいままで、72h運用に乗らない）"
results["ops_72h"] = ops

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_node_signature.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------- コンソール出力 ----------
print(f"帯域 {LAM[0]:.2f}-{LAM[-1]:.2f}um / 外気{TA_WINTER-273.15:.0f}C / tau={TAU} / NEdT(300K)={NEDT_AT_300K}K\n")
print(f"{'ノード':<34}{'ΔTb':>8}{'雑音':>8}{'SNR':>7}  {'判定':<18}{'時定数'}")
print("-"*96)
for name, d in detect.items():
    print(f"{name:<34}{d['contrast']:>7.1f}K{d['noise']:>7.1f}K{d['snr']:>7.1f}  {d['verdict']:<18}{d['tau_h']}h")
print("\n[熱時定数の独立計算]")
for k, v in tau_calc.items():
    print(f"  {k}: tau = {v['tau_h']:.1f} h  ({v['assume']})")
print("\n[発災後72時間の運用に乗るか]")
for k, v in ops.items():
    print(f"  {k}: {v}")
