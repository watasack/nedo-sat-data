"""PoC-2: 合成プラントシーンでの検知性能シミュレーション（モンテカルロ）
0.5m地表グリッドで真値シーンを合成 → MWIR放射伝達 → PSF(3.5m) → 3.5mサンプリング
→ NEdT・幾何ずれ・天空/大気の撮像間変動を注入 → 検知器を評価（AUC）。
検知器: (1)シーン内コントラスト(タンク屋根パッチ) (2)兄弟資産差分(ユニット面的劣化)
        (3)ステップ変化検知(時系列CUSUM)
"""
import numpy as np
from scipy.ndimage import gaussian_filter, shift as ndshift
import json, os

# リポジトリ相対パス（execで読み込まれる場合は呼び出し側の__file__基準にフォールバック）
_POC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(globals().get("__file__", "."))))
if os.path.basename(_POC_DIR) != "poc":
    _POC_DIR = os.path.join(os.getcwd(), "poc")
POC_OUT = os.path.join(_POC_DIR, "out")

rng = np.random.default_rng(42)
C1, C2 = 1.191042e8, 1.4387752e4
LAM = np.linspace(3.4, 4.2, 41)

def planck_band_arr(T):
    B = C1 / (LAM[None, :]**5 * (np.exp(C2/(LAM[None, :]*T.reshape(-1, 1))) - 1.0))
    return np.trapezoid(B, LAM, axis=1).reshape(T.shape)

# 輝度→温度の逆変換はLUTで高速化
_T_lut = np.linspace(200, 400, 2001)
_L_lut = planck_band_arr(_T_lut)
def tb_arr(L):
    return np.interp(L, _L_lut, _T_lut)

GSD_TRUE, GSD_SAT = 0.5, 3.5
TA = 288.0

