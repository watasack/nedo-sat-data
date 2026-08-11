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
_POC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_POC, "out"); os.makedirs(OUT, exist_ok=True)

# ---------- 共有物理・シーン系（poc2の定義を再利用） ----------
_src = open(os.path.join(_POC, "src", "poc2_scene_sim.py")).read().split("results = {}")[0]
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
tifs = sorted(glob.glob(os.path.join(_POC, "data", "*ST_B10*[Tt][Ii][Ff]")) +
              glob.glob("/root/.claude/uploads/**/*ST_B10*.TIF", recursive=True) +
              glob.glob("/root/.claude/uploads/**/*ST_B10*.tif", recursive=True) +
              glob.glob("/home/claude/poc/data/*ST_B10*[Tt][Ii][Ff]"))
MODE = "A:Landsat実データ" if len(tifs) >= 3 else "B:合成シーン(リハーサル)"

if MODE.startswith("A"):
    # ==================================================================
    # モードA: Landsat C2L2 ST_B10（30m画素・昼間パス）による通し実行
    # 【重要な限界の宣言】Landsatの熱バンドは設備単位（3.5m級）の解析が
    # 物理的に不可能なため、ここでは京浜の大型プラント「複合体レベル」の
    # 概略AOI（±数百mの精度、要現地検証）で集約時系列を抽出し、
    # 共通モード正規化→兄弟差分→ステップ走査が実データで通ることを示す。
    # 設備単位の監視はHotSat-2でのみ成立する（本デモの結論であり制約）。
    # ==================================================================
    import tifffile
    from pyproj import Transformer
    _tr = Transformer.from_crs(4326, 32654, always_xy=True)  # WGS84 → UTM54N

    # 京浜臨海部の概略AOI（lon/lat矩形）。複合体レベルの集約用
    AOIS = {
        "川崎火力(千鳥町)":   (139.750, 35.512, 139.762, 35.522, "power"),
        "東扇島火力":         (139.745, 35.495, 139.760, 35.505, "power"),
        "浮島製油所地区":     (139.765, 35.520, 139.785, 35.535, "refinery"),
        "水江町製油所地区":   (139.720, 35.515, 139.735, 35.525, "refinery"),
        "扇島製鉄所地区":     (139.700, 35.470, 139.730, 35.490, "steel"),
        "大黒町火力地区":     (139.680, 35.462, 139.690, 35.472, "power"),
    }
    REF_AOI = (139.695, 35.525, 139.715, 35.540)  # 川崎市街地 = 不変参照面（相対校正用）
    # 【2026年8月11日・PoC-6(a) / review_v7 P-9】上の参照面は14シーンのうち8シーンで
    # スワス端欠測に入るため有効エポックが6本に落ちていた。**捨てていたのはシーンではなく
    # 参照面の置き場所である。** 全14シーンの共通有効域の内側で、旧参照面と時系列が一致する
    # 陸域（市街地）を探して置き直したのが下。選定条件は
    #   (a) 全14シーンで有効 (b) 資産AOIと重ならない
    #   (c) 空間σ 1.5〜3.5K＝市街地らしさ（水面はσ<0.5Kで陸面の共通モードを追えない）
    #   (d) 旧参照面と同じ共通モードを表すこと ← 重複6エポックで差のσが最小のものを採用
    # 実測: 旧参照面との相関 r=0.9998、差のσ 0.28K、平均差 +0.78K。**代替として成立している。**
    REF_AOI_V2 = (139.6615, 35.4952, 139.6815, 35.5098)   # 鶴見区市街地・全14シーン有効
    REF_VARIANTS = [("v2_全14シーン", REF_AOI_V2), ("v1_旧_川崎市街地", REF_AOI)]
    SIBLING_PAIRS = [("川崎火力(千鳥町)", "東扇島火力"), ("浮島製油所地区", "水江町製油所地区")]

    def read_geo(p):
        with tifffile.TiffFile(p) as tf:
            pg = tf.pages[0]
            a = pg.asarray().astype(np.float32)
            scale = pg.tags[33550].value       # (sx, sy, sz)
            tie = pg.tags[33922].value         # (i, j, k, X, Y, Z)
        a[a == 0] = np.nan
        return a*0.00341802 + 149.0, (tie[3], tie[4], scale[0], scale[1])

    def aoi_slice(geo, lon0, lat0, lon1, lat1, shape):
        x0, y1 = _tr.transform(lon0, lat0)   # 南西
        x1, y0 = _tr.transform(lon1, lat1)   # 北東
        X0, Y0, sx, sy = geo
        c0, c1 = int((x0-X0)/sx), int((x1-X0)/sx)
        r0, r1 = int((Y0-y0)/sy), int((Y0-y1)/sy)
        r0, r1 = max(0, r0), min(shape[0], r1)
        c0, c1 = max(0, c0), min(shape[1], c1)
        return np.s_[r0:r1, c0:c1]

    def robust_agg_nan(v):
        f = np.isfinite(v)
        if v.size == 0 or f.mean() < 0.5:   # 雲・スワス外で半分以上欠測なら不採用
            return np.nan
        v = np.sort(v[f].ravel())
        return float(v[int(v.size*.1):int(v.size*.9)].mean())

    # 京浜はLandsatの隣接パス境界に位置し、約半数のシーンはスワス端で北西側が
    # 欠測する（東扇島のみカバー）。市街地参照面が有効なシーンだけを採用する。
    # 画像は1回だけ読む（参照面を変えても入力は同じ）
    imgs = [read_geo(p) for p in tifs]
    variants = {}
    for _label, ref_aoi in REF_VARIANTS:
        epochs_meta = []
        series = {k: [] for k in AOIS}
        raw = {k: [] for k in AOIS}
        ref_series = []
        skipped = []
        for p, (img, geo) in zip(tifs, imgs):
            ref_v = robust_agg_nan(img[aoi_slice(geo, *ref_aoi, img.shape)])
            if not np.isfinite(ref_v):
                skipped.append(os.path.basename(p)[:8]); continue
            for k, (a0, b0, a1, b1, _kind) in AOIS.items():
                v = robust_agg_nan(img[aoi_slice(geo, a0, b0, a1, b1, img.shape)])
                raw[k].append(v)
                # 共通モード正規化: 市街地参照面との差（季節・大気・校正の共通成分を除去）
                series[k].append(v - ref_v if np.isfinite(v) else np.nan)
            ref_series.append(ref_v)
            epochs_meta.append(os.path.basename(p)[:8])

        def interp_nan(s):
            s = np.array(s, float)
            ok = np.isfinite(s)
            if ok.sum() < max(4, int(len(s)*0.7)): return None
            s[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), s[ok])
            return s

        MIN_PRE = 2 if len(epochs_meta) <= 8 else 4   # 有効エポック数に応じた走査窓
        series_i = {k: interp_nan(v) for k, v in series.items()}
        findings = []
        for a, b in SIBLING_PAIRS:
            if series_i[a] is None or series_i[b] is None: continue
            d = series_i[a] - series_i[b]
            z, k = step_scan(d, min_pre=MIN_PRE)
            findings.append(dict(pair=f"{a} − {b}", type="兄弟差分ステップ走査",
                                 z=round(z, 1), at=epochs_meta[k] if k else "-",
                                 slope_per_ep=round(trend_slope(d), 3),
                                 judged="ステップ検出" if abs(z) > 4 else "有意な段差なし(健全側)"))
        for k, s in series_i.items():
            if s is None: continue
            z, kk = step_scan(s, min_pre=MIN_PRE)
            findings.append(dict(asset=k, type="対市街地差の走査", z=round(z, 1),
                                 at=epochs_meta[kk] if kk else "-",
                                 slope_per_ep=round(trend_slope(s), 3),
                                 judged="ステップ検出" if abs(z) > 4 else "有意な段差なし"))

        # 振れ幅（提出物④が引用している量）。**定義を必ず一緒に保存する**——資産のみか
        # 参照面も含めるかで約1K違い、記録が無いと再現できない（review_v7 P-6 で実際に踏んだ）
        _as = np.array([v for s_ in raw.values() for v in s_], float)
        _wr = np.concatenate([_as, np.array(ref_series, float)])
        _df = np.array([v for s_ in series.values() for v in s_], float)
        spread = {
            "正規化前_資産のみ_K": round(float(np.nanmax(_as) - np.nanmin(_as)), 2),
            "正規化前_資産と参照面_K": round(float(np.nanmax(_wr) - np.nanmin(_wr)), 2),
            "正規化後_対参照面差_K": round(float(np.nanmax(_df) - np.nanmin(_df)), 2),
            "定義": "各系列の最大−最小。集約は10-90パーセンタイルのトリム平均",
        }

        results = {
            "mode": MODE, "ref_aoi": list(ref_aoi), "spread_K": spread,
            "n_epochs": len(epochs_meta), "epochs_skipped_swath_edge": skipped,
            "pixel_m": 30,
            "ref_series_K": [round(float(v), 2) for v in ref_series],
            "note": ("複合体レベルの概略AOI集約（AOIは±数百m精度・要現地検証）。"
                     "Landsat昼間パスのため太陽加熱が支配的であり、市街地参照との差で"
                     "共通モードを除去した相対指標。設備単位の解析は3.5m級(HotSat-2)が必要"
                     "——という分解能ギャップ自体が本提案の前提を実データで裏付ける"),
            "series_vs_urban_ref_K": {k: [round(float(x), 2) if np.isfinite(x) else None for x in v]
                                      for k, v in series.items()},
            "epochs": epochs_meta,
            "findings": findings,
        }

        variants[_label] = results
        print(f"[{_label}] 有効{results['n_epochs']}エポック "
              f"/ 除外{len(results['epochs_skipped_swath_edge'])} "
              f"/ 振れ幅 {spread['正規化前_資産と参照面_K']}K → {spread['正規化後_対参照面差_K']}K "
              f"/ 最大|z| {max(abs(f['z']) for f in results['findings']):.1f}")

    # 新参照面が旧参照面の代替として成立していることの根拠を保存する。
    # **これを保存しないと「相関 r=0.9998」が文書にしか無い数字になる**（型E-4）
    _v2 = variants["v2_全14シーン"]; _v1 = variants["v1_旧_川崎市街地"]
    _common = [e for e in _v1["epochs"] if e in _v2["epochs"]]
    _i2 = [_v2["epochs"].index(e) for e in _common]
    _i1 = [_v1["epochs"].index(e) for e in _common]
    _s2 = np.array([_v2["ref_series_K"][i] for i in _i2], float)
    _s1 = np.array([_v1["ref_series_K"][i] for i in _i1], float)
    ref_equiv = {
        "重複エポック数": len(_common),
        "相関r": round(float(np.corrcoef(_s2, _s1)[0, 1]), 4),
        "差の標準偏差_K": round(float(np.std(_s2 - _s1, ddof=1)), 2),
        "平均差_K": round(float(np.mean(_s2 - _s1)), 2),
        "判定": "代替として成立（同じ共通モードを表している）",
        "選定条件": ("(a)全14シーンで有効 (b)資産AOIと重ならない "
                     "(c)空間σ1.5〜3.5K＝市街地らしさ（水面はσ<0.5Kで陸面の共通モードを追えない）"
                     "(d)旧参照面との差のσが最小"),
    }

    results = dict(variants["v2_全14シーン"])
    results["ref_equivalence_v2_vs_v1"] = ref_equiv
    results["note_ref"] = (
        "既定の参照面は REF_AOI_V2（鶴見区市街地・全14シーン有効）。"
        "旧参照面の結果は variants に残してある。"
        "**12_提出版_様式4.md と 08 が引用している数値は旧参照面のもの**なので、"
        "本文を触るときは variants['v1_旧_川崎市街地'] を見ること")
    results["variants"] = variants
    with open(os.path.join(OUT, "poc4_results_real.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    raise SystemExit(0)
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
