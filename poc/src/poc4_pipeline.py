"""PoC-4: 保温劣化監視パイプライン（エンドツーエンド・リハーサル）
実データ差し替え可能な処理系:
  ingest → 位置合わせ(位相相関サブピクセル) → 資産マスク集約(侵食+トリム平均)
  → 共通モード正規化(不変参照面) → 兄弟差分 → ステップ検知(z検定) → 優先順位レポート

入力モード:
  A) Landsat C2 L2 ST_B10 GeoTIFF群（ユーザーアップロード時に自動検出, tifffileで読込,
     DN→K変換: DN*0.00341802+149.0）
  B) 合成シーン群（poc2のシーン生成系で14エポックを生成: 本リハーサルのデフォルト）
注入イベント(モードB): ユニット0にep8でステップ(+2K面的劣化)、タンク4にep6以降パッチ成長、
  タンク10にep10で外装張替え(ε 0.25→0.10: 見かけ温度低下→「外装履歴確認」フラグの実演)
"""
import numpy as np, json, os, glob, csv

rng_seed = 123
OUT = "/home/claude/poc/out"; os.makedirs(OUT, exist_ok=True)

# ---------- 共有物理・シーン系（poc2の定義を再利用） ----------
_src = open("/home/claude/poc/src/poc2_scene_sim.py").read().split("results = {}")[0]
exec(_src)  # Scene, observe, planck_lut, tank_score, unit_mean, sat_coords, auc など
rng = np.random.default_rng(rng_seed)

# ---------- パイプライン部品（入力形式に依存しない） ----------
def coregister(img, ref):
    """位相相関によるサブピクセル位置合わせ（整数シフト+線形補間）"""
    F = np.fft.fft2(ref - ref.mean()) * np.conj(np.fft.fft2(img - img.mean()))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-9)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    if dy > img.shape[0]//2: dy -= img.shape[0]
    if dx > img.shape[1]//2: dx -= img.shape[1]
    from scipy.ndimage import shift as ndshift2
    return ndshift2(img, (dy, dx), order=1, mode="nearest"), (float(dy), float(dx))

def common_mode_normalize(img, ref_mask):
    """不変参照面（舗装・地面）の中央値でシーン共通モード（天空/大気/校正）を除去"""
    return img - np.median(img[ref_mask])

def robust_agg(img, mask):
    v = np.sort(img[mask].ravel())
    n = v.size
    return float(v[int(n*.1):max(int(n*.9), int(n*.1)+1)].mean()) if n > 4 else float(np.median(v))

def step_scan(series, min_pre=4):
    """全時点でステップz値を走査し最大を返す（変化点検知の簡易版）"""
    s = np.asarray(series); best = (0.0, None)
    for k in range(min_pre, len(s)-2):
        pre, post = s[:k], s[k:]
        z = (post.mean() - pre.mean())/(pre.std(ddof=1)/np.sqrt(len(pre)) + post.std(ddof=1)/np.sqrt(len(post)) + 1e-6)
        if abs(z) > abs(best[0]): best = (float(z), k)
    return best

def trend_slope(series):
    x = np.arange(len(series))
    return float(np.polyfit(x, series, 1)[0])

# ---------- 入力モード判定 ----------
tifs = sorted(glob.glob("/root/.claude/uploads/**/*ST_B10*.TIF", recursive=True) +
              glob.glob("/root/.claude/uploads/**/*ST_B10*.tif", recursive=True) +
              glob.glob("/home/claude/poc/data/*ST_B10*[Tt][Ii][Ff]"))
MODE = "A:Landsat実データ" if len(tifs) >= 3 else "B:合成シーン(リハーサル)"

if MODE.startswith("A"):
    import tifffile
    epochs, labels = [], []
    for p in tifs:
        a = tifffile.imread(p).astype(np.float32)
        a[a == 0] = np.nan
        epochs.append(a*0.00341802 + 149.0)  # DN→地表面温度K
        labels.append(os.path.basename(p)[:40])
    print(f"[ingest] Landsat {len(epochs)}エポック読込。資産マスクは要定義（GUI/座標指定は次段階）")
    # 実データ時の資産マスク定義はユーザーとの対話で座標指定（このリハーサルではここまで）
    results = {"mode": MODE, "n_epochs": len(epochs), "note": "資産マスク定義待ち"}
