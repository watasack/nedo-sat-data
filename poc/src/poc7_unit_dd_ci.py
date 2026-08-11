"""PoC-7: 提出物の見出し数値「二重差分 AUC 0.92」を区間つきで測り直し、
        PoC-2 が模擬していなかった「兄弟資産間の放射率の差動経年」を実装する

## なぜこれが最優先か

`12_提出版_様式4.md` 設問④が引用しているPoC由来の数値のうち、**判別性能を主張しているのは
「ユニット面的劣化+1Kの判別AUCは静的比較0.54に対し二重差分0.92」の1行だけ**である。
つまりこの提案の技術的成立性の主張は、この1つの数字に乗っている。

その数字には2つの問題があった（2026年8月11日の追跡監査で判明）。

### 問題1: 標本が24対24しかない（型D-1）

`poc2_scene_sim.py` の (2) は `N_TRIALS = 6`、ユニット対8組のうち劣化は
`range(0,8,2)` の4組。したがって **1つのAUCは 4×6=24 個の陽性と24個の陰性から出ている。**
AUC 0.92 での標準誤差は 0.05 級である。**0.92 は点推定であって、区間が付いていない。**

同じ型の誤りで、PoC-2 のタンクパッチ +3K/100m² の公表値は試行を12回に増やすと
再現しなかった（0.88 → 0.730 [0.679, 0.777]。PoC-5b）。**同じ検査を提出物の数値に当てる。**

### 問題2: 差動経年が模擬されていない（型C-2）

`Scene.__init__` は資産ごとに ε を1回引いて固定し、`observe()` は ε を触らない。
つまり **前期6エポックと後期6エポックで兄弟資産のεは完全に同一**である。
実際には外装の風化・汚損は資産ごとに違う速さで進むので、兄弟間のε差は時間とともに開く。

PoC-5 はこの項を解析側の雑音モデルに 0.3K（輝度温度）として入れており、
**入れると +1K・6エポックの解析AUCは 0.939 → 0.834 に下がる**と予測した。
ここでは**シミュレータ側に実装して、その予測が当たるかを確かめる**。

実装のしかた: 後期の観測前に、各ユニット部材の配管ラック画素の ε を
独立に N(0, δε) で摂動する。δε は「兄弟差の見かけ温度変化のσ」が目標値になるよう決める。
PoC-1 (B) の実測で Δε=0.05 → 1.9K なので、1K あたり Δε≈0.0263。
兄弟差は独立な2つの摂動の差なので σ_diff = √2 · δTb なので δTb = target/√2。

## 出力

`poc/out/poc7_results.json`（所要 約23分）

**評価条件は PoC-2 と同一**（変化点既知の前後6エポック分割・トリム平均集約）なので、
公表値と直接比較できる。楽観条件そのものは変えていない。
"""
import json
import os
import time

import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(_here, "poc2_scene_sim.py")).read().split("results = {}")[0])

BANDS = {"A_仮定_3.4-4.2um": (3.4, 4.2), "B_実帯域_3.7-4.95um": (3.7, 4.95)}


def set_band(lo, hi, n=41):
    global LAM, _T_lut, _L_lut
    LAM = np.linspace(lo, hi, n)
    _T_lut = np.linspace(200, 400, 2001)
    _L_lut = planck_band_arr(_T_lut)


# Δε → 見かけ温度の換算（PoC-1 (B) の風化アルミ: Δε=0.05 で 1.9K）
DEPS_PER_K = 0.05 / 1.9
AGING_LEVELS = [0.0, 0.15, 0.3, 0.5]     # 兄弟差の差動経年 [K, 輝度温度]
DTS = [0.5, 1.0, 2.0]
N_TRIALS = 40
N_EP = 6
N_BOOT = 2000


def bootstrap_auc(pos, neg, rng_b, n=N_BOOT):
    pos, neg = np.asarray(pos), np.asarray(neg)
    out = []
    for _ in range(n):
        p = pos[rng_b.integers(0, pos.size, pos.size)]
        q = neg[rng_b.integers(0, neg.size, neg.size)]
        out.append(auc(p, q))
    return float(np.percentile(out, 5)), float(np.percentile(out, 95))


