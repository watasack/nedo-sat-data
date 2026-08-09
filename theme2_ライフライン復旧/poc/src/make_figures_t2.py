"""テーマ2 様式4の図版を生成する（図1〜図4）

割当は `12_提出版_様式4.md` の「図表の割当」節に従う。
  図1 ① 火口の積雪から下流の判断までの全段と、その裏付けおよび限界
  図2 ② 山麓6観測所からの標高外挿と、火口高度の実測との食い違い
  図3 ③ 消雪日を特定できる年数の実測（8火山・カタログ集計）
  図4 ⑤ 想定ユーザー、予算の所在、事業化の二段階
（④は本文中の表1なので図版は無い）

**図の中にファイル名や他図への参照を書かないこと**——テーマ1で実際に混入させて
作り直した。ここでも書いていない。

数値の出典は `01_検討経緯.md` 8.4〜8.7節。図2・図3は同節の実測値をそのまま使う。
出力: theme2_ライフライン復旧/poc/out/fig/
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib_fontja  # noqa: F401  日本語フォント
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "fig")
os.makedirs(_OUT, exist_ok=True)

INK = "#1a1a1a"
ACCENT = "#c0392b"      # 実測・食い違いを示す赤
BASE = "#2c5f8d"        # 計画・既存を示す青
MUTED = "#8a8a8a"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "text.color": INK})


def _box(ax, x, y, w, h, text, fc="white", ec=BASE, fs=9.5, lw=1.4, weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            zorder=3, linespacing=1.45, fontweight=weight)


def _arrow(ax, x1, y1, x2, y2, color=INK, lw=1.5):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                                 color=color, lw=lw, zorder=1,
                                 shrinkA=2, shrinkB=2))


# ============================================================
# 図1 監視の全段と、その裏付けおよび限界
# ============================================================
def fig1():
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    stages = [
        (0.015, "光学衛星\nアーカイブ", "Landsat 1984年〜\nSentinel-2 / MODIS\nすべて無償"),
        (0.212, "各年の\n消雪日マップ", "火口周辺を面的に\n±10日で特定"),
        (0.409, "後退積算による\n積雪水量の復元", "融雪量を消雪日から\n遡って積算"),
        (0.606, "年超過確率分布\n（2年・10年）", "指針が求める\n評価の形にする"),
        (0.803, "泥流総量 → \n下流の判断", "現況施設での処理可否\n対策の規模と工期"),
    ]
    w, y = 0.182, 0.60
    for i, (x, title, sub) in enumerate(stages):
        _box(ax, x, y, w, 0.20, title, fs=10.5, weight="bold")
        ax.text(x + w / 2, y - 0.055, sub, ha="center", va="top", fontsize=8.6,
                color=MUTED, linespacing=1.4)
        if i:
            _arrow(ax, x - 0.015, y + 0.10, x, y + 0.10)

    # 裏付け（下向き）
    ax.text(0.5, 0.435, "裏付け", ha="center", fontsize=10, fontweight="bold", color=BASE)
    ev = [
        (0.165, "8火山でカタログを\n直接集計し実測"),
        (0.500, "蔵王計画の公表8値を\n誤差0.44%以内で再現"),
        (0.835, "十勝岳は積雪深54.6cmで\n区分が反転する"),
    ]
    for x, t in ev:
        _box(ax, x - 0.145, 0.285, 0.29, 0.115, t, fc="#eef4fa", ec=BASE, fs=8.8, lw=1.0)

    # 限界（自白）
    ax.text(0.5, 0.225, "限界（先に自白する）", ha="center", fontsize=10,
            fontweight="bold", color=ACCENT)
    lim = [
        (0.165, "100年超過確率は\n外挿になる"),
        (0.500, "融雪係数の文献幅が\n±33%の系統誤差"),
        (0.835, "火口高度の実測は\n蔵王の4冬期分のみ"),
    ]
    for x, t in lim:
        _box(ax, x - 0.145, 0.055, 0.29, 0.115, t, fc="#fdf0ee", ec=ACCENT, fs=8.8, lw=1.0)

    ax.text(0.5, 0.955, "火口の積雪を測ることが、下流の判断を変える",
            ha="center", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(_OUT, "t2_fig1_chain.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# 図2 山麓6観測所からの外挿と、火口高度の実測との食い違い
# ============================================================
def fig2():
    """縦軸は積雪水量[mm]で統一する。

    原典（防災科研×新潟大の共同研究報告書）が標高別に載せているのは**積雪水量**であり、
    標高別の積雪深は載っていない。水量を密度で割って積雪深に直すこともできるが、
    実測密度 252/419/401 kg/m³ と標高1,500/1,600/1,700m の対応順が原典で確認できて
    いないため、その換算はしない（順を取り違えると点が上下に大きく動く）。
    設問②の本文も「積雪水量」で書いてあるので、本文と図の量をここで一致させる。

    計画側（回帰式・火口の想定値）は積雪深なので、密度350 kg/m³ で水量に換算する。
    350は蔵王計画と報告書がともに使っている一律値（8.5節）。線形変換なので図の形は
    変わらず、計画の土俵の上で比較していることになる。
    """
    RHO = 350.0    # kg/m³。計画・報告書がともに使う一律値。1m の雪 = 350mm の水

    # 蔵王計画 図2-21 の6観測所（標高m, 年最大積雪深cm）。8.5節で numpy.polyfit により
    # 回帰係数 y=0.2139x+8.5516（R²=0.767）を再現済み
    st = np.array([[38.9, 17], [86, 18], [152.5, 50], [245, 92], [265, 34], [525, 121]])
    a, b = 0.2139, 8.5516

    # 防災科研×新潟大の現地測量（2023年3月9日）。標高別の積雪水量[mm]＝原典の実測値そのもの
    uav = np.array([[1500, 550], [1600, 390], [1700, 106]])
    basin_mean = 1.10 * RHO        # 流域平均積雪深1.10m（面積0.271km²）→ 385mm
    plan_at_crater = 3.81 * RHO    # 計画の火口高度の想定積雪深3.81m → 1,334mm

    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    x = np.linspace(0, 1850, 200)
    # 回帰の範囲内は実線、その外（外挿）は破線。実線を全域に引くと破線が隠れる
    inr, out = x <= 525, x >= 525
    ax.plot(x[inr], (a * x[inr] + b) / 100.0 * RHO, color=BASE, lw=2.2, zorder=3,
            label="計画の回帰式（6観測所の年最大から）")
    ax.plot(x[out], (a * x[out] + b) / 100.0 * RHO, color=BASE, lw=2.0,
            ls=(0, (6, 3)), zorder=3, label="同・火口高度への外挿")
    ax.axvspan(525, 1850, color=BASE, alpha=0.055, zorder=0)
    ax.text(1190, 95, "回帰に使った観測所より上\n（約1,220mの外挿）",
            ha="center", fontsize=9, color=BASE)

    ax.scatter(st[:, 0], st[:, 1] / 100.0 * RHO, s=52, color=BASE, zorder=5,
               label="回帰に使った気象庁6観測所の年最大（38.9〜525m）")
    ax.scatter(uav[:, 0], uav[:, 1], s=95, marker="D", color=ACCENT, zorder=6,
               label="火口高度の現地測量（2023年3月9日・標高別）")
    ax.scatter([1650], [basin_mean], s=150, marker="*", color=ACCENT, zorder=6,
               edgecolor="white", linewidth=0.8, label="同・流域平均（0.271km²）")
    ax.scatter([1750], [plan_at_crater], s=110, marker="s", color=BASE, zorder=6,
               facecolor="white", linewidth=2.0, label="計画が採った火口高度の想定")

    # 食い違いを縦の矢印で示す
    ax.annotate("", xy=(1750, plan_at_crater), xytext=(1750, basin_mean),
                arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=1.8), zorder=7)
    ax.text(1735, (plan_at_crater + basin_mean) / 2, "実測は計画値の\n約29%",
            ha="right", va="center", fontsize=10.5, color=ACCENT, fontweight="bold")

    # 実測の傾きが逆であることを示す補助線
    ax.plot(uav[:, 0], uav[:, 1], color=ACCENT, lw=1.4, ls=":", zorder=5)
    ax.text(1600, 355, "標高が上がるほど減る\n（強風と疎林化）", ha="center", va="top",
            fontsize=9.2, color=ACCENT)

    ax.text(1880, 18, "計画側は密度350 kg/m³ で水量に換算（計画・報告書が使う一律値）",
            fontsize=8.4, color=MUTED, ha="right", va="bottom")

    # 軸ラベルに「年最大」は付けない——青系列は年最大積雪深からの換算だが、赤系列は
    # 2023年3月9日の単日測量であり、1本のラベルで両方を限定できない。限定は凡例側に置く
    ax.set_xlabel("標高 [m]"); ax.set_ylabel("積雪水量 [mm]")
    ax.set_xlim(-60, 1900); ax.set_ylim(0, 1540)
    ax.grid(alpha=0.25, lw=0.6)
    ax.legend(loc="upper left", fontsize=8.6, framealpha=0.95)
    ax.set_title("外挿の先に実測があり、直線から外れている", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(_OUT, "t2_fig2_extrapolation.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# 図3 消雪日を特定できる年数の実測（8火山・カタログ集計）
# ============================================================
def fig3():
    # 8.6節の実測（±10日精度で使える年数、中位推定／悲観推定、1984〜2026の43年中）
    vol = ["樽前山", "鳥海山", "磐梯山", "富士山", "草津白根山", "浅間山", "蔵王山", "十勝岳"]
    eras = ["1984-98\nLandsat 5単独", "1999-2012\n+Landsat 7",
            "2013-16\n+Landsat 8", "2017-26\n+Sentinel-2"]
    mid = np.array([[10, 14, 4, 10], [8, 14, 4, 10], [4, 14, 4, 10], [4, 12, 3, 10],
                    [2, 12, 3, 10], [2, 12, 2, 10], [3, 8, 4, 10], [2, 8, 3, 10]])
    pess = np.array([23, 26, 20, 22, 17, 17, 15, 15])   # 悲観推定の合計

    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    y = np.arange(len(vol))
    left = np.zeros(len(vol))
    shades = ["#cfe0ef", "#9dc0dd", "#5b93c4", "#2c5f8d"]
    for j, e in enumerate(eras):
        ax.barh(y, mid[:, j], left=left, height=0.62, color=shades[j],
                edgecolor="white", linewidth=0.8, label=e, zorder=3)
        left = left + mid[:, j]

    ax.scatter(pess, y, marker="|", s=420, color=ACCENT, linewidth=2.4, zorder=5,
               label="悲観推定（雲量30%未満のみ採用）")

    # 注記は棒の上の余白に置く（棒や凡例と重ねない）
    for xv, lab in [(10, "2年超過確率\nに必要"), (20, "10年超過確率\nに必要")]:
        ax.axvline(xv, color=INK, ls="--", lw=1.1, zorder=4)
        ax.text(xv + 0.4, -1.05, lab, fontsize=8.8, va="center")

    ax.axvline(43, color=MUTED, ls=":", lw=1.4, zorder=4)
    ax.text(42.4, -1.05, "アーカイブの天井 43年\n（100年確率は外挿）", fontsize=8.8,
            ha="right", va="center", color=MUTED)

    ax.set_yticks(y); ax.set_yticklabels(vol)
    ax.set_ylim(len(vol) - 0.4, -1.7)   # 反転しつつ上に注記用の余白を確保
    ax.set_xlabel("消雪日を ±10日 で特定できる年数（1984〜2026年の43融雪期中）")
    ax.set_xlim(0, 46)
    ax.grid(axis="x", alpha=0.25, lw=0.6, zorder=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.135), fontsize=8.4,
              ncol=5, framealpha=0.95, columnspacing=1.1, handlelength=1.4)
    # 見出しは中位推定に対する結論であることを明示する。悲観推定では4火山が20年を割るので、
    # 無条件の断定にすると同じ図の赤マーカーと食い違って見える
    ax.set_title("中位推定なら2年・10年超過確率に足りる。100年確率は外挿になる",
                 fontsize=12.0, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(_OUT, "t2_fig3_years.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


# ============================================================
# 図4 想定ユーザー、予算の所在、事業化の二段階
# ============================================================
def fig4():
    fig, ax = plt.subplots(figsize=(9.4, 5.2))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    _box(ax, 0.03, 0.63, 0.30, 0.24,
         "想定ユーザー\n\n地方整備局 砂防事務所\n都道府県 砂防部局",
         fs=9.8, ec=BASE, lw=1.6)
    ax.text(0.18, 0.585, "緊急減災対策砂防計画の対象 29火山\nうち積雪火山 21座",
            ha="center", va="top", fontsize=8.8, color=MUTED, linespacing=1.4)

    _box(ax, 0.375, 0.63, 0.30, 0.24,
         "予算の所在\n\n火山地域における\n土砂災害対策",
         fs=9.8, ec=BASE, lw=1.6)
    ax.text(0.525, 0.585, "同じ事業内容の行に\n「計画の改定」と「リアルタイム\nハザードマップの運用・整備」が並ぶ",
            ha="center", va="top", fontsize=8.8, color=MUTED, linespacing=1.4)

    # 「発注予定」と書くと提出日には陳腐化する（公告は令和8年5月予定）。出典の性格＝
    # 公表された発注の見通し、に主語を寄せて時制を持たせない
    _box(ax, 0.72, 0.63, 0.25, 0.24,
         "需要は表に出ている\n\n那須岳で衛星による積雪深推定の\n検討が発注見通しに載る",
         fs=9.0, ec=ACCENT, lw=1.6, fc="#fdf0ee")
    ax.text(0.845, 0.585, "積雪計5基がある事務所が\n面的な推定を求めている",
            ha="center", va="top", fontsize=8.8, color=ACCENT, linespacing=1.4)

    _arrow(ax, 0.335, 0.75, 0.373, 0.75)
    _arrow(ax, 0.68, 0.75, 0.718, 0.75)

    # 二段階
    _box(ax, 0.06, 0.16, 0.38, 0.22,
         "第1段階  2027年度\n\n計画・ハザードマップの改定に伴う\n検討業務への技術提供\n（建設コンサルタント等との共同提案）",
         fs=9.2, ec=BASE, lw=1.6)
    _box(ax, 0.56, 0.16, 0.38, 0.22,
         "第2段階  2028年度以降\n\n積雪火山 21座への年次提供\nリアルタイムハザードマップへ接続",
         fs=9.2, ec=BASE, lw=1.6, fc="#eef4fa")
    _arrow(ax, 0.45, 0.27, 0.55, 0.27, lw=2.0)

    ax.text(0.5, 0.075, "本提案が担うのは当年値ではなく、当年値では作れない多年の年超過確率分布である",
            ha="center", fontsize=9.6, color=ACCENT, fontweight="bold")

    ax.text(0.5, 0.955, "誰に、どの予算で、いつ売るか", ha="center",
            fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(_OUT, "t2_fig4_business.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4()
    for f in sorted(os.listdir(_OUT)):
        p = os.path.join(_OUT, f)
        print(f"  {f}  ({os.path.getsize(p)/1024:.0f} KB)")