class Scene:
    """1000x1000m のプラントシーン"""
    def __init__(self, n_tanks=24, n_unit_pairs=8, tank_R_m=(12, 30)):
        self.N = 2000
        self.T = np.full((self.N, self.N), TA, np.float32)   # 表面温度
        self.eps = np.full((self.N, self.N), 0.95, np.float32)
        self.tanks, self.units = [], []
        self._yy, self._xx = np.mgrid[0:self.N, 0:self.N]
        yy, xx = self._yy, self._xx
        # タンク（グリッド配置・重なりなし）
        cells = [(r, c) for r in range(6) for c in range(4)]
        for i in range(n_tanks):
            r_, c_ = cells[i]
            cy, cx = 150 + r_*300, 150 + c_*300
            R = rng.uniform(*tank_R_m) / GSD_TRUE
            m = (yy-cy)**2 + (xx-cx)**2 < R**2
            self.T[m] = TA + rng.uniform(4, 10)
            self.eps[m] = np.clip(rng.normal(0.25, 0.02), 0.15, 0.4)
            self.tanks.append(dict(cy=cy, cx=cx, R=R, mask_id=i))
        # プロセスユニット対（兄弟資産: 同一負荷の並列系列）
        for i in range(n_unit_pairs):
            base_load = rng.uniform(8, 16)
            pair = []
            for j in range(2):
                y0 = 60 + (i % 4)*480; x0 = 1300 + (i//4)*340 + j*160
                h, w = int(140/GSD_TRUE), int(60/GSD_TRUE)
                m = (yy >= y0) & (yy < y0+h) & (xx >= x0) & (xx < x0+w)
                rack = m & ((yy // 8) % 2 == 0)   # 配管ラック縞 fill~0.5
                self.T[rack] = TA + base_load + rng.normal(0, 0.3)
                self.eps[m & ~rack] = 0.9  # ラック間は舗装
                self.eps[rack] = np.clip(rng.normal(0.25, 0.02), 0.15, 0.4)
                pair.append(dict(y0=y0, x0=x0, h=h, w=w))
            self.units.append(pair)

    def add_tank_patch(self, tank, dT, area_m2, erode_sat_px=None):
        """erode_sat_px指定時: 検知側の境界侵食後マスク内に収まるよう配置を制約"""
        R_p = np.sqrt(area_m2/np.pi)/GSD_TRUE
        th = rng.uniform(0, 2*np.pi)
        if erode_sat_px is None:
            rr = tank["R"]*0.5
        else:
            rr_max = max(tank["R"] - erode_sat_px*(GSD_SAT/GSD_TRUE) - R_p, 0.0)
            rr = rng.uniform(0, rr_max)
        cy, cx = tank["cy"]+rr*np.sin(th), tank["cx"]+rr*np.cos(th)
        yy, xx = self._yy, self._xx
        m = ((yy-cy)**2 + (xx-cx)**2 < R_p**2) & ((yy-tank["cy"])**2 + (xx-tank["cx"])**2 < tank["R"]**2)
        self.T[m] += dT

    def add_unit_diffuse(self, pair_idx, member, dT):
        u = self.units[pair_idx][member]
        sl = np.s_[u["y0"]:u["y0"]+u["h"], u["x0"]:u["x0"]+u["w"]]
        hot = self.T[sl] > TA + 2
        self.T[sl][hot] += dT

def planck_lut(T):
    """LUT補間による高速B(T)（配列対応）"""
    return np.interp(T, _T_lut, _L_lut)

def observe(scene, T_sky=None, tau=None, nedt=1.0, jitter=True):
    """1エポックの衛星観測（輝度温度画像を返す）"""
    T_sky = rng.normal(240, 6) if T_sky is None else T_sky
    tau = np.clip(rng.normal(0.75, 0.03), 0.6, 0.9) if tau is None else tau
    L_sky = float(planck_lut(np.array([T_sky]))[0])
    L_atm = float(planck_lut(np.array([285.0]))[0])
    L = tau*(scene.eps*planck_lut(scene.T) + (1-scene.eps)*L_sky) + (1-tau)*L_atm
    sigma_px = (GSD_SAT/2.355)/GSD_TRUE
    L = gaussian_filter(L, sigma_px)
    if jitter:
        L = ndshift(L, rng.uniform(-3.5, 3.5, 2), order=1, mode="nearest")  # ±0.5衛星画素
    k = int(GSD_SAT/GSD_TRUE)  # 7
    n = (scene.N//k)*k
    Ls = L[:n, :n].reshape(n//k, k, n//k, k).mean(axis=(1, 3))
    # NEdT: 300K相当の輝度揺らぎとして付加
    dL = (planck_band_arr(np.array([301.0])) - planck_band_arr(np.array([299.0])))[0]/2
    Ls = Ls + rng.normal(0, nedt*dL, Ls.shape)
    return tb_arr(Ls)

def sat_coords(y, x):
    return int(y*GSD_TRUE/GSD_SAT), int(x*GSD_TRUE/GSD_SAT)

def tank_score(img, tank):
    cy, cx = sat_coords(tank["cy"], tank["cx"]); R = tank["R"]*GSD_TRUE/GSD_SAT
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    m = (yy-cy)**2 + (xx-cx)**2 < (R-3.0)**2   # 境界3px侵食（低ε屋根×高ε地面の混合縁勾配を除外）
    v = img[m]
    if v.size < 12: return np.nan              # 小型タンクは「監視不能資産」として除外（可視面仕様）
    med = np.median(v); mad = np.median(np.abs(v-med))*1.4826 + 1e-6
    return (np.percentile(v, 95) - med)/mad    # シーン内コントラスト指標

def unit_mean(img, u):
    y0, x0 = sat_coords(u["y0"], u["x0"]); y1, x1 = sat_coords(u["y0"]+u["h"], u["x0"]+u["w"])
    v = img[y0+1:y1-1, x0+1:x1-1]
    return np.mean(np.sort(v.ravel())[int(v.size*.1):int(v.size*.9)])  # トリム平均

def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return (pos[:, None] > neg[None, :]).mean() + 0.5*(pos[:, None] == neg[None, :]).mean()

results = {}
N_TRIALS = 6

# ---------- (1) タンク屋根パッチ: シーン内コントラストAUC ----------
grid = [(dT, A) for dT in (2.0, 3.0, 5.0) for A in (50, 100, 200)]
tank_auc = {}
for dT, A in grid:
    pos, neg = [], []
    for t in range(N_TRIALS):
        sc = Scene()
        deg = list(range(0, 24, 2))
        for i in deg: sc.add_tank_patch(sc.tanks[i], dT, A)
        img = observe(sc)
        for i, tk in enumerate(sc.tanks):
            (pos if i in deg else neg).append(tank_score(img, tk))
    tank_auc[f"dT={dT}K,A={A}m2"] = float(auc(pos, neg))
results["tank_patch_auc"] = tank_auc

# ---------- (2) ユニット面的劣化: 兄弟差分（静的/二重差分） ----------
unit_res = {}
for dT in (0.5, 1.0, 2.0):
    stat_pos, stat_neg, dd_pos, dd_neg = [], [], [], []
    for t in range(N_TRIALS):
        sc = Scene()
        deg_pairs = list(range(0, 8, 2))
        # 前期6エポック: 劣化なし / 後期6エポック: 劣化注入
        pre = [observe(sc) for _ in range(6)]
        for i in deg_pairs: sc.add_unit_diffuse(i, 0, dT)
        post = [observe(sc) for _ in range(6)]
        for i, pair in enumerate(sc.units):
            d_pre = np.mean([unit_mean(im, pair[0]) - unit_mean(im, pair[1]) for im in pre])
            d_post = np.mean([unit_mean(im, pair[0]) - unit_mean(im, pair[1]) for im in post])
            (stat_pos if i in deg_pairs else stat_neg).append(d_post)          # 静的: 単発の兄弟差
            (dd_pos if i in deg_pairs else dd_neg).append(d_post - d_pre)      # 二重差分
    unit_res[f"dT={dT}K"] = dict(static_auc=float(auc(stat_pos, stat_neg)),
                                 double_diff_auc=float(auc(dd_pos, dd_neg)))
results["unit_diffuse_auc"] = unit_res

# ---------- (3) ステップ変化検知（外装脱落級 +2K を月次時系列で） ----------
det, fa = 0, 0
n_ep, step_at = 12, 6
for t in range(N_TRIALS):
    sc = Scene()
    series = {i: [] for i in range(8)}
    ref = []
    for e in range(n_ep):
        if e == step_at:
            for i in (0, 2, 4): sc.add_unit_diffuse(i, 0, 2.0)
        img = observe(sc)
        ref_v = np.median(img)  # シーン共通モード（地面参照）
        for i, pair in enumerate(sc.units):
            series[i].append(unit_mean(img, pair[0]) - unit_mean(img, pair[1]))
    for i in range(8):
        s = np.array(series[i]); base = s[:step_at]
        z = (s[step_at:].mean() - base.mean())/(base.std(ddof=1) + 1e-6)
        flag = abs(z) > 3
        if i in (0, 2, 4): det += flag
        else: fa += flag
results["step_detection"] = dict(detect_rate=det/(3*N_TRIALS), false_alarm_rate=fa/(5*N_TRIALS),
                                 step_size_K=2.0, epochs=n_ep, note="兄弟差分系列のステップz検定(z>3)")

os.makedirs(POC_OUT, exist_ok=True)
# 既存JSONへマージ書き込み（単体再実行でtank_patch_auc_v2等の追記結果を消さない）
_json_path = os.path.join(POC_OUT, "poc2_results.json")
if os.path.exists(_json_path):
    _prev = json.load(open(_json_path))
    _prev.update(results)
    results = _prev
with open(_json_path, "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print(json.dumps(results, ensure_ascii=False, indent=1))

# 図用に代表シーン1枚を保存
sc = Scene()
for i in (0, 4, 8): sc.add_tank_patch(sc.tanks[i], 5.0, 200)
sc.add_unit_diffuse(0, 0, 2.0)
np.save(os.path.join(POC_OUT, "demo_scene_tb.npy"), observe(sc).astype(np.float32))
np.save(os.path.join(POC_OUT, "demo_scene_truth.npy"), sc.T[::4, ::4].astype(np.float32))
print("demo scene saved")