def pair_diff(img, pair):
    return unit_mean(img, pair[0]) - unit_mean(img, pair[1])


def run(band_name, n_trials=N_TRIALS):
    lo, hi = BANDS[band_name]
    set_band(lo, hi)
    # dT × aging ごとに (静的スコア, 二重差分スコア) を溜める
    acc = {(dt, ag): dict(sp=[], sn=[], dp=[], dn=[]) for dt in DTS for ag in AGING_LEVELS}
    for dt_i, dt in enumerate(DTS):
        for t in range(n_trials):
            globals()["rng"] = np.random.default_rng(50000 + dt_i * 1000 + t)
            sc = Scene()
            eps0 = sc.eps.copy()
            deg_pairs = set(range(0, 8, 2))
            # 前期（劣化なし・経年なし）
            pre = [observe(sc) for _ in range(N_EP)]
            d_pre = [np.mean([pair_diff(im, p) for im in pre]) for p in sc.units]
            # 劣化を注入（1回だけ）
            for i in deg_pairs:
                sc.add_unit_diffuse(i, 0, dt)
            for ag in AGING_LEVELS:
                # 差動経年: 各部材のラック画素のεを独立に摂動する
                sc.eps = eps0.copy()
                if ag > 0:
                    d_tb = ag / np.sqrt(2.0)          # 兄弟差のσを ag にするための片側
                    for pair in sc.units:
                        for u in pair:
                            sl = np.s_[u["y0"]:u["y0"] + u["h"], u["x0"]:u["x0"] + u["w"]]
                            rack = sc.eps[sl] < 0.5   # ラック（低ε）だけが外装
                            de = float(rng.normal(0, d_tb * DEPS_PER_K))
                            blk = sc.eps[sl]
                            blk[rack] = np.clip(blk[rack] + de, 0.05, 0.6)
                            sc.eps[sl] = blk
                post = [observe(sc) for _ in range(N_EP)]
                for i, p in enumerate(sc.units):
                    dp = np.mean([pair_diff(im, p) for im in post])
                    a = acc[(dt, ag)]
                    (a["sp"] if i in deg_pairs else a["sn"]).append(dp)
                    (a["dp"] if i in deg_pairs else a["dn"]).append(dp - d_pre[i])
        print(f"  [{band_name}] dT={dt}K 完了 ({time.time()-T0:.0f}s)")
    rng_b = np.random.default_rng(4242)
    out = {}
    for dt in DTS:
        row = {}
        for ag in AGING_LEVELS:
            a = acc[(dt, ag)]
            s_auc = float(auc(a["sp"], a["sn"]))
            d_auc = float(auc(a["dp"], a["dn"]))
            slo, shi = bootstrap_auc(a["sp"], a["sn"], rng_b)
            dlo, dhi = bootstrap_auc(a["dp"], a["dn"], rng_b)
            row[f"差動経年={ag}K"] = dict(
                静的兄弟差分AUC=round(s_auc, 3), 静的90CI=[round(slo, 3), round(shi, 3)],
                二重差分AUC=round(d_auc, 3), 二重差分90CI=[round(dlo, 3), round(dhi, 3)],
                標本数=[len(a["dp"]), len(a["dn"])])
        out[f"+{dt}K"] = row
    return out


T0 = time.time()
results = {"meta": dict(
    試行回数=N_TRIALS, エポック数_前期後期=N_EP, 標本数の内訳=f"劣化4対×{N_TRIALS}試行",
    PoC2の試行回数=6, PoC2の標本数="24対24",
    差動経年の実装="後期の観測前に各部材のラック画素のεを独立にN(0,δε)で摂動。δε=(ag/√2)×0.05/1.9",
    評価条件="PoC-2と同一（変化点既知の前後分割・トリム平均集約）",
    ブートストラップ反復=N_BOOT,
    seed規則="dT・試行ごとに default_rng(50000+dt_i*1000+t)")}

print("=== PoC-7: 提出物の 0.92 を区間つきで測り直す ===")
for b in BANDS:
    results[b] = run(b)

# ---- 公表値との比較（仮定帯域・差動経年なしが PoC-2 の条件）----
PUB = {"+0.5K": dict(static=0.44, dd=0.86),
       "+1.0K": dict(static=0.54, dd=0.92),
       "+2.0K": dict(static=0.69, dd=0.997)}
