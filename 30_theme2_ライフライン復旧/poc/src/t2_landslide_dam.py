"""河道閉塞（天然ダム）の湛水量と越流猶予時間は、衛星＋DEMで判断に足る精度が出るか

候補案:
  Sentinel-1/2 で湛水面の平面形（面積）を測り、国土地理院DEMから作った
  容積曲線 V(h) で体積に変換し、満水までの残容量 ÷ 流入量 = 越流猶予時間 を出す。
  「有無・位置」は林野庁のSAR判読ガイドブックで既にマニュアル化されているが、
  「量と時間」は誰も面的に出していない。

この案の生死は2点に集約される。両方をここで潰す。

  【型②】面積の観測誤差が体積誤差に何倍で効くか。
          谷地形は V ∝ h^2 級なので誤差が増幅される。
  【型⑤】越流猶予時間の誤差の主因は、体積なのか流入量なのか。
          流入量が主因なら、体積をどれだけ精密に測っても猶予時間は当たらない
          （災害廃棄物案が「解体率が主因」で死んだのと同じ型）。

出力: theme2_ライフライン復旧/poc/out/t2_landslide_dam.json
"""
import json
import os

import numpy as np

# ---- 実在した天然ダムの規模（一次資料での裏取りは要。ここは桁の確認用）----
# 湛水面積 A [m2] と 湛水量 V [m3] の組。平均水深 h_mean = V/A も併記する。
CASES = {
    "小規模（渓流・湛水量10万m3級）": dict(A=2.0e4, V=1.0e5),
    "中規模（湛水量50万m3級）": dict(A=6.0e4, V=5.0e5),
    "大規模（紀伊半島型・湛水量数百万m3）": dict(A=3.0e5, V=5.0e6),
}

# ---- 谷の断面形。V ∝ h^p、A ∝ h^(p-1) ----
# p=2: V字谷（断面三角形・prismatic）  p=3: すり鉢状  p=1.5: 幅の広い谷底
P_EXP = {"V字谷 (p=2)": 2.0, "幅の広い谷底 (p=1.5)": 1.5, "すり鉢状 (p=3)": 3.0}


def volume_from_area(A, A0, V0, p):
    """基準 (A0,V0) を通る V ∝ A^{p/(p-1)} の関係。A∝h^{p-1}, V∝h^p より"""
    return V0 * (A / A0) ** (p / (p - 1.0))


def rel_dV_from_dA(p):
    """面積の相対誤差 1 に対する体積の相対誤差の倍率 = p/(p-1)"""
    return p / (p - 1.0)


results = {}

# ===== 1. 面積の観測誤差 =====
# 水域マスクの境界は概ね1画素ぶんずれる。面積誤差 ≒ 周長 × 画素サイズ × バイアス係数。
# 谷の湛水池は細長いので、周長は等価円の 1.5〜2.5 倍を見込む（elongation factor）。
SENSORS = {"Sentinel-2 (10m)": 10.0, "Sentinel-1 IW GRD (20m)": 20.0, "Landsat (30m)": 30.0}
ELONG = 2.0        # 等価円周長に対する実周長の倍率（細長い谷の湛水池）
BIAS_PIX = 0.5     # 系統的な過大/過小推定（画素の半分。ランダム誤差は平均化されるが系統誤差は残る）

area_err = {}
for cname, c in CASES.items():
    A = c["A"]
    P_circle = 2.0 * np.sqrt(np.pi * A)
    P = ELONG * P_circle
    row = {}
    for sname, px in SENSORS.items():
        dA = P * px * BIAS_PIX
        row[sname] = dict(周長_m=round(P), 面積誤差_m2=round(dA),
                          面積相対誤差_pct=round(100 * dA / A, 1))
    area_err[cname] = row
results["area_error"] = area_err

# ===== 2. 面積誤差 → 体積誤差（型②の判定）=====
vol_err = {}
for pname, p in P_EXP.items():
    amp = rel_dV_from_dA(p)
    row = {"増幅率_dV/V ÷ dA/A": round(amp, 2)}
    for cname, c in CASES.items():
        sub = {}
        for sname in SENSORS:
            ra = area_err[cname][sname]["面積相対誤差_pct"]
            sub[sname] = round(ra * amp, 1)
        row[cname] = sub
    vol_err[pname] = row
results["volume_error_pct"] = vol_err

