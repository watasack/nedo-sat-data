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

# 参照パレット（ライト）
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
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
    "加熱炉・高温配管系の保温不良(+15K)": "加熱炉・高温配管系の保温不良 (+15K)",
    "タンク屋根の劣化パッチ(+5K)": "タンク屋根の劣化パッチ (+5K, 100m²)",
    "タンク屋根の劣化パッチ(+3K,100m²≈8px)": "タンク屋根の劣化パッチ (+3K, 100m²)",
    "ユニット面的劣化(+1K) 二重差分×6エポック": "ユニット面的劣化 (+1K) 二重差分×6エポック",
    "ユニット面的劣化(+1K) 対双子資産": "ユニット面的劣化 (+1K) 兄弟差分・単発",
    "個別配管CUIスポット(f=0.15,+5K)": "個別配管CUIスポット (+5K, 充足率0.15)",
}
fig, ax = plt.subplots(figsize=(8, 3.6))
y = np.arange(len(order))
ax.barh(y, snrs, height=0.55, color=BLUE, zorder=3)
ax.axvline(1.0, color=CRIT, lw=1.2, ls="--", zorder=4)
ax.text(1.07, 0.5, "検出限界 SNR=1", color=CRIT, fontsize=9, va="center")
for yi, s in zip(y, snrs):
    ax.text(s+0.07, yi, f"{s:.2f}", va="center", fontsize=9, color=INK2)
ax.set_yticks(y, [names[k] for k in order])
ax.set_xlabel("SNR（信号/誤差RSS, NEdT=1K仮定・単発観測）")
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
a2.plot(ep, t10, color=ORANGE, lw=2, marker="o", ms=4, zorder=3, label="TANK10（ep10で外装張替え）")
a2.plot(ep, t04, color=MUTED, lw=2, marker="o", ms=4, zorder=2, label="TANK04（参照）")
a2.axvline(10, color=CRIT, lw=1.0, ls="--")
a2.text(10.15, -18.6, "検出 z=-11.4\n→εアーティファクトと分類\n（劣化と誤報しない）", color=CRIT, fontsize=8.5)
a2.set_title("タンク見かけ温度 — 外装更新の弁別")
a2.set_xlabel("エポック（月次相当）"); a2.set_ylabel("対地面 輝度温度差 (K)")
a2.legend(fontsize=8, loc="upper right")
fig.suptitle("監視パイプライン通しリハーサル（合成14エポック）: 検知と誤報弁別", y=1.02, fontsize=11)
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
