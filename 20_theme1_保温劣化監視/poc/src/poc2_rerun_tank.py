"""修正版tank_score（3px侵食）でタンクパッチAUCを再計算し、poc2_results.jsonを更新
注意: 本スクリプトのグリッド(A=100/200/400)はpoc2_scene_sim本体(A=50/100/200)と異なる。
現行poc2_results.jsonのtank_patch_aucは本スクリプト由来（再実行順序はCLAUDE.md参照）。"""
import numpy as np, json, os
_here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(_here, 'poc2_scene_sim.py')).read().split('results = {}')[0])

N_TRIALS = 6
grid = [(dT, A) for dT in (2.0, 3.0, 5.0) for A in (100, 200, 400)]
tank_auc, excluded = {}, 0
for dT, A in grid:
    pos, neg = [], []
    for t in range(N_TRIALS):
        sc = Scene()
        deg = list(range(0, 24, 2))
        for i in deg: sc.add_tank_patch(sc.tanks[i], dT, A)
        img = observe(sc)
        for i, tk in enumerate(sc.tanks):
            s = tank_score(img, tk)
            if np.isnan(s): excluded += 1; continue
            (pos if i in deg else neg).append(s)
    tank_auc[f"dT={dT}K,A={A}m2"] = float(auc(pos, neg))
    print(f"dT={dT} A={A}: AUC={tank_auc[f'dT={dT}K,A={A}m2']:.3f} (n_pos={len(pos)}, n_neg={len(neg)})")

_json_path = os.path.join(POC_OUT, 'poc2_results.json')
r = json.load(open(_json_path))
r["tank_patch_auc"] = tank_auc
r["tank_note"] = ("3px侵食版。小型タンク(概ねD<25m)は可視面不足で監視対象外として除外。"
                  f"除外率={excluded/(N_TRIALS*24*len(grid)):.0%}。"
                  "低ε屋根は天空反射で地面より低輝度となり境界混合画素が±10K級の縁勾配を作るため、"
                  "深い侵食が必須（実データでも資産マスク設計の要点）")
json.dump(r, open(_json_path, 'w'), ensure_ascii=False, indent=1)
print("updated")
