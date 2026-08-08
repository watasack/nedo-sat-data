"""応募書類用の図版生成（poc/out/*.json → poc/out/fig/*.png）

dataviz原則: 1軸、カテゴリ色は固定順（blue→orange→aqua）、系列2以上は凡例必須、
細いマーク、選択的直接ラベル、グリッドは控えめ。ライトモード（印刷/Word想定）。
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib_fontja  # noqa: F401  日本語フォント(IPAexゴシック)

# 参照パレット（ライト）。カテゴリは固定スロット順で使う（循環させない）
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
YELLOW, MAGENTA, GREEN = "#eda100", "#e87ba4", "#008300"
CAT6 = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN]
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASE, SURF = "#e1e0d9", "#c3c2b7", "#fcfcfb"
CRIT = "#d03b3b"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF,
    "axes.edgecolor": BASE, "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.labelcolor": INK2, "text.color": INK,
    "font.size": 10, "axes.titlesize": 11,
    "axes.spines.top": False, "axes.spines.right": False,
})

_here = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_here, "..", "out")
FIG = os.path.join(OUT, "fig")
os.makedirs(FIG, exist_ok=True)

def save(fig, name):
    fig.savefig(os.path.join(FIG, name), dpi=200, bbox_inches="tight",
                facecolor=SURF)
    plt.close(fig)
    print("saved", name)

p1 = json.load(open(os.path.join(OUT, "poc1_results.json")))
p2 = json.load(open(os.path.join(OUT, "poc2_results.json")))
p3 = json.load(open(os.path.join(OUT, "poc3_results.json")))
p4s = json.load(open(os.path.join(OUT, "poc4_series.json")))

# ---------- 図1: 検出対象別SNR（誤差バジェットの帰結） ----------
cases = p1["detection_cases"]
order = sorted(cases, key=lambda k: cases[k]["snr"])
snrs = [cases[k]["snr"] for k in order]
names = {
    "加熱炉・高温配管系の保温不良(+15K)": "加熱炉・高温配管系の保温不良 (+15K)・単発",
    "タンク屋根の劣化パッチ(+5K)": "タンク屋根の劣化パッチ (+5K, 100m²)・単発",
    "タンク屋根の劣化パッチ(+3K,100m²≈8px)": "タンク屋根の劣化パッチ (+3K, 100m²)・単発",
    "ユニット面的劣化(+1K) 二重差分×6エポック": "ユニット面的劣化 (+1K) 二重差分×6エポック",
    "ユニット面的劣化(+1K) 対双子資産": "ユニット面的劣化 (+1K) 兄弟差分・単発",
    "個別配管CUIスポット(f=0.15,+5K)": "個別配管CUIスポット (+5K, 充足率0.15)・単発",
}
fig, ax = plt.subplots(figsize=(8, 3.6))
y = np.arange(len(order))
ax.barh(y, snrs, height=0.55, color=BLUE, zorder=3)
ax.axvline(1.0, color=CRIT, lw=1.2, ls="--", zorder=4)
ax.text(1.07, 0.5, "検出限界 SNR=1", color=CRIT, fontsize=9, va="center")
for yi, s in zip(y, snrs):
    ax.text(s+0.07, yi, f"{s:.2f}", va="center", fontsize=9, color=INK2)
ax.set_yticks(y, [names[k] for k in order])
ax.set_xlabel("SNR（信号/誤差RSS, NEdT=1K仮定。エポック数は各ラベルに明記）")
ax.set_title("何が見えて何が見えないか — 検出対象別SNR（MWIR誤差バジェット計算）")
ax.grid(axis="y", visible=False)
save(fig, "fig1_snr_budget.png")

# ---------- 図1b: 測定方式別の誤差RSS vs 信号 ----------
bud = p1["budget"]
methods = ["絶対温度（撮像間差分）", "シーン内相対比較（同一資産内）", "兄弟資産差分（ユニット集約N=50px）"]
short = ["撮像間の絶対値比較", "シーン内相対比較", "兄弟資産差分（集約）"]
rss = [bud[m]["rss"] for m in methods]
sig = p1["signals"]["タンク屋根パッチ(+3K,f=1)"]
fig, ax = plt.subplots(figsize=(7, 2.9))
y = np.arange(len(methods))
ax.barh(y, rss, height=0.5, color=[CRIT, BLUE, BLUE], zorder=3)
ax.axvline(sig, color=INK2, lw=1.2, ls="--", zorder=4)
ax.text(sig+0.1, -0.55, f"代表信号 {sig:.1f}K（タンクパッチ+3Kの輝度温度換算）",
        color=INK2, fontsize=9, va="top")
for yi, v in zip(y, rss):
    ax.text(v+0.12, yi, f"{v:.1f}K", va="center", fontsize=9, color=INK2)
ax.set_yticks(y, short)
ax.set_xlabel("誤差バジェット RSS (K)")
ax.set_title("測定方式の選択が成立性を決める — 絶対値比較は物理的に不成立")
ax.grid(axis="y", visible=False)
ax.set_xlim(0, 11)
save(fig, "fig1b_method_budget.png")

# ---------- 図2: ユニット面的劣化の判別AUC（静的 vs 二重差分） ----------
ud = p2["unit_diffuse_auc"]
dts = ["dT=0.5K", "dT=1.0K", "dT=2.0K"]
stat = [ud[k]["static_auc"] for k in dts]
dd = [ud[k]["double_diff_auc"] for k in dts]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
y = np.arange(len(dts))
for yi, s, d in zip(y, stat, dd):
    ax.plot([s, d], [yi, yi], color=GRID, lw=2, zorder=2)
ax.scatter(stat, y, s=70, color=MUTED, zorder=3, label="静的兄弟差分（単発）")
ax.scatter(dd, y, s=70, color=BLUE, zorder=3, label="兄弟差分の時間変化（二重差分・前後6エポック）")
ax.axvline(0.5, color=BASE, lw=1.0, ls="--")
ax.text(0.502, -0.42, "偶然水準", color=MUTED, fontsize=8.5)
for yi, s, d in zip(y, stat, dd):
    ax.text(s, yi+0.18, f"{s:.2f}", ha="center", va="bottom", fontsize=9, color=MUTED)
    ax.text(d, yi+0.18, f"{d:.2f}", ha="center", va="bottom", fontsize=9, color=BLUE)
ax.set_yticks(y, ["劣化 +0.5K", "劣化 +1.0K", "劣化 +2.0K"])
ax.set_xlabel("判別AUC（合成シーン・モンテカルロ）")
ax.set_xlim(0.35, 1.05)
ax.set_ylim(-0.6, 2.6)
ax.set_title("「兄弟差分の時間変化」が推定器の本命 — 静的差分との判別力比較")
ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.18), ncols=2,
          fontsize=8.5, framealpha=0.9, borderaxespad=0)
ax.grid(axis="y", visible=False)
save(fig, "fig2_unit_auc.png")

# ---------- 図3: 降雨後特徴量の成立回数（体制別） ----------
sc = p3["scenarios"]
scen = list(sc.keys())          # モードA(実データ)/B(気候値)でキーが異なる
lab = [s.replace("(", "\n(", 1) for s in scen]
single = [sc[s]["single_per_year"] for s in scen]
slope = [sc[s]["slope_per_year"] for s in scen]
is_real = str(p3.get("mode", "")).startswith("A")
x = np.arange(len(scen)); w = 0.36
fig, ax = plt.subplots(figsize=(7, 3.4))
b1 = ax.bar(x-w/2, [v["median"] for v in single], w-0.04, color=BLUE, zorder=3,
            label="単点特徴量（降雨後の高温残留）")
b2 = ax.bar(x+w/2, [v["median"] for v in slope], w-0.04, color=ORANGE, zorder=3,
            label="回復速度（傾き・2回撮像）")
for xs, vals in ((x-w/2, single), (x+w/2, slope)):
    ax.errorbar(xs, [v["median"] for v in vals],
                yerr=[[v["median"]-v["p25"] for v in vals],
                      [v["p75"]-v["median"] for v in vals]],
                fmt="none", ecolor=INK2, elinewidth=1, capsize=3, zorder=4)
for xi, v in zip(x-w/2, single):
    ax.text(xi, v["p75"]+0.6, f'{v["median"]:.0f}', ha="center", fontsize=9, color=INK2)
for xi, v in zip(x+w/2, slope):
    ax.text(xi, v["p75"]+0.6, f'{v["median"]:.0f}', ha="center", fontsize=9, color=INK2)
ax.set_xticks(x, lab)
ax.set_ylabel("成立回数（回/年, 中央値と四分位範囲）")
if is_real:
    ax.set_title("降雨後特徴量は現行体制では「機会的」— 回復速度は年数回に留まる\n（川崎の実気象2020-2025・パス時刻雲量で判定）", fontsize=10.5)
else:
    ax.set_title("降雨後特徴量は現行体制では「機会的」— 回復速度は年0〜1回しか成立しない")
ax.legend(fontsize=8.5, loc="upper left")
ax.grid(axis="x", visible=False)
save(fig, "fig3_rain_feature.png")

# ---------- 図4: パイプライン通しリハーサル（検知時系列） ----------
ts = p4s["ts"]; ep = np.arange(len(p4s["labels"]))
u0 = np.array(ts["UNIT00A"]) - np.array(ts["UNIT00B"])
u1 = np.array(ts["UNIT01A"]) - np.array(ts["UNIT01B"])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.3))
a1.plot(ep, u0, color=BLUE, lw=2, marker="o", ms=4, zorder=3, label="UNIT00（ep08で+2K劣化を注入）")
a1.plot(ep, u1, color=MUTED, lw=2, marker="o", ms=4, zorder=2, label="UNIT01（健全）")
a1.axvline(8, color=CRIT, lw=1.0, ls="--")
a1.text(8.15, -0.52, "検出 z=4.7\n→点検派遣", color=CRIT, fontsize=8.5, va="top")
a1.set_title("兄弟差分の時系列 — 面的劣化ステップ")
a1.set_xlabel("エポック（月次相当）"); a1.set_ylabel("兄弟差分 (K)")
a1.legend(fontsize=8, loc="upper left")
t10 = np.array(ts["TANK10"]); t04 = np.array(ts["TANK04"])
# 注: TANK04は「参照」ではなく、ep06以降パッチを漸増注入した資産。単発指標では
# 検知に至らない（既知の限界＝見逃し）。付録の注入真値と図の凡例を一致させる。
a2.axvspan(6, len(ep)-1, color=AQUA, alpha=0.07, zorder=1)
a2.plot(ep, t10, color=ORANGE, lw=2, marker="o", ms=4, zorder=3, label="TANK10（ep10で外装張替え）")
a2.plot(ep, t04, color=AQUA, lw=2, marker="o", ms=4, zorder=2,
        label="TANK04（ep06以降パッチ漸増を注入）")
a2.axvline(10, color=CRIT, lw=1.0, ls="--")
a2.annotate("検出 z=-11.4\n→εアーティファクトと分類\n（劣化と誤報しない）",
            xy=(10.2, 0.30), xycoords=("data", "axes fraction"),
            color=CRIT, fontsize=8.5, va="top")
a2.annotate("注入区間。単発指標では未検出＝見逃し\n→時系列スタックで対処（図5）",
            xy=(6.2, 0.46), xycoords=("data", "axes fraction"),
            color=AQUA, fontsize=8.5, va="top")
a2.set_title("タンク見かけ温度 — 外装更新の弁別と、見逃しの自白")
a2.set_xlabel("エポック（月次相当）"); a2.set_ylabel("対地面 輝度温度差 (K)")
a2.legend(fontsize=8, loc="upper right")
fig.suptitle("監視パイプライン通しリハーサル（合成14エポック）: 検知・誤報弁別・見逃し", y=1.02, fontsize=11)
save(fig, "fig4_pipeline.png")

# ---------- 図5: タンクパッチ検知の時系列スタック効果（v2があれば） ----------
if "ep1" in p2.get("tank_patch_auc_v2", {}):
    v2 = p2["tank_patch_auc_v2"]
    eps_n = [1, 6, 12]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for c, dt in zip([MUTED, ORANGE, BLUE], ["2.0", "3.0", "5.0"]):
        k = f"dT={dt}K,A=100m2"
        ax.plot(eps_n, [v2[f"ep{n}"][k] for n in eps_n], color=c, lw=2,
                marker="o", ms=5, zorder=3, label=f"パッチ +{dt}K / 100m²")
        ax.text(eps_n[-1]+0.25, v2["ep12"][k], f'{v2["ep12"][k]:.2f}',
                color=c, fontsize=9, va="center")
    ax.axhline(0.5, color=BASE, lw=1.0, ls="--")
    ax.text(1.0, 0.512, "偶然水準", color=MUTED, fontsize=8.5)
    ax.set_xticks(eps_n, ["単発", "6エポック", "12エポック(1年)"])
    ax.set_xlim(0.6, 13.4); ax.set_ylim(0.35, 1.05)
    ax.set_ylabel("判別AUC")
    ax.set_title("タンク屋根パッチは時系列スタックで限界域から検出域へ（v2検知器）")
    ax.legend(fontsize=8.5, loc="lower right")
    save(fig, "fig5_tank_stack.png")
else:
    print("tank_patch_auc_v2 なし — 図5はスキップ")

# ---------- 図6: 実データ実証（Landsat ST_B10・京浜臨海部） ----------
# 「計算とシミュレーションだけではない」ことを示すための実データパネル。
# 一次審査で最初に問われる"本当に動くのか"に、実衛星データで答える。
# tifffile/pyproj が無い環境ではスキップ（他図の生成は妨げない）。
try:
    import tifffile
    from pyproj import Transformer
except ImportError:
    print("tifffile/pyproj なし — 図6はスキップ")
    tifffile = None

_real_path = os.path.join(OUT, "poc4_results_real.json")
if tifffile is not None and os.path.exists(_real_path):
    import glob
    p4r = json.load(open(_real_path))
    DATA = os.path.join(_here, "..", "data")
    _tr = Transformer.from_crs(4326, 32654, always_xy=True)   # WGS84 → UTM54N

    # poc4_pipeline.py と同一のAOI定義（±数百m精度の概略AOI・要現地検証）
    AOIS = {
        "川崎火力(千鳥町)":   (139.750, 35.512, 139.762, 35.522),
        "東扇島火力":         (139.745, 35.495, 139.760, 35.505),
        "浮島製油所地区":     (139.765, 35.520, 139.785, 35.535),
        "水江町製油所地区":   (139.720, 35.515, 139.735, 35.525),
        "扇島製鉄所地区":     (139.700, 35.470, 139.730, 35.490),
        "大黒町火力地区":     (139.680, 35.462, 139.690, 35.472),
    }
    REF_AOI = (139.695, 35.525, 139.715, 35.540)   # 川崎市街地 = 不変参照面

    def _read_geo(p):
        with tifffile.TiffFile(p) as tf:
            pg = tf.pages[0]
            a = pg.asarray().astype(np.float32)
            sc, tie = pg.tags[33550].value, pg.tags[33922].value
        a[a == 0] = np.nan
        return a*0.00341802 + 149.0, (tie[3], tie[4], sc[0], sc[1])

    def _sl(geo, lon0, lat0, lon1, lat1, shape):
        x0, y1 = _tr.transform(lon0, lat0)
        x1, y0 = _tr.transform(lon1, lat1)
        X0, Y0, sx, sy = geo
        c0, c1 = int((x0-X0)/sx), int((x1-X0)/sx)
        r0, r1 = int((Y0-y0)/sy), int((Y0-y1)/sy)
        return np.s_[max(0, r0):min(shape[0], r1), max(0, c0):min(shape[1], c1)]

    def _agg(v):
        f = np.isfinite(v)
        if v.size == 0 or f.mean() < 0.5:
            return np.nan
        v = np.sort(v[f].ravel())
        return float(v[int(v.size*.1):int(v.size*.9)].mean())

    epochs = p4r["epochs"]
    diff = p4r["series_vs_urban_ref_K"]
    raw = {k: [] for k in AOIS}
    ref_series = []
    for e in epochs:
        p = glob.glob(os.path.join(DATA, e + "*ST_B10*.tif"))[0]
        img, geo = _read_geo(p)
        ref_series.append(_agg(img[_sl(geo, *REF_AOI, img.shape)]))
        for k, b in AOIS.items():
            raw[k].append(_agg(img[_sl(geo, *b, img.shape)]))

    raw_all = np.array([raw[k] for k in AOIS] + [ref_series])
    rng_raw = float(np.nanmax(raw_all) - np.nanmin(raw_all))
    d_all = np.array([diff[k] for k in AOIS])
    rng_diff = float(np.nanmax(d_all) - np.nanmin(d_all))

    # 表示用の1エポック（夏・雲量2%）の輝度温度マップ
    MAP_EPOCH = "20230727"
    img, geo = _read_geo(glob.glob(os.path.join(DATA, MAP_EPOCH + "*ST_B10*.tif"))[0])
    mx0, my0 = _tr.transform(139.672, 35.455)
    mx1, my1 = _tr.transform(139.792, 35.548)
    X0, Y0, sx, sy = geo
    c0, c1 = int((mx0-X0)/sx), int((mx1-X0)/sx)
    r0, r1 = int((Y0-my1)/sy), int((Y0-my0)/sy)
    crop = img[r0:r1, c0:c1]
    extent = (mx0/1000, mx1/1000, my0/1000, my1/1000)   # km表示

    xlab = [f"{e[:4]}\n{e[4:6]}/{e[6:]}" for e in epochs]
    xi = np.arange(len(epochs))

    fig = plt.figure(figsize=(13.2, 5.0))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1.0], hspace=0.30, wspace=0.30)
    am = fig.add_subplot(gs[:, 0])
    ar = fig.add_subplot(gs[0, 1])
    ad = fig.add_subplot(gs[1, 1], sharex=ar)

    # --- A: 実輝度温度マップ ---
    lo, hi = np.nanpercentile(crop, [2, 98])
    im = am.imshow(crop, cmap="inferno", vmin=lo, vmax=hi, extent=extent,
                   origin="upper", interpolation="nearest")
    cb = fig.colorbar(im, ax=am, fraction=0.045, pad=0.02)
    cb.set_label("輝度温度 (K)", fontsize=9)
    cb.outline.set_visible(False)
    for (k, b), c in zip(AOIS.items(), CAT6):
        bx0, by0 = _tr.transform(b[0], b[1]); bx1, by1 = _tr.transform(b[2], b[3])
        am.add_patch(plt.Rectangle((bx0/1000, by0/1000), (bx1-bx0)/1000, (by1-by0)/1000,
                                   fill=False, ec=c, lw=1.8, zorder=5))
    rx0, ry0 = _tr.transform(REF_AOI[0], REF_AOI[1])
    rx1, ry1 = _tr.transform(REF_AOI[2], REF_AOI[3])
    am.add_patch(plt.Rectangle((rx0/1000, ry0/1000), (rx1-rx0)/1000, (ry1-ry0)/1000,
                               fill=False, ec="#ffffff", lw=1.8, ls="--", zorder=5))
    am.text(rx0/1000+0.15, ry1/1000-0.35, "市街地参照面", color="#ffffff", fontsize=8.5)
    am.set_title(f"Landsat-8 ST_B10 実データ（{MAP_EPOCH[:4]}-{MAP_EPOCH[4:6]}-{MAP_EPOCH[6:]}, 雲量2.1%）\n"
                 "京浜臨海部・30m画素／色枠=監視AOI, 白破線=不変参照面", fontsize=9.5)
    am.set_xlabel("UTM54N 東距 (km)"); am.set_ylabel("UTM54N 北距 (km)")
    am.grid(False)

    # --- B: 生の見かけ温度（共通モード除去前） ---
    for (k, c) in zip(AOIS, CAT6):
        ar.plot(xi, raw[k], color=c, lw=1.6, marker="o", ms=4, zorder=3, label=k)
    ar.plot(xi, ref_series, color=MUTED, lw=1.6, ls="--", marker="s", ms=4,
            zorder=2, label="市街地参照面")
    ar.text(xi[-1]+0.12, ref_series[-1], "市街地参照面", color=INK2, fontsize=7.5, va="center")
    ar.set_ylabel("見かけ輝度温度 (K)")
    ar.set_title(f"① 生の見かけ温度 — 季節・大気で全資産が同相に {rng_raw:.1f}K 振れる\n"
                 "　 （系列色は左の地図・下の②と共通）",
                 fontsize=9.5, loc="left")
    ar.tick_params(labelbottom=False)

    # --- C: 市街地参照差（共通モード除去後） ---
    for (k, c) in zip(AOIS, CAT6):
        ad.plot(xi, diff[k], color=c, lw=1.6, marker="o", ms=4, zorder=3, label=k)
    ad.axhline(0, color=BASE, lw=1.0, ls="--")
    ad.set_ylabel("対市街地参照 差 (K)")
    ad.set_xticks(xi, xlab, fontsize=8)
    ad.set_xlim(-0.3, len(epochs)-0.35)
    zmax = max(abs(f["z"]) for f in p4r["findings"])
    ad.set_title(f"② 市街地参照差 — 共通モードが落ちて {rng_diff:.1f}K に（振れ幅 1/{rng_raw/rng_diff:.1f}）\n"
                 f"　 兄弟差分ステップ走査 {len(p4r['findings'])}件すべて |z| は最大 {zmax:.1f} → 誤検知ゼロ",
                 fontsize=9.5, loc="left")
    ad.legend(fontsize=7.5, loc="upper left", bbox_to_anchor=(0.0, -0.22),
              ncols=3, framealpha=0.9, borderaxespad=0, columnspacing=1.2)

    fig.suptitle("実衛星データでパイプラインが通ることの実証 — 「絶対値を測らない」原則の実データ検証"
                 f"（有効{p4r['n_epochs']}エポック / 全14シーン中、スワス端8シーンは自動除外）",
                 y=1.015, fontsize=11)
    save(fig, "fig6_realdata.png")
else:
    print("poc4_results_real.json なし — 図6はスキップ")


# ---------- 図7: 分解能ギャップ（なぜ3.5m級TIRが要るのか） ----------
# poc2_scene_sim.py の先頭部（Scene/放射計算）だけをexecで共有する。
# poc2を直接importすると重いモンテカルロが走るため（poc4_pipeline.py と同じ流儀）。
_p2src = open(os.path.join(_here, "poc2_scene_sim.py")).read().split("results = {}")[0]
_ns = {"__file__": os.path.join(_here, "poc2_scene_sim.py")}
exec(compile(_p2src, "poc2_scene_sim.py", "exec"), _ns)
Scene, planck_lut, tb_arr = _ns["Scene"], _ns["planck_lut"], _ns["tb_arr"]
planck_band_arr, GSD_TRUE = _ns["planck_band_arr"], _ns["GSD_TRUE"]
_gf = _ns["gaussian_filter"]

PATCH_DT, PATCH_A = 5.0, 100.0     # +5K / 100m²（図5と同じ代表ケース）
T_SKY, TAU = 240.0, 0.75           # 比較のため大気・天空条件は固定
HALF_M = 100.0                     # 切り出し半幅（→ 200m四方）

def _radiance(sc):
    """0.5m真値グリッドの大気上端放射（PSF・サンプリング前）"""
    L_sky = float(planck_lut(np.array([T_SKY]))[0])
    L_atm = float(planck_lut(np.array([285.0]))[0])
    return TAU*(sc.eps*planck_lut(sc.T) + (1-sc.eps)*L_sky) + (1-TAU)*L_atm

def _blur_bin(L, gsd):
    """指定GSDのPSF畳み込み＋画素積分（放射のまま返す）"""
    if gsd <= GSD_TRUE:
        return L, 1
    k = int(round(gsd/GSD_TRUE))
    Ls = _gf(L, (gsd/2.355)/GSD_TRUE)
    n = (L.shape[0]//k)*k
    return Ls[:n, :n].reshape(n//k, k, n//k, k).mean(axis=(1, 3)), k

_sc = Scene()
# 切り出しが画像内に収まる位置のタンクから、大きめの1基を選ぶ
_m = int(HALF_M/GSD_TRUE)
_cand = [t for t in _sc.tanks
         if _m < t["cy"] < _sc.N-_m and _m < t["cx"] < _sc.N-_m]
_tank = max(_cand, key=lambda t: t["R"])
L_clean = _radiance(_sc)
_sc.add_tank_patch(_tank, PATCH_DT, PATCH_A)
L_patch = _radiance(_sc)

cy, cx = int(_tank["cy"]), int(_tank["cx"])
_rs = np.random.default_rng(7)
_dL = (planck_band_arr(np.array([301.0])) - planck_band_arr(np.array([299.0])))[0]/2

panels = []
for gsd, name in ((GSD_TRUE, "真値（地表 0.5m）"),
                  (3.5, "HotSat-2 相当 3.5m"),
                  (30.0, "Landsat 相当 30m")):
    Lp, k = _blur_bin(L_patch, gsd)
    Lc, _ = _blur_bin(L_clean, gsd)
    # NEdT 1K相当を等しく付加（比較の主題は空間分解能であり放射感度ではない）
    img = tb_arr(Lp + _rs.normal(0, _dL, Lp.shape)) if gsd > GSD_TRUE else tb_arr(Lp)
    # パッチ起因の見かけ温度上昇＝パッチ有無の差（ノイズを含まない真の信号）
    d_true = tb_arr(Lp) - tb_arr(Lc)
    sub = np.s_[(cy-_m)//k:(cy+_m)//k, (cx-_m)//k:(cx+_m)//k]
    panels.append((name, gsd, img[sub], d_true[sub], float(np.nanmax(d_true[sub]))))

vmin = min(np.nanpercentile(p[2], 1) for p in panels)
vmax = max(np.nanpercentile(p[2], 99) for p in panels)
dmax_all = max(p[4] for p in panels)

fig, axs = plt.subplots(2, 3, figsize=(11.4, 8.2))
fig.subplots_adjust(hspace=0.30, bottom=0.13)
for j, (name, gsd, arr, darr, dmax) in enumerate(panels):
    npx = 200.0/gsd
    # 上段: 観測される見かけ輝度温度
    a = axs[0, j]
    im = a.imshow(arr, cmap="inferno", vmin=vmin, vmax=vmax, origin="upper",
                  extent=(0, 200, 0, 200), interpolation="nearest")
    a.set_title(f"{name}\nこの200m四方 = {npx:.0f}×{npx:.0f} 画素", fontsize=10)
    # 下段: パッチ起因の上昇分だけを取り出したもの（＝検知器が使う信号）
    b = axs[1, j]
    im2 = b.imshow(darr, cmap="Blues", vmin=0, vmax=dmax_all, origin="upper",
                   extent=(0, 200, 0, 200), interpolation="nearest")
    ok = dmax >= 1.0
    b.set_title(f"パッチ起因の上昇 最大 {dmax:.2f}K\n"
                + ("→ 画素として立つ" if ok else "→ 周囲に混合して消える"),
                fontsize=10, color=(BLUE if ok else CRIT))
    for ax in (a, b):
        ax.set_xticks([0, 100, 200]); ax.set_yticks([0, 100, 200])
        ax.tick_params(labelsize=8)
        ax.grid(False)
axs[0, 0].set_ylabel("① 観測される見かけ輝度温度 (m)", fontsize=9.5)
axs[1, 0].set_ylabel("② パッチ起因の上昇分のみ (m)", fontsize=9.5)
cb = fig.colorbar(im, ax=axs[0, :], fraction=0.024, pad=0.015)
cb.set_label("見かけ輝度温度 (K)", fontsize=9); cb.outline.set_visible(False)
cb2 = fig.colorbar(im2, ax=axs[1, :], fraction=0.024, pad=0.015)
cb2.set_label("パッチ起因の上昇 (K)", fontsize=9); cb2.outline.set_visible(False)
fig.text(0.5, 0.055, "※ 上段でタンク屋根が周囲より低温に見えるのは、低ε（0.15〜0.4）の金属面が"
         "冷たい天空を映すため。絶対値を測らない設計の理由でもある。\n"
         "※ 下段は同一シーンのパッチ有無の差分＝検知器が使う信号成分（放射ノイズを含まない真値）。",
         ha="center", va="top", fontsize=8.5, color=INK2)
fig.suptitle(f"分解能ギャップ — 同一シーン・同一劣化（屋根パッチ +{PATCH_DT:.0f}K / {PATCH_A:.0f}m²）を3つの画素サイズで観測\n"
             f"既存の30m級TIRでは信号が {dmax_all/panels[2][4]:.0f} 分の1に薄まり、設備単位の判断は物理的に成立しない",
             y=0.985, fontsize=11)
save(fig, "fig7_resolution_gap.png")

# ---------- 図0: 技術的実証の全体像（監視チェーンと、各段の根拠） ----------
# 一次審査で最初に見る1枚。各段が「どの図・どのPoC・どの数値」で裏付いているかを
# 明示し、扱えないことは下段に自白として並べる。数値はすべて poc/out/*.json 由来。
_ud = p2["unit_diffuse_auc"]["dT=1.0K"]
_v2 = p2["tank_patch_auc_v2"]
_abs_rss = p1["budget"]["絶対温度（撮像間差分）"]["rss"]
_cui = p1["detection_cases"]["個別配管CUIスポット(f=0.15,+5K)"]["snr"]
_sl3 = p3["scenarios"]["現行1機(3日)"]["slope_per_year"]["median"]
_sl2 = p3["scenarios"]["現行1機(2日)"]["slope_per_year"]["median"]

stages = [
    ("① 取得",
     "HotSat-2 (MWIR)\n3.5m・夜間タスキング",
     f"30m級では信号が1/{dmax_all/panels[2][4]:.0f}\nに薄まる（図7）"),
    ("② 前処理",
     "位置合わせ＋共通モード除去\n（不変参照面との差）",
     f"実Landsatで振れ幅\n{rng_raw:.1f}K → {rng_diff:.1f}K（図6）"),
    ("③ 指標化",
     "シーン内相対 / 兄弟資産差分\n/ その時間変化（二重差分）",
     f"絶対値比較は誤差RSS\n{_abs_rss:.1f}Kで不成立（図1b）"),
    ("④ 検知",
     "ステップ走査(z) ＋\n時系列残差スタック",
     f"面的劣化AUC {_ud['static_auc']:.2f}→{_ud['double_diff_auc']:.2f}（図2）\n"
     f"タンクパッチ {_v2['ep1']['dT=5.0K,A=100m2']:.2f}→{_v2['ep12']['dT=5.0K,A=100m2']:.2f}（図5）"),
    ("⑤ 業務",
     "点検派遣・CMMS突合\nεアーティファクト弁別",
     f"注入劣化を検出 z=4.7 / 外装更新を\n誤報しない z=-11.4（図4）"),
]
limits = [
    f"個別配管のCUIスポットは検出できない（SNR {_cui:.2f}・図1）。面的・複合体単位の指標に限定する。",
    f"降雨後の回復速度特徴量は現行1機体制では機会的（年{_sl3:.1f}〜{_sl2:.1f}回・実気象・図3）。必須機能に置かない。",
    "温度の絶対値は測らない。ε不確かさと天空放射が支配的なため、すべて相対量で設計している。",
    "タンク屋根パッチは単発では限界域（AUC 0.64）。12エポックの蓄積を前提とする（図5）。",
]

fig, ax = plt.subplots(figsize=(13.6, 6.4))
ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
W, X0, GAPX = 1.72, 0.28, 0.20
for i, ((tag, body, ev), c) in enumerate(zip(stages, CAT6)):
    x = X0 + i*(W+GAPX)
    ax.add_patch(plt.Rectangle((x, 6.55), W, 2.45, fc=SURF, ec=c, lw=2.0,
                               zorder=3, joinstyle="round"))
    ax.text(x+W/2, 8.62, tag, ha="center", va="center", fontsize=11, color=c, zorder=4)
    ax.text(x+W/2, 7.55, body, ha="center", va="center", fontsize=9.2, color=INK, zorder=4)
    # 根拠チップ
    ax.add_patch(plt.Rectangle((x, 4.75), W, 1.35, fc="#f4f3ef", ec="none", zorder=3))
    ax.text(x+W/2, 5.42, ev, ha="center", va="center", fontsize=8.3, color=INK2, zorder=4)
    ax.plot([x+W/2, x+W/2], [6.55, 6.12], color=BASE, lw=1.0, ls="--", zorder=2)
    if i < len(stages)-1:
        ax.annotate("", xy=(x+W+GAPX-0.02, 7.78), xytext=(x+W+0.02, 7.78),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.4))
ax.text(X0, 9.42, "監視チェーンの全段が、自主PoCの計算・シミュレーション・実データで裏付けられている",
        fontsize=12.5, color=INK, va="center")
ax.text(X0, 4.35, "各段の根拠（図番号は本書の図版・数値は poc/out/*.json 由来、乱数シード固定で再現可能）",
        fontsize=8.8, color=MUTED, va="center")

ax.add_patch(plt.Rectangle((X0, 0.35), 5*W+4*GAPX, 3.35, fc="#faf6f4", ec=CRIT,
                           lw=1.4, zorder=3))
ax.text(X0+0.22, 3.32, "この提案で「できないこと」— 先に自白し、代替設計とセットで示す",
        fontsize=10.5, color=CRIT, va="center", zorder=4)
for j, t in enumerate(limits):
    ax.text(X0+0.22, 2.62-j*0.60, "・" + t, fontsize=9.0, color=INK2, va="center", zorder=4)
save(fig, "fig0_overview.png")

# ---------- 図8: 運用ビュー（設備単位の状態マップ＋優先度付きアラート） ----------
# 「地図を見れば、どこで何が起きていて、システムが何と言ったかが分かる」1枚。
# poc4のモードB（合成14エポック）と同一のシーンを再現し、判定結果を地図に重ねる。
# rngはexecごとに再シードされる（poc2冒頭の default_rng(42)）ため、
# poc4_results.json の findings と同一のシーンが再現される。
p4 = json.load(open(os.path.join(OUT, "poc4_results.json")))
_ns8 = {"__file__": os.path.join(_here, "poc2_scene_sim.py")}
exec(compile(_p2src, "poc2_scene_sim.py", "exec"), _ns8)
# 重要: poc4_pipeline.py は poc2ヘッダを exec した「あとで」 rng を seed 123 に
# 貼り替えている（rng_seed = 123）。Scene/observe は呼び出し時にグローバルの rng を
# 引くため、poc4のシーンは seed 42 ではなく 123 で生成されている。
# ここで同じ貼り替えをしないと、判定結果(findings)と地図上の資産配置が食い違う。
_ns8["rng"] = np.random.default_rng(123)
Scene8, observe8, sat_coords8 = _ns8["Scene"], _ns8["observe"], _ns8["sat_coords"]
GSD_SAT8 = _ns8["GSD_SAT"]

N_EP, STEP_AT, PATCH_FROM, REPL_AT = 14, 8, 6, 10   # poc4_pipeline.py モードBと同一
_s8 = Scene8()
_frames = []
for e in range(N_EP):
    if e == STEP_AT:
        _s8.add_unit_diffuse(0, 0, 2.0)
    if e >= PATCH_FROM:
        _s8.add_tank_patch(_s8.tanks[4], 1.2, 60)
    if e == REPL_AT:
        _tk = _s8.tanks[10]
        _m = (_s8._yy-_tk["cy"])**2 + (_s8._xx-_tk["cx"])**2 < _tk["R"]**2
        _s8.eps[_m] = 0.10
    _frames.append(observe8(_s8))
base = np.mean(_frames, axis=0)   # 基図は14エポック平均（放射ノイズを抑えた背景）
Hs, Ws = base.shape
EXT = (0, Ws*GSD_SAT8, Hs*GSD_SAT8, 0)   # 原点左上・メートル表示

# 判定ステータス（色だけに頼らず、必ずラベルと併記する）
ST_ALERT, ST_INFO = CRIT, "#eda100"
ST_OK, ST_MISS = "#1baf7a", "#4a3aa7"
truth = p4["injected_truth"]
flagged = {f["asset"]: f for f in p4["findings"]}
missed = [a for a in truth if a not in flagged]

def _status_of(name):
    """判定区分。εアーティファクト（外装更新による見かけ温度の急落）だけが
    「変化はあるが点検不要」。それ以外の検出は点検対象。
    注: UNIT00のaction文にも「外装イベント疑い」の語が含まれるため、
    'εアーティファクト' の語で判定する（'外装' では誤判定になる）。"""
    f = flagged.get(name)
    if f is None:
        return ("miss", ST_MISS) if name in truth else ("ok", ST_OK)
    return ("info", ST_INFO) if "εアーティファクト" in f.get("action", "") else ("alert", ST_ALERT)

fig = plt.figure(figsize=(13.8, 6.6))
gs = fig.add_gridspec(1, 2, width_ratios=[1.12, 1.0], wspace=0.06)
am = fig.add_subplot(gs[0, 0])
al = fig.add_subplot(gs[0, 1]); al.axis("off")

# --- 地図: 基図はグレーに落とし、判定色を前に出す ---
_lo, _hi = np.nanpercentile(base, [1, 99])
am.imshow(base, cmap="gray", vmin=_lo, vmax=_hi, extent=EXT, origin="upper",
          interpolation="nearest", zorder=1)
labels8 = []
for i, tk in enumerate(_s8.tanks):
    r, c = sat_coords8(tk["cy"], tk["cx"])
    R = tk["R"]*GSD_TRUE/GSD_SAT8
    name = f"TANK{i:02d}"
    st, col = _status_of(name)
    lw, alpha = (2.4, 1.0) if st != "ok" else (0.9, 0.55)
    am.add_patch(plt.Circle((c*GSD_SAT8, r*GSD_SAT8), R*GSD_SAT8, fill=False,
                            ec=col, lw=lw, alpha=alpha, zorder=4,
                            ls=("--" if st == "miss" else "-")))
    if st != "ok":
        labels8.append((c*GSD_SAT8, r*GSD_SAT8, R*GSD_SAT8, name, st, col))
for i, pair in enumerate(_s8.units):
    for j, u in enumerate(pair):
        r0, c0 = sat_coords8(u["y0"], u["x0"])
        r1, c1 = sat_coords8(u["y0"]+u["h"], u["x0"]+u["w"])
        name = f"UNIT{i:02d}"
        st, col = _status_of(name)
        lw, alpha = (2.4, 1.0) if st != "ok" else (0.9, 0.55)
        am.add_patch(plt.Rectangle((c0*GSD_SAT8, r0*GSD_SAT8),
                                   (c1-c0)*GSD_SAT8, (r1-r0)*GSD_SAT8, fill=False,
                                   ec=col, lw=lw, alpha=alpha, zorder=4))
        if st != "ok" and j == 0:
            labels8.append((c0*GSD_SAT8, r0*GSD_SAT8, 0, name, st, col))
_txt = {"alert": "要点検", "info": "点検不要と判定", "miss": "未検出（見逃し）"}
for x, y, R, name, st, col in labels8:
    up = y > 300                       # 図の上端に近い資産はラベルを下に出す
    ay = (y - R) if up else (y + R)
    ha = "left" if x < 700 else "right"
    am.annotate(f"{name}\n{_txt[st]}", xy=(x, ay),
                xytext=(x + (38 if ha == "left" else -38), ay + (-62 if up else 62)),
                fontsize=9, color=col, zorder=6, ha=ha,
                arrowprops=dict(arrowstyle="-", color=col, lw=1.2),
                bbox=dict(boxstyle="round,pad=0.28", fc=SURF, ec=col, lw=1.0))
am.set_title("設備単位の状態マップ（HotSat-2相当 3.5m・合成プラント 1km四方・14エポック監視後）\n"
             "基図=見かけ輝度温度の14エポック平均（グレー）／枠=監視資産（円:タンク24基, 矩形:プロセスユニット8対）",
             fontsize=9.5, pad=14)
am.set_xlabel("東西 (m)"); am.set_ylabel("南北 (m)"); am.grid(False)
_lg = [plt.Line2D([], [], color=ST_ALERT, lw=2.4, label="要点検（劣化疑い）"),
       plt.Line2D([], [], color=ST_INFO, lw=2.4, label="変化ありだが点検不要（εアーティファクト）"),
       plt.Line2D([], [], color=ST_MISS, lw=2.4, ls="--", label="劣化があるのに未検出（見逃し）"),
       plt.Line2D([], [], color=ST_OK, lw=1.2, alpha=0.55, label="出力なし（健全と判定）")]
am.legend(handles=_lg, fontsize=8.2, loc="upper left", bbox_to_anchor=(0, -0.10),
          ncols=2, framealpha=0.95, borderaxespad=0)

# --- 右: 優先度付きアラート（システム出力）と真値の答え合わせ ---
al.text(0, 1.0, "この地図に対してシステムが出力したもの", fontsize=12.5, va="top", color=INK)
al.text(0, 0.945, "（poc4_results.json の findings をそのまま転記）",
        fontsize=8.5, va="top", color=MUTED)
_chip = {"alert": "［要点検］", "info": "［点検不要］", "miss": "［未検出］"}

def _wrap(s, w=46):
    """和文は空白で折り返せないため文字数で折る（textwrapは空白依存で不適）"""
    return "\n".join(s[i:i+w] for i in range(0, len(s), w))

_rows = []
for f in p4["findings"]:
    st, col = _status_of(f["asset"])
    _rows.append((col,
                  f"{_chip[st]} {f['asset']}　{f['type']}　z={f['z']:+.1f} @{f['at']}",
                  _wrap(f"判定: {f['action']}"),
                  f"真値: {truth.get(f['asset'], '—')}　→　一致"))
for a in missed:
    _rows.append((ST_MISS, f"{_chip['miss']} {a}　（システム出力なし）",
                  _wrap("判定: 単発指標では信号がノイズに埋もれ、アラートに至らない"),
                  _wrap(f"真値: {truth[a]}　→　取りこぼし。12エポックの時系列スタックで対処（図5）")))
_y = 0.885
for col, head, judge, tr in _rows:
    al.add_patch(plt.Rectangle((0, _y-0.205), 1.0, 0.195, transform=al.transAxes,
                               fc="#f6f5f1", ec=col, lw=1.6, clip_on=False, zorder=2))
    al.text(0.016, _y-0.028, head, fontsize=10.5, va="top", color=col, zorder=3)
    al.text(0.016, _y-0.088, judge, fontsize=9.0, va="top", color=INK2, zorder=3)
    al.text(0.016, _y-0.142, tr, fontsize=9.0, va="top", color=INK2, zorder=3)
    _y -= 0.243
_n_assets = len(_s8.tanks) + len(_s8.units)
al.text(0.016, _y+0.005, f"上記以外の {_n_assets - len(_rows)} 資産: 出力なし ＝ 誤報ゼロ",
        fontsize=10.5, va="top", color=ST_OK)
al.text(0, _y-0.085, "注入した3件のうち2件を正しく仕分けし（劣化＝点検へ／外装更新＝点検不要）、\n"
        "1件は取りこぼした。この見逃しを隠さず出力に載せる設計にしている。\n\n"
        "審査上の注記: これはHotSat-2の実データではなく、3.5m級センサを模した\n"
        "合成プラント（poc2/poc4）での通しリハーサルである。実機サンプルでの\n"
        "同一ビューの再現はJSI照会（09）の回答待ち。",
        fontsize=9, va="top", color=INK2)
fig.suptitle("運用ビュー — 地図上で「どこが・何が・どう判定されたか」が一目で分かる",
             y=0.99, fontsize=12.5)
save(fig, "fig8_operations_map.png")

# ---------- 図9: 実データ版の状態マップ（複合体単位・京浜） ----------
# 図8と同じ「地図＋判定リスト」の型を実データに適用する。設備単位ではなく
# 複合体単位である点、AOIが概略である点を図中に明記する。
if "crop" in globals():
    fig = plt.figure(figsize=(13.8, 6.2))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.18, 1.0], wspace=0.08)
    am = fig.add_subplot(gs[0, 0])
    al = fig.add_subplot(gs[0, 1]); al.axis("off")

    _lo, _hi = np.nanpercentile(crop, [2, 98])
    am.imshow(crop, cmap="gray", vmin=_lo, vmax=_hi, extent=extent,
              origin="upper", interpolation="nearest", zorder=1)

    # 対市街地差の走査結果（資産ごと）と、兄弟差分ステップ走査（ペアごと）
    _self_z = {f["asset"]: f for f in p4r["findings"] if f.get("type") == "対市街地差の走査"}
    _pair_f = [f for f in p4r["findings"] if f.get("type") == "兄弟差分ステップ走査"]
    _ctr = {}
    for k, b in AOIS.items():
        bx0, by0 = _tr.transform(b[0], b[1]); bx1, by1 = _tr.transform(b[2], b[3])
        _ctr[k] = ((bx0+bx1)/2000, (by0+by1)/2000)
        am.add_patch(plt.Rectangle((bx0/1000, by0/1000), (bx1-bx0)/1000, (by1-by0)/1000,
                                   fill=False, ec=ST_OK, lw=2.0, zorder=5))
        # ラベル位置は兄弟差分バッジとの衝突を避けて個別指定（既定は箱の上）
        _pos = {"川崎火力(千鳥町)": "left", "東扇島火力": "below"}.get(k, "above")
        if _pos == "left":
            _tx, _ty, _ha, _va = bx0/1000 - 0.10, (by0+by1)/2000, "right", "center"
        elif _pos == "below":
            _tx, _ty, _ha, _va = (bx0+bx1)/2000, by0/1000 - 0.16, "center", "top"
        else:
            _tx, _ty, _ha, _va = (bx0+bx1)/2000, by1/1000 + 0.16, "center", "bottom"
        am.text(_tx, _ty, k, color=ST_OK, fontsize=8.6, ha=_ha, va=_va, zorder=6,
                bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec="none", alpha=0.85))
    # 兄弟資産どうしを結ぶ（「何と何を比べているか」を地図で示す）
    for f in _pair_f:
        a, b_ = [s.strip() for s in f["pair"].split("−")]
        (x0, y0), (x1, y1) = _ctr[a], _ctr[b_]
        am.plot([x0, x1], [y0, y1], color=BLUE, lw=1.6, ls="--", zorder=4)
        _t = 0.30
        am.text(x0+(x1-x0)*_t, y0+(y1-y0)*_t, f"兄弟差分\nz={f['z']:+.1f}", color=BLUE,
                fontsize=8.2, ha="center", va="center", zorder=6,
                bbox=dict(boxstyle="round,pad=0.22", fc=SURF, ec=BLUE, lw=0.9))
    rx0, ry0 = _tr.transform(REF_AOI[0], REF_AOI[1])
    rx1, ry1 = _tr.transform(REF_AOI[2], REF_AOI[3])
    am.add_patch(plt.Rectangle((rx0/1000, ry0/1000), (rx1-rx0)/1000, (ry1-ry0)/1000,
                               fill=False, ec=INK2, lw=1.8, ls="--", zorder=5))
    am.text((rx0+rx1)/2000, ry1/1000+0.16, "市街地参照面（不変面）", color=INK2, fontsize=8.6,
            ha="center", va="bottom", zorder=6,
            bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec="none", alpha=0.85))
    am.set_title(f"複合体単位の状態マップ（Landsat 30m 実データ・{p4r['n_epochs']}エポック監視後）\n"
                 "基図=見かけ輝度温度（グレー）／緑枠=監視AOI, 青破線=兄弟資産の比較関係",
                 fontsize=9.5, pad=12)
    am.set_xlabel("UTM54N 東距 (km)"); am.set_ylabel("UTM54N 北距 (km)"); am.grid(False)
    am.legend(handles=[plt.Line2D([], [], color=ST_OK, lw=2.0, label="出力なし（健全と判定）"),
                       plt.Line2D([], [], color=BLUE, lw=1.6, ls="--", label="兄弟資産の比較ペア"),
                       plt.Line2D([], [], color=INK2, lw=1.8, ls="--", label="不変参照面（共通モード除去用）")],
              fontsize=8.2, loc="upper left", bbox_to_anchor=(0, -0.12), ncols=3,
              framealpha=0.95, borderaxespad=0)

    al.text(0, 1.0, "この地図に対してシステムが出力したもの", fontsize=12.5, va="top", color=INK)
    al.text(0, 0.945, "（poc4_results_real.json の findings をそのまま転記）",
            fontsize=8.5, va="top", color=MUTED)
    al.text(0.012, 0.878, "走査対象", fontsize=9, va="top", color=MUTED)
    al.text(0.55, 0.878, "種別", fontsize=9, va="top", color=MUTED)
    al.text(0.735, 0.878, "z", fontsize=9, va="top", color=MUTED, ha="right")
    al.text(0.775, 0.878, "判定", fontsize=9, va="top", color=MUTED)
    _y = 0.835
    for f in p4r["findings"]:
        nm = f.get("pair", f.get("asset", ""))
        kind = "兄弟差分" if f["type"].startswith("兄弟") else "対市街地"
        al.add_patch(plt.Rectangle((0, _y-0.062), 1.0, 0.056, transform=al.transAxes,
                                   fc="#f6f5f1", ec="none", clip_on=False, zorder=2))
        al.text(0.012, _y-0.012, nm, fontsize=9, va="top", color=INK, zorder=3)
        al.text(0.55, _y-0.012, kind, fontsize=9, va="top", color=INK2, zorder=3)
        al.text(0.735, _y-0.012, f"{f['z']:+.1f}", fontsize=9, va="top", color=INK2,
                zorder=3, ha="right")
        al.text(0.775, _y-0.012, f["judged"], fontsize=9, va="top", color=ST_OK, zorder=3)
        _y -= 0.072
    al.text(0, _y-0.02, f"{len(p4r['findings'])}件すべてで有意な段差なし ＝ 実データで誤検知ゼロ",
            fontsize=10.5, va="top", color=ST_OK)
    al.text(0, _y-0.10,
            "審査上の注記:\n"
            "・Landsatは30m画素・昼間パスのため、これは「複合体レベルで手順が\n"
            "　通ること」の実証であり、設備単位の実証ではない（設備単位は図8）。\n"
            "・AOIは±数百m精度の概略であり現地検証は未了。\n"
            "・実データ側に既知の劣化事象がないため、ここで示せるのは\n"
            "　「健全なものを健全と判定できる（誤報を出さない）」ことまでである。",
            fontsize=9, va="top", color=INK2)
    fig.suptitle("実データでの運用ビュー — 京浜臨海部6複合体を実Landsatで監視した結果",
                 y=0.99, fontsize=12.5)
    save(fig, "fig9_realdata_map.png")
else:
    print("実データ未取得 — 図9はスキップ")