# ===== 3. 越流猶予時間の誤差分解（型⑤の判定）=====
# 猶予時間 T = (V_full - V_now) / Q_in
# 相対誤差: (dT/T)^2 = (d(残容量)/残容量)^2 + (dQ/Q)^2
#
# 流入量 Q の不確かさ:
#   (a) 流域面積 × 降雨 × 流出率 で推定する場合。山地の未観測流域では
#       GSMaP の降雨誤差が 30-50%、流出率の不確かさが 20-40% → RSS で 40-65%
#   (b) 衛星の水面積の時系列差から dV/dt を直接読む場合。
#       ただし Sentinel-1 は6日、Sentinel-2 は5日回帰。湛水が数時間〜数日で進むなら間に合わない
Q_UNCERT = {
    "降雨×流出率から推定（未観測山地流域）": 0.50,
    "同上・条件が良い場合": 0.35,
    "衛星の水面積時系列から dV/dt を直読（再訪5-6日）": 0.20,
}
# 残容量の相対誤差は、満水容積と現容積の差なので、両者の誤差が効く。
# ここでは体積相対誤差をそのまま残容量にも当てる（保守的）。
timing = {}
for pname, p in P_EXP.items():
    amp = rel_dV_from_dA(p)
    for cname in CASES:
        rv = area_err[cname]["Sentinel-1 IW GRD (20m)"]["面積相対誤差_pct"] * amp / 100.0
        row = {}
        for qname, rq in Q_UNCERT.items():
            rt = float(np.sqrt(rv**2 + rq**2))
            dominant = "体積" if rv > rq else "流入量"
            row[qname] = dict(猶予時間の相対誤差_pct=round(100 * rt, 1),
                              誤差の主因=dominant,
                              体積の寄与_pct=round(100 * rv, 1),
                              流入量の寄与_pct=round(100 * rq, 1))
        timing[f"{pname} / {cname}"] = row
results["timing_error"] = timing

# ===== 4. 判断に必要な精度から逆算 =====
# 下流の避難判断で意味を持つのは「あと何時間か」の桁。
# 猶予が12時間なのか48時間なのかが分かれば行動が変わるが、
# 24時間 ±50% (12-36h) では避難のリードタイム(数時間〜半日)に対して辛うじて使える。
# 一方 ±100% を超えると「桁も言えない」。
VERDICT_THRESH = {"使える": 0.35, "限界域": 0.70}
verdict = {}
for k, row in timing.items():
    sub = {}
    for qname, v in row.items():
        r = v["猶予時間の相対誤差_pct"] / 100.0
        sub[qname] = ("使える" if r <= VERDICT_THRESH["使える"]
                      else "限界域" if r <= VERDICT_THRESH["限界域"] else "不可")
    verdict[k] = sub
results["verdict"] = verdict

# ===== 5. 観測頻度の壁 =====
# 湛水の進行が速いと、再訪間隔の間に越流してしまう。
# 満水までの時間 = 満水容積 / 流入量。流入量は流域面積×降雨強度×流出率。
CATCHMENT_KM2 = [5.0, 20.0, 100.0]
RAIN_MM_H = [10.0, 30.0, 60.0]
RUNOFF = 0.6
fill = {}
for cname, c in CASES.items():
    row = {}
    for ck in CATCHMENT_KM2:
        for r in RAIN_MM_H:
            Q = ck * 1e6 * (r / 1000.0) / 3600.0 * RUNOFF   # m3/s
            t_h = c["V"] / Q / 3600.0
            row[f"流域{ck:.0f}km2 × 雨{r:.0f}mm/h"] = round(t_h, 1)
    fill[cname] = row
results["fill_time_hours"] = fill

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
os.makedirs(_OUT, exist_ok=True)
with open(os.path.join(_OUT, "t2_landslide_dam.json"), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1, default=float)

# ---------- 出力 ----------
print("=== 1. 水域マスクの面積誤差（境界が画素の半分ずれる系統誤差）===")
for cname, row in area_err.items():
    print(f"  {cname}  (面積 {CASES[cname]['A']:.0f} m2, 湛水量 {CASES[cname]['V']:.0f} m3, "
          f"平均水深 {CASES[cname]['V']/CASES[cname]['A']:.1f} m)")
    for sname, v in row.items():
        print(f"      {sname}: 周長{v['周長_m']}m → 面積誤差 {v['面積相対誤差_pct']}%")

print("\n=== 2. 面積誤差 → 体積誤差（型②）===")
for pname, row in vol_err.items():
    print(f"  {pname}  増幅率 ×{row['増幅率_dV/V ÷ dA/A']}")
    for cname in CASES:
        s = row[cname]
        print(f"      {cname}: " + ", ".join(f"{k.split(' ')[0]}={v}%" for k, v in s.items()))

print("\n=== 3. 越流猶予時間の誤差分解（型⑤）===")
for k, row in timing.items():
    print(f"  {k}")
    for qname, v in row.items():
        print(f"      {qname}: 全体{v['猶予時間の相対誤差_pct']}% "
              f"（体積{v['体積の寄与_pct']}% / 流入量{v['流入量の寄与_pct']}%）→ 主因は{v['誤差の主因']}")

print("\n=== 4. 判定 ===")
for k, row in verdict.items():
    print(f"  {k}: " + ", ".join(f"{q.split('（')[0]}→{v}" for q, v in row.items()))

print("\n=== 5. 満水までの時間 [h]（再訪5-6日＝120-144h と比較すること）===")
for cname, row in fill.items():
    print(f"  {cname}")
    for k, v in row.items():
        mark = "  ← 再訪より速い" if v < 120 else ""
        print(f"      {k}: {v} h{mark}")
