"""PoC-5b: タンクパッチ検知器v2を、NEdTと帯域を振ってモンテカルロで回す

PoC-5 は SNR を解析式で出し、SNR→AUC を AUC=Phi(SNR/sqrt2) で写した。
この写像は**兄弟差分の時間変化では PoC-2 のMCと 0.02 以内で一致するが、
タンクパッチでは大きく過大に出る**（単発 解析0.89 対 MC実測0.64）。
理由は、二重差分が「場所が既知の1つの検定」である一方、タンクパッチ検知は
**パッチ位置が未知でPSF整合フィルタの最大値を取る＝多重比較**だからである。
最大値統計は平均より裾が重く、解析写像はそこを写せない。

したがってタンクパッチの「NEdTが何Kなら何エポック要るか」は、
**解析式ではなく検知器そのものを回して**出さなければならない。ここでやるのはそれである。

`poc2_scene_sim.py` の `observe()` は nedt を引数に持ち、雑音を
`rng.normal(0, nedt*dL300)` で放射輝度領域に注入している（dL300 = dB/dT|300K）。
つまり**この実装の nedt は最初から300K規定**であり、PoC-2 側は一貫していた。
不整合があったのは PoC-1 の側である（PoC-5 の 2b 節）。

帯域も振る。`LAM` を差し替えて放射輝度LUTを作り直せば、同じ検知器を
仮定帯域 3.4-4.2um と HotSat-2 実帯域 3.7-4.95um の両方で回せる。

**評価条件は PoC-2 と同じ楽観条件のまま**である（可視面内・持続パッチ・
パッチは侵食後マスク内）。ここで変えたのは NEdT と帯域とエポック数だけなので、
PoC-2 の公表値と直接比較できる。楽観条件そのものの影響は PoC-6 で扱う。

出力: poc/out/poc5b_results.json（所要 約8〜12分）
"""
import json
import os
import time

import numpy as np
from scipy.ndimage import gaussian_filter

_here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(_here, "poc2_scene_sim.py")).read().split("results = {}")[0])

BANDS = {
    "A_仮定_3.4-4.2um": (3.4, 4.2),
    "B_実帯域_3.7-4.95um": (3.7, 4.95),
}


def set_band(lo, hi, n=41):
    """LAM を差し替え、輝度→温度LUTと dL300 を作り直す"""
    global LAM, _T_lut, _L_lut, dL300
    LAM = np.linspace(lo, hi, n)
    _T_lut = np.linspace(200, 400, 2001)
    _L_lut = planck_band_arr(_T_lut)
    dL300 = (planck_band_arr(np.array([301.0]))
             - planck_band_arr(np.array([299.0])))[0] / 2
    return dL300


# ---- v2検知器（poc2_tank_v2.py と同一。importできないので写す） ----
def tank_resid_map(img, tank, erode_px=1.0, nbins=4):
    cy, cx = sat_coords(tank["cy"], tank["cx"])
    R = tank["R"] * GSD_TRUE / GSD_SAT
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    r = np.sqrt((yy - cy)**2 + (xx - cx)**2)
    m = r < (R - erode_px)
    if m.sum() < 12:
        return None, None
    v = img[m]
    rb = np.minimum((r[m] / (R - erode_px) * nbins).astype(int), nbins - 1)
    prof = np.full(nbins, np.nan)
    for b in range(nbins):
        sel = rb == b
        if sel.sum() >= 3:
            prof[b] = np.median(v[sel])
    ok = ~np.isnan(prof)
    if ok.sum() < 1:
        return None, None
    prof[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), prof[ok])
    Tmed = np.median(v)
    dLdT = (planck_band_arr(np.array([Tmed + 1.0]))
            - planck_band_arr(np.array([Tmed - 1.0])))[0] / 2
    out = np.zeros(img.shape, np.float32)
    out[m] = (v - prof[rb]) * (dLdT / dL300)
    return out, m


def tank_score_v2(resids, mask, sig=1.0, dmin=0.9):
    acc = np.mean(resids, axis=0)
    num = gaussian_filter(acc, sig)
    den = gaussian_filter(mask.astype(float), sig)
    mf = num / np.maximum(den, 1e-6)
    sel = mask & (den > dmin)
    if sel.sum() < 8:
        return np.nan
    mv = mf[sel]
    return float(np.max(mv) - np.median(mv))


N_TRIALS = 12
N_EP = 24                      # 月次2年分。1/3/6/12/18/24 で切って評価
EP_EVAL = (1, 3, 6, 12, 18, 24)
PATCHES = [(5.0, 100), (3.0, 100)]

# 走らせる組み合わせ: 実帯域は NEdT を全振り、仮定帯域は PoC-2 再現用に 1K のみ
CONFIGS = [("B_実帯域_3.7-4.95um", nd) for nd in (0.5, 1.0, 2.0, 3.0)] \
    + [("A_仮定_3.4-4.2um", 1.0)]

results = {"meta": dict(
    n_trials=N_TRIALS, n_epochs_generated=N_EP, epochs_evaluated=list(EP_EVAL),
    patches=[f"+{d}K/{a}m2" for d, a in PATCHES],
    detector="v2: 放射方向デトレンド(4ビン)+ノイズ等価輝度正規化+時系列残差スタック+PSF整合フィルタ(σ1px)",
    evaluation_conditions="PoC-2と同一の楽観条件（可視面内・持続パッチ・侵食後マスク内配置）",
    nedt_convention="observe()は rng.normal(0, nedt*dL300) で注入。nedtは300K規定",
    seed_rule="config毎に default_rng(1000+i) で貼り替え（再現可能）")}

