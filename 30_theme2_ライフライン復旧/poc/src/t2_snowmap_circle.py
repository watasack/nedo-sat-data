#!/usr/bin/env python3
"""消雪日マップの集計範囲を「火口半径3 kmの円」に限って取り直す。

## なぜ要るか

`fetch_snowmap_poc.py` が作った `snow_doy_YYYY.npy` は **火口中心 ±3 km の矩形**
（203×202画素 × 30 m ＝ 6.09 × 6.06 km ＝ 41,006画素）である。
`t2_snowmap_results.json` の `pixels_total` が 41,006 であることがその証拠で、
**四隅は火口から 4.3 km ある**。ところが提案も資料も「火口半径3 km」と呼んでいた。

融雪型火山泥流は火口起源の現象なので、**火口から遠い四隅を混ぜると標高の低い側へ
系統的に引っ張られる**。実際、2022年の画素中央値は矩形 117 日目 → 円 144.5 日目で、
**9年で2番目に早い年が2番目に遅い年に入れ替わる**。

## ここでやること

既存の `.npy` に半径3 kmの円マスク（31,392画素）を掛けて、年ごとの
決定画素率・画素中央値・面積平均を取り直す。**新しい観測は要らない**——
矩形は円を含んでいるので、既存データの部分集合を取るだけである。

## 依存を持たない理由

この環境には numpy が入らない（pip がプロキシで 403）。他の t2_*.py は numpy を使うので
**この環境では再実行できない**。本スクリプトは素の Python だけで書いてあるので単体で走る。
`t2_meltout_accuracy.py` 側にも同じ円マスクを入れてあるが、**あちらの出力 JSON は
マスク導入前のもの**で、numpy のある環境で回し直すまで矩形基準のまま残る（下の
`downstream_effect` に、回し直したときに何がどれだけ動くかを書いてある）。

出力: poc/out/t2_snowmap_circle_r3km.json
"""
import ast, array, json, math, os, struct

_SRC = os.path.dirname(os.path.abspath(__file__))
_POC = os.path.dirname(_SRC)
_DATA = os.path.join(_POC, "data", "snowmap")
_OUT = os.path.join(_POC, "out")
YEARS = list(range(2017, 2026))
RADIUS_M = 3000.0
PIXEL_M = 30.0


def load_npy(path):
    with open(path, "rb") as f:
        assert f.read(6) == b"\x93NUMPY"
        maj, _ = f.read(2)
        n = 2 if maj == 1 else 4
        hlen = struct.unpack("<H" if maj == 1 else "<I", f.read(n))[0]
        hdr = ast.literal_eval(f.read(hlen).decode())
        rows, cols = hdr["shape"]
        a = array.array({"<f4": "f", "<f8": "d"}[hdr["descr"]])
        a.fromfile(f, rows * cols)
    return a, rows, cols


def circle_mask(rows, cols):
    """AOI は火口中心 ±3 km の矩形なので、円の中心は画像の中心・半径は画幅の半分。"""
    cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0
    r = RADIUS_M / PIXEL_M
    return [(i, ((i // cols) - cy) ** 2 + ((i % cols) - cx) ** 2 <= r * r)
            for i in range(rows * cols)]


def year_stats(y, inside_only):
    a, rows, cols = load_npy(os.path.join(_DATA, f"snow_doy_{y}.npy"))
    mask = circle_mask(rows, cols)
    vals, tot = [], 0
    for i, ins in mask:
        if inside_only and not ins:
            continue
        tot += 1
        v = a[i]
        if v == v:
            vals.append(v)
    vals.sort()
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return dict(母数画素=tot, 決定画素=n, 決定率=round(n / tot, 3),
                画素中央値=round(med, 1), 面積平均=round(sum(vals) / n, 1))


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def main():
    res = {"_what": "消雪日マップを火口半径3kmの円に限って集計し直したもの（矩形との対比つき）",
           "定義": {"円": f"火口中心から半径 {RADIUS_M:.0f} m（31,392画素）",
                    "矩形": "既存の .npy そのまま＝円の外接矩形 203×202画素 ＝ 6.09×6.06 km（41,006画素）",
                    "画素": f"{PIXEL_M:.0f} m グリッド（UTM 54N）"}}
    for key, inside in (("円_半径3km", True), ("矩形_従来", False)):
        per = {str(y): year_stats(y, inside) for y in YEARS}
        am = [per[str(y)]["面積平均"] for y in YEARS]
        med = [per[str(y)]["画素中央値"] for y in YEARS]
        fr = [per[str(y)]["決定率"] for y in YEARS]
        res[key] = dict(
            年別=per,
            面積平均=dict(平均=round(sum(am) / len(am), 1), 標準偏差=round(sd(am), 2),
                          最早_最晩=[min(am), max(am)]),
            画素中央値=dict(最早_最晩=[min(med), max(med)], 幅=round(max(med) - min(med), 1)),
            決定率=dict(最小_最大=[min(fr), max(fr)]))

    c, r = res["円_半径3km"], res["矩形_従来"]
    sig_r = math.sqrt(max(r["面積平均"]["標準偏差"] ** 2 - 5.4 ** 2, 0))
    sig_c = math.sqrt(max(c["面積平均"]["標準偏差"] ** 2 - 5.4 ** 2, 0))
    res["downstream_effect"] = {
        "面積平均の標準偏差": {"矩形": r["面積平均"]["標準偏差"], "円": c["面積平均"]["標準偏差"]},
        "観測誤差を除いた信号_日": {"矩形": round(sig_r, 1), "円": round(sig_c, 1),
                                    "式": "sqrt(σ² − 5.4²)。5.4日は t2_return_period.json の "
                                          "snr_in_days.IV_2017-26 の観測誤差"},
        "信号対雑音比": {"矩形": round(sig_r / 5.4, 2), "円": round(sig_c / 5.4, 2)},
        "丸めの注意": "提出物と t2_return_period.json は σ を 8.9 に丸めた上で 信号7.1日・SNR1.30 と"
                      "書いている。ここでは丸めない σ（矩形8.93／円8.80）から計算しているので、"
                      "矩形の SNR は 1.32 と出る。**資料で引用するときは提出物側の 1.30 → 1.29 に揃えること**",
        "判定": "円にしても提出物の結論は動かない（信号 7.1→6.9日、SNR 1.30→1.29）。"
                "動くのは画素中央値で、2022年が 117.0 → 144.5 日目（9年で2番目に早い→2番目に遅い）",
        "取り直せなかった量": "観測間隔（中央値20日・最悪48日）。画素ごとの挟み込み幅は "
                              ".npy に残っていない（保存されているのは中点だけ）ので、円内で取り直すには "
                              "fetch_snowmap_poc.py からの再実行が要る",
    }
    os.makedirs(_OUT, exist_ok=True)
    p = os.path.join(_OUT, "t2_snowmap_circle_r3km.json")
    json.dump(res, open(p, "w"), ensure_ascii=False, indent=1)
    print(f"書き出し: {p}")
    for y in YEARS:
        a, b = c["年別"][str(y)], r["年別"][str(y)]
        flag = "  ←変化" if abs(a["画素中央値"] - b["画素中央値"]) >= 1 else ""
        print(f"  {y}: 中央値 円 {a['画素中央値']:>5} / 矩形 {b['画素中央値']:>5}"
              f"   決定率 {a['決定率']:.0%} / {b['決定率']:.0%}{flag}")
    print(f"  面積平均σ: 円 {c['面積平均']['標準偏差']} / 矩形 {r['面積平均']['標準偏差']}")


if __name__ == "__main__":
    main()
