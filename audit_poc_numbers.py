"""文書が引用しているPoCの数値を、poc/out/*.json のどのキーに戻れるかで追跡する

## なぜ要るか

このプロジェクトのPoCの誤りは、2026年8月11日の第2次PoCまで**常設の見張りがいなかった**
（既存4レビューアは全員が数値を職掌外にしている）。そこで見つかった14の型のうち、
**唯一機械的に検査できるのが「引用された数字がJSONに戻れるか」である**（型E-4）。

戻れない数字は次の4つのどれかで、対応が違う:

  (a) 陳腐化   … 再実行で値が変わったのに文書が追随していない → **訂正**
  (b) 手計算   … JSONの値から算術で作った派生値 → **出所を文書に書く**
  (c) 外部出典 … 文献・要項・統計から取った値 → **出典を文書に書く**
  (d) 根拠なし … どこからも来ていない → **指摘**

このスクリプトは (a)〜(d) を区別しない。**区別できないものを全部並べる**のが仕事で、
仕分けは人間（または nedo-poc-auditor）がやる。

## やり方

1. `poc/out/*.json` と `theme2_*/poc/out/*.json` を再帰的に走査し、**全数値を集める**
   （キーへのパスつき。丸めの表記違いを吸収するため複数の丸めで持つ）
2. 文書の各行のうち **PoCの数値が出てくる行だけ**を対象にする（キーワードで絞る。
   日付・字数・施設数・金額のような別種の数字を拾わないため）
3. その行の数値を1つずつ、JSONの値集合に照合する
4. 照合できなかったものを、行の文脈つきで列挙する

**この検査は「戻れた数字は正しい」ことを意味しない。** 同じ値がJSONにあるだけで、
その数字が正しい文脈で引用されているかは見ていない。**追跡可能性だけの検査である。**

使い方: `python3 audit_poc_numbers.py [--all] [--doc パス]`
  --all  キーワードで絞らず全行を対象にする（雑音は増える）
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# PoCの数値が出てくる行を拾うキーワード。ここに無い話題の数字は対象外にする
POC_KEYWORDS = [
    "AUC", "SNR", "NEdT", "NEΔL", "エポック", "ep)", "雑音", "誤報", "偽陽性",
    "検知", "検出", "判別", "誤差", "バジェット", "スイング", "ゲイン", "増幅",
    "画素", "分解能", "σ", "標準偏差", "RMSE", "区間", "分位", "超過確率",
    "消雪", "積雪", "SWE", "融雪", "DDF", "E[G]", "観測間隔", "年々変動",
    "閾値", "z=", "|z|", "段差", "感度", "相関", "帯域", "µm", "um)",
    "雑音床", "兄弟", "二重差分", "共通モード", "季節", "離隔", "デコンボリューション",
    "成立/年", "回/年", "件/プラント", "代用資産", "試行", "ブートストラップ",
]

# 数値トークン。カンマ区切り・小数・符号つきを拾う。
# **lookbehind に \w を使ってはいけない**——Pythonの \w は日本語文字を含むので
# 「水蒸気爆発期2,759千m³」で先頭の 2 が弾かれ、カンマの後ろの 759 を拾ってしまう
# （最初の実装で実際に踏んだ）。除くのは数字・小数点・カンマだけにする。
# **後読みの否定に , を入れてはいけない**（2度目の罠）。"(139.6615, 35.4952" のように
# 数値の直後にカンマが来ると "139.6615" 全体が弾かれ、"139" だけを拾ってしまう。
# 「2,759 から 759 を拾う」問題は前方の (?<![\d.,]) が既に防いでいるので、
# 後方は数字の継続だけを禁じればよい。
NUM_RE = re.compile(
    r"(?<![\d.,])([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?)(?!\d)")

# 照合から除く自明な数（節番号・年・型番などに埋もれるもの）
TRIVIAL = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 100}
# 年・日付として現れる数
YEARISH = set(range(1900, 2101))


def collect_json_numbers():
    """全PoC JSONから**生の**数値を集める。返り値は [(値, パス), ...]

    **丸めの変種や×100を登録してはいけない。** 最初の実装はそれをやって母集団を
    2千個から9千4百個に膨らませ、**小数の偶然一致率が100%になった**
    （＝「戻せた」が何も意味しない検査になっていた。PoC-4の「偽陽性0件」と同じ型の誤り）。
    照合は「文書が印字した桁数で丸めたら一致するか」で行う。丸めは照合側で1回だけ。
    """
    vals = []
    files = sorted(glob.glob(os.path.join(ROOT, "poc", "out", "*.json"))) + \
        sorted(glob.glob(os.path.join(ROOT, "theme2_*", "poc", "out", "*.json")))

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        elif isinstance(o, bool):
            return
        elif isinstance(o, (int, float)):
            vals.append((float(o), path))
        elif isinstance(o, str):
            # 文字列に埋め込まれた数値も拾う（"約23分" "0.217 × E[G]" など）。
            # 母集団を膨らませるので**別リストにして、生の値で照合できなかったときだけ使う**
            for m in NUM_RE.finditer(o):
                try:
                    vals.append((float(m.group(1).replace(",", "")), path + "(文字列内)"))
                except ValueError:
                    continue

    for p in files:
        try:
            walk(json.load(open(p)), os.path.relpath(p, ROOT))
        except Exception as e:
            print(f"[警告] {p} を読めない: {e}", file=sys.stderr)
    return vals, files


def _decimals(raw):
    return len(raw.split(".")[1]) if "." in raw else 0


def is_traceable(x, vals, raw=None, allow_pct=False):
    """文書が印字した桁数で丸めたらJSONの生値と一致するか

    raw を渡すと桁数をそこから取る（渡さないと整数扱い）。
    allow_pct=True なら v*100 も試す（行に % がある場合だけ許す）。
    返り値は一致したJSONのパス、無ければ None。
    """
    nd = _decimals(raw) if raw is not None else 0
    for v, path in vals:
        if round(v, nd) == x:
            return path
        if allow_pct and round(v * 100.0, nd) == x:
            return path + "(×100)"
    return None


def audit_doc(path, vals, keyword_filter=True):
    out = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except Exception:
        return out
    in_code = False
    for ln, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if keyword_filter and not any(k in line for k in POC_KEYWORDS):
            continue
        for m in NUM_RE.finditer(line):
            raw = m.group(1)
            try:
                x = float(raw.replace(",", ""))
            except ValueError:
                continue
            if x in TRIVIAL or (x.is_integer() and int(x) in YEARISH):
                continue
            if abs(x) > 1e7:
                continue
            hit = is_traceable(x, vals, raw=raw, allow_pct=("%" in line))
            if hit is None:
                out.append(dict(file=os.path.relpath(path, ROOT), line=ln,
                                value=raw, context=line.strip()[:150]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="キーワードで絞らない")
    ap.add_argument("--every-doc", action="store_true", help="調査メモも含め全mdを対象にする")
    ap.add_argument("--doc", action="append", help="対象文書を明示（複数可）")
    args = ap.parse_args()

    vals, files = collect_json_numbers()
    print(f"# PoC数値の追跡監査\n")
    print(f"JSON {len(files)} 本から {len(vals)} 個の相異なる数値を集めた。")
    for f in files:
        print(f"  - {os.path.relpath(f, ROOT)}")

    if args.doc:
        docs = args.doc
    elif args.every_doc:
        docs = sorted(glob.glob(os.path.join(ROOT, "*.md"))) + \
            sorted(glob.glob(os.path.join(ROOT, "theme2_*", "*.md")))
        docs = [d for d in docs if os.path.basename(d) != "CLAUDE.md"]
    else:
        # 既定は**PoCの結果を引用する文書**だけ。調査メモ（01・05）は外部出典の数値が
        # 大半なので既定から外す（--every-doc で入る）
        docs = [os.path.join(ROOT, x) for x in (
            "07_PoC中間結果.md", "12_提出版_様式4.md", "08_応募書類ドラフト.md",
            "02_提案書骨子_v0.2.md", "15_事業計画の裏付け.md", "13_本文の字数予算.md",
            "18_テーマ代替案の検討.md", "21_差し替え検証_独立セッション.md",
        )] + [os.path.join(ROOT, "theme2_ライフライン復旧", x) for x in (
            "07_PoC結果.md", "12_提出版_様式4.md", "13_事業計画の裏付け.md",
        )]
        docs = [d for d in docs if os.path.exists(d)]

    total = 0
    per_file = {}
    for d in docs:
        rows = audit_doc(d, vals, keyword_filter=not args.all)
        if rows:
            per_file[os.path.relpath(d, ROOT)] = rows
            total += len(rows)

    print(f"\n## JSONに戻せなかった数値: {total} 件\n")
    for f, rows in sorted(per_file.items(), key=lambda kv: -len(kv[1])):
        print(f"### {f}  ({len(rows)} 件)\n")
        for r in rows:
            print(f"  L{r['line']:>4} `{r['value']}`  … {r['context']}")
        print()

    # ---- この検査自身の検出力を測る（偶然一致率）----
    import random as _r
    rnd = _r.Random(7)
    print("## この検査の検出力（偶然一致率）\n")
    print("**偶然一致率が高い桁では『戻せた』は何も意味しない。** 情報があるのは戻せなかった側だけである。\n")
    print("| 数値の形 | 偶然一致率 |")
    print("|---|---|")
    for label, gen, fmt in (
        ("小数1桁 0.1-9.9", lambda: rnd.uniform(0.1, 9.9), "%.1f"),
        ("小数2桁 0.01-0.99", lambda: rnd.uniform(0.01, 0.99), "%.2f"),
        ("小数3桁 0.001-0.999", lambda: rnd.uniform(0.001, 0.999), "%.3f"),
        ("整数 13-999", lambda: rnd.randint(13, 999), "%d"),
        ("整数 1000-9999", lambda: rnd.randint(1000, 9999), "%d"),
    ):
        n, hit = 1200, 0
        for _ in range(n):
            rawv = fmt % gen()
            if is_traceable(float(rawv), vals, raw=rawv) is not None:
                hit += 1
        print(f"| {label} | {hit/n:.1%} |")
    print()

    print("## 仕分けの区分（人間がやる）\n")
    print("  (a) 陳腐化   → 訂正")
    print("  (b) 手計算   → 出所を文書に書く")
    print("  (c) 外部出典 → 出典を文書に書く")
    print("  (d) 根拠なし → 指摘")


if __name__ == "__main__":
    main()
