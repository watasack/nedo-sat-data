#!/usr/bin/env python3
"""図の中に載る文字数を数える（`12_提出版_様式4.md` の「回答別の着地」節が持つ4つの値の再計算用）。

**なぜ要るか**: 事務局照会の質問4が「500字程度に図表の文字が算入されるか」を聞いており、
回答が(C)（図の中の文字も算入する）だった場合の着地計算にこの4値が要る。
`12_提出版_様式4.md` は「図を直したらこの4つを数え直すこと」と指示しているが、
数え方が文章でしか書かれていなかったため、直すたびに手で数え直すことになっていた。
図4に社会的インパクトの帯を足した時点で機械化した。

**数え方**（`12` の着地節が定義しているものをそのまま実装する）:
  - `make_figures_t2.py` の各 fig 関数の中にある文字列リテラルを集計する
  - 空白（改行を含む）は数えない
  - **関数の docstring は数えない**（図には載らないため。これを入れると図2が335字ぶん過大になる）
  - 色コード・スタイル語・マーカー形状（"#c0392b" "center" "round,pad=..." "*" "<->" 等）は数えない
  - **日本語以外も数える**（"+Landsat 7" のような欧文行も図に載る文字だから）
  - 軸目盛りの自動数値は文字列リテラルではないので自然に除かれる

実行: python3 count_fig_chars.py
"""
import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent / "poc" / "src" / "make_figures_t2.py"

# 色コード（#rrggbb）と、英数記号だけで構成される指定語（"center" "round,pad=0.012" 等）
STYLE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z0-9_\-\.,:= ]*)$")
# matplotlib のマーカー・矢印スタイル（CJKを含まない短い記号列）
MARKER = re.compile(r"^[^　-鿿＀-￯]{1,4}$")


def count(fn: ast.FunctionDef) -> int:
    body = fn.body
    # 先頭が文字列リテラルだけの式なら docstring。図には載らない
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    total = 0
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value
                if STYLE.match(s) or MARKER.match(s):
                    continue
                total += len(re.sub(r"\s", "", s))
    return total


def main():
    tree = ast.parse(SRC.read_text())
    out = {}
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef) and re.fullmatch(r"fig\d+", fn.name):
            out[fn.name] = count(fn)
    for k in sorted(out):
        print(f"{k} = {out[k]}字")
    print("\n12_提出版_様式4.md の「回答別の着地」節に書く形:")
    print("／".join(f"図{k[3:]}={v}字" for k, v in sorted(out.items())))


if __name__ == "__main__":
    main()