ref = results["A_仮定_3.4-4.2um"]
cmp_ = {}
for k, pv in PUB.items():
    got = ref[k]["差動経年=0.0K"]
    lo, hi = got["二重差分90CI"]
    cmp_[k] = dict(
        公表_静的=pv["static"], 本PoC_静的=got["静的兄弟差分AUC"], 静的90CI=got["静的90CI"],
        公表_二重差分=pv["dd"], 本PoC_二重差分=got["二重差分AUC"], 二重差分90CI=got["二重差分90CI"],
        公表値は区間内か=bool(lo <= pv["dd"] <= hi))
results["comparison_with_published"] = dict(
    比較=cmp_,
    注=("PoC-2 は N_TRIALS=6（24対24）、本PoCは40（160対160）。乱数列も違うので"
        "完全一致はしない。見るのは**公表値が本PoCの90%区間に入るか**である"))

# ---- PoC-5 の解析予測との突き合わせ ----
ANALYTIC = {"+0.5K": dict(no_aging=0.780, aging03=0.686),
            "+1.0K": dict(no_aging=0.939, aging03=0.834),
            "+2.0K": dict(no_aging=0.999, aging03=0.974)}
pred = {}
for k, av in ANALYTIC.items():
    g0 = ref[k]["差動経年=0.0K"]["二重差分AUC"]
    g3 = ref[k]["差動経年=0.3K"]["二重差分AUC"]
    pred[k] = dict(
        経年なし_解析=av["no_aging"], 経年なし_MC=g0, 差=round(g0 - av["no_aging"], 3),
        経年0_3K_解析=av["aging03"], 経年0_3K_MC=g3, 差_=round(g3 - av["aging03"], 3),
        MCでの低下=round(g0 - g3, 3),
        解析での低下=round(av["no_aging"] - av["aging03"], 3))
results["vs_poc5_analytic"] = dict(
    比較=pred,
    問い="PoC-5 が解析で予測した『差動経年0.3Kを入れると0.92→0.83』はMCで再現するか")

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "poc7_results.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------------- 出力 ----------------
print("\n=== 公表値との比較（仮定帯域・差動経年なし）===")
for k, v in cmp_.items():
    print(f"  {k}: 静的 公表{v['公表_静的']} vs 本PoC {v['本PoC_静的']} {v['静的90CI']}")
    print(f"        二重差分 公表{v['公表_二重差分']} vs 本PoC {v['本PoC_二重差分']} "
          f"{v['二重差分90CI']} → 公表値は区間内か: {v['公表値は区間内か']}")

print("\n=== 差動経年を入れたとき（仮定帯域・二重差分AUC）===")
print("      劣化量 " + "".join(f"{ag}K".rjust(10) for ag in AGING_LEVELS))
for k in PUB:
    print(f"  {k:>10} " + "".join(
        f"{ref[k][f'差動経年={ag}K']['二重差分AUC']:>10.3f}" for ag in AGING_LEVELS))

print("\n=== PoC-5 の解析予測は当たったか ===")
for k, v in pred.items():
    print(f"  {k}: 経年なし 解析{v['経年なし_解析']} / MC {v['経年なし_MC']}（差{v['差']:+.3f}）")
    print(f"        経年0.3K 解析{v['経年0_3K_解析']} / MC {v['経年0_3K_MC']}（差{v['差_']:+.3f}）"
          f"  低下幅 解析{v['解析での低下']:.3f} / MC {v['MCでの低下']:.3f}")

print("\n=== 帯域の効果（差動経年なし・二重差分AUC）===")
for k in PUB:
    a = results["A_仮定_3.4-4.2um"][k]["差動経年=0.0K"]["二重差分AUC"]
    b = results["B_実帯域_3.7-4.95um"][k]["差動経年=0.0K"]["二重差分AUC"]
    print(f"  {k}: 仮定帯域 {a:.3f} → 実帯域 {b:.3f}（{b-a:+.3f}）")
print(f"\n所要 {time.time()-T0:.0f} 秒 → poc/out/poc7_results.json")