boot_rng = np.random.default_rng(777)
t0 = time.time()
table = {}
for ci, (bname, nedt) in enumerate(CONFIGS):
    lo, hi = BANDS[bname]
    set_band(lo, hi)
    key = f"{bname} / NEdT={nedt}K"
    table[key] = {}
    for dT, A in PATCHES:
        globals()["rng"] = np.random.default_rng(1000 + ci * 10 + int(dT))
        scores = {n: ([], []) for n in EP_EVAL}
        excluded = 0
        for t in range(N_TRIALS):
            sc = Scene(tank_R_m=(20, 40))
            deg = set(range(0, 24, 2))
            for i in deg:
                sc.add_tank_patch(sc.tanks[i], dT, A, erode_sat_px=1.0)
            imgs = [observe(sc, nedt=nedt) for _ in range(N_EP)]
            for i, tk in enumerate(sc.tanks):
                maps, mask = [], None
                for img in imgs:
                    rm, mm = tank_resid_map(img, tk)
                    if rm is None:
                        break
                    maps.append(rm)
                    mask = mm
                if len(maps) < N_EP:
                    excluded += 1
                    continue
                for n in EP_EVAL:
                    s = tank_score_v2(maps[:n], mask)
                    if not np.isnan(s):
                        (scores[n][0] if i in deg else scores[n][1]).append(s)
        row = {}
        for n in EP_EVAL:
            pos, neg = np.array(scores[n][0]), np.array(scores[n][1])
            a = float(auc(pos, neg))
            # AUCの標本不確かさ。資産をブートストラップで引き直す
            bs = []
            for _ in range(400):
                p = pos[boot_rng.integers(0, pos.size, pos.size)]
                q = neg[boot_rng.integers(0, neg.size, neg.size)]
                bs.append(float(auc(p, q)))
            row[f"{n}ep"] = round(a, 3)
            row[f"{n}ep_90CI"] = [round(float(np.percentile(bs, 5)), 3),
                                  round(float(np.percentile(bs, 95)), 3)]
            row[f"{n}ep_n"] = [int(pos.size), int(neg.size)]
        row["除外率_可視面不足"] = round(excluded / (N_TRIALS * 24), 3)
        # AUC0.90 に到達するエポック数。点推定と、90%区間の下限が0.90を超える点の両方を出す
        hit = next((n for n in EP_EVAL if row[f"{n}ep"] >= 0.90), None)
        hit_lo = next((n for n in EP_EVAL if row[f"{n}ep_90CI"][0] >= 0.90), None)
        row["AUC0.90に到達した最小エポック"] = hit if hit else f">{max(EP_EVAL)}"
        row["AUC0.90を区間下限で超える最小エポック"] = hit_lo if hit_lo else f">{max(EP_EVAL)}"
        # AUCはエポックに対し単調増加すべき。逆転があれば標本不足の印なので記録する
        seq = [row[f"{n}ep"] for n in EP_EVAL]
        row["単調性の逆転回数"] = int(sum(1 for i in range(len(seq) - 1) if seq[i + 1] < seq[i]))
        table[key][f"+{dT}K/{A}m2"] = row
        print(f"[{time.time()-t0:6.0f}s] {key} +{dT}K/{A}m2: "
              + " ".join(f"{n}ep={row[f'{n}ep']:.3f}" for n in EP_EVAL)
              + f"  逆転{row['単調性の逆転回数']}回")
results["auc"] = table

# ---- PoC-2 公表値の再現確認（仮定帯域・NEdT=1K・12エポック） ----
PUB = {"+5.0K/100m2": {"1ep": 0.64, "6ep": 0.89, "12ep": 0.96},
       "+3.0K/100m2": {"1ep": 0.56, "6ep": 0.83, "12ep": 0.88}}
repro = {}
ref = table.get("A_仮定_3.4-4.2um / NEdT=1.0K", {})
for pk, pv in PUB.items():
    got = ref.get(pk, {})
    repro[pk] = {ep: dict(公表=v, 本PoC=got.get(ep), 差=(round(got[ep] - v, 3)
                                                        if got.get(ep) is not None else None))
                 for ep, v in pv.items()}
results["reproduction_of_poc2"] = dict(
    比較=repro,
    注="乱数列とエポック生成数(24)がPoC-2(12)と異なるため完全一致はしない。"
       "同じ水準に乗ることの確認が目的である")

# ---- 帯域の効果（NEdT=1Kでの実帯域 対 仮定帯域） ----
band_effect = {}
a = table.get("A_仮定_3.4-4.2um / NEdT=1.0K", {})
b = table.get("B_実帯域_3.7-4.95um / NEdT=1.0K", {})
for pk in a:
    band_effect[pk] = {ep: dict(仮定帯域=a[pk][ep], 実帯域=b[pk][ep],
                                差=round(b[pk][ep] - a[pk][ep], 3))
                       for ep in (f"{n}ep" for n in EP_EVAL)}
results["band_effect_at_nedt1K"] = band_effect

with open(os.path.join(POC_OUT, "poc5b_results.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

print(f"\n=== 帯域の効果（NEdT=1K）===")
for pk, row in band_effect.items():
    print(f"  {pk}: " + ", ".join(f"{ep} {v['仮定帯域']}→{v['実帯域']}({v['差']:+.3f})"
                                  for ep, v in row.items()))
print("\n=== NEdT掃引（実帯域）: AUC0.90に到達した最小エポック ===")
for key, row in table.items():
    if not key.startswith("B_"):
        continue
    print(f"  {key}: " + ", ".join(f"{pk}→{v['AUC0.90に到達した最小エポック']}"
                                   for pk, v in row.items()))
print(f"\n所要 {time.time()-t0:.0f} 秒 → poc/out/poc5b_results.json")