else:
    # ---------- モードB: 合成14エポック生成 ----------
    N_EP, STEP_AT, PATCH_FROM, REPL_AT = 14, 8, 6, 10
    sc = Scene()
    epochs, truth_log = [], []
    for e in range(N_EP):
        if e == STEP_AT:
            sc.add_unit_diffuse(0, 0, 2.0)                        # ユニット0: 面的劣化ステップ
        if e >= PATCH_FROM:
            sc.add_tank_patch(sc.tanks[4], 1.2, 60)               # タンク4: パッチ漸増(累積)
        if e == REPL_AT:
            tk = sc.tanks[10]
            m = (sc._yy-tk["cy"])**2 + (sc._xx-tk["cx"])**2 < tk["R"]**2
            sc.eps[m] = 0.10                                      # タンク10: 外装張替え(新品アルミ)
        epochs.append(observe(sc))
        truth_log.append(dict(epoch=e, events=[]))
    labels = [f"ep{e:02d}" for e in range(N_EP)]

    # ---------- 資産マスク（衛星グリッド上） ----------
    H, W = epochs[0].shape
    yy, xx = np.mgrid[0:H, 0:W]
    masks, kinds = {}, {}
    for i, tk in enumerate(sc.tanks):
        cy, cx = sat_coords(tk["cy"], tk["cx"]); R = tk["R"]*GSD_TRUE/GSD_SAT
        masks[f"TANK{i:02d}"] = (yy-cy)**2 + (xx-cx)**2 < (R-1.0)**2
        kinds[f"TANK{i:02d}"] = "tank"
    for i, pair in enumerate(sc.units):
        for j, u in enumerate(pair):
            y0, x0 = sat_coords(u["y0"], u["x0"]); y1, x1 = sat_coords(u["y0"]+u["h"], u["x0"]+u["w"])
            m = np.zeros((H, W), bool); m[y0+1:y1-1, x0+1:x1-1] = True
            masks[f"UNIT{i:02d}{'AB'[j]}"] = m
            kinds[f"UNIT{i:02d}{'AB'[j]}"] = "unit"
    asset_union = np.zeros((H, W), bool)
    for m in masks.values(): asset_union |= m
    ref_mask = ~asset_union  # 地面・舗装=不変参照面

    # ---------- 前処理: 位置合わせ+共通モード正規化 ----------
    shifts = []
    proc = []
    for img in epochs:
        al, sh = coregister(img, epochs[0])
        proc.append(common_mode_normalize(al, ref_mask))
        shifts.append(sh)

    # ---------- 資産別時系列 ----------
    ts = {k: [robust_agg(im, m) for im in proc] for k, m in masks.items()}
    tank_contrast = {}
    for i, tk in enumerate(sc.tanks):
        key = f"TANK{i:02d}"
        cs = []
        for im in proc:
            v = im[masks[key]]
            med = np.median(v); mad = np.median(np.abs(v-med))*1.4826 + 1e-6
            cs.append(float((np.percentile(v, 95)-med)/mad))
        tank_contrast[key] = cs

    # ---------- 検知・ランキング ----------
    findings = []
    for i in range(len(sc.units)):
        a, b = f"UNIT{i:02d}A", f"UNIT{i:02d}B"
        d = np.array(ts[a]) - np.array(ts[b])
        z, k = step_scan(d)
        if abs(z) > 4:
            findings.append(dict(asset=f"UNIT{i:02d}", type="兄弟差分ステップ", z=round(z, 1),
                                 at=labels[k], direction="上昇(劣化疑い)" if z > 0 else "下降",
                                 action="当該ユニットへ点検チーム派遣（面的劣化/外装イベント疑い）"))
    for key, cs in tank_contrast.items():
        z, k = step_scan(cs)
        sl = trend_slope(cs)
        if abs(z) > 4 or sl > 0.15:
            findings.append(dict(asset=key, type="屋根面内コントラスト異常", z=round(z, 1),
                                 slope_per_ep=round(sl, 3), at=labels[k] if k else "-",
                                 action="屋根の局所劣化パッチ疑い→ドローン精密確認"))
    for key in [k for k, kd in kinds.items() if kd == "tank"]:
        z, k = step_scan(ts[key])
        if z is not None and z < -4:
            findings.append(dict(asset=key, type="見かけ温度の急落", z=round(z, 1), at=labels[k],
                                 action="外装更新（張替え）履歴の確認。εアーティファクトの可能性→CMMS突合"))
    findings.sort(key=lambda f: -abs(f.get("z", 0)))

    # ---------- レポート出力 ----------
    with open(f"{OUT}/poc4_priority_report.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["asset", "type", "z", "slope_per_ep", "at", "direction", "action"])
        w.writeheader()
        for fd in findings: w.writerow({k: fd.get(k, "") for k in w.fieldnames})
    results = {
        "mode": MODE, "n_epochs": N_EP, "coreg_shifts_px": shifts[:3],
        "injected_truth": {"UNIT00": f"ep{STEP_AT:02d}で+2K面的劣化", "TANK04": f"ep{PATCH_FROM:02d}以降パッチ漸増",
                           "TANK10": f"ep{REPL_AT:02d}で外装張替え(εアーティファクト)"},
        "findings": findings[:8],
        "detected": {
            "UNIT00": any(f["asset"] == "UNIT00" for f in findings),
            "TANK04": any(f["asset"] == "TANK04" for f in findings),
            "TANK10_flag": any(f["asset"] == "TANK10" and "外装" in f["action"] for f in findings)},
    }
    np.save(f"{OUT}/poc4_epochs_proc.npy", np.stack(proc).astype(np.float32))
    with open(f"{OUT}/poc4_series.json", "w") as f:
        json.dump({"ts": ts, "tank_contrast": tank_contrast, "labels": labels}, f)

with open(f"{OUT}/poc4_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
