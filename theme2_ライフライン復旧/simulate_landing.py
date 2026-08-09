#!/usr/bin/env python3
"""質問4の回答が(B)だった場合の着地を、実際に適用して測る。

`12_提出版_様式4.md` の「回答別の着地」節は**実測値**を要求している（見込み値を書かない）。
本文を1行直すたびに手で適用して数え直していたので機械化した。

  (A) 本文のみを数える            → 現状のまま。何もしない
  (B) キャプション・図表番号は算入 → 下の OPS を適用した結果を測る（このスクリプトの仕事）
  (C) 図の中の文字も算入          → 全設問の図表とキャプションを落とす。本文列がそのまま合算になる

実行: python3 simulate_landing.py
      python3 simulate_landing.py --write   ← 一時ファイル _landing_B.md を残す（目視確認用）
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "12_提出版_様式4.md"
TMP = HERE / "_landing_B.md"
COUNTER = HERE.parent / "count_chars.py"

# (B) の手順。**本文を削るのではなく置換して文が破断しないようにする**。
# 各要素は (設問, 説明, 探す文字列, 置換後)。置換後が "" なら削除。
OPS = [
    ("④", "表1とキャプション行を両方落として図表なしにする（表の分量が5設問で最大）",
     "表1 火口周辺の積雪水量を得る手段の比較。\n\n"
     "| 手段 | 分解能 | 火口高度で | 過去に遡れるか |\n"
     "|---|---|---|---|\n"
     "| 積雪深計 | 点 | 気象庁の常設点は0 | 不可 |\n"
     "| 気象庁 解析積雪深 | 5kmメッシュ | 外挿 | 可 |\n"
     "| 雪おろシグナル | 1kmメッシュ | 1,700mで実測の約6倍 | 可 |\n"
     "| 航空レーザ | 面 | 噴火時は飛べない場合 | 不可 |\n"
     "| 再解析＋水文モデル | 流域 | 流量観測がなく較正不可 | 可 |\n"
     "| 衛星＋機械学習 | 面 | 地点実測との統合が要る | 当年のみ |\n"
     "| 本提案（光学衛星） | 30m | 火口周辺を直接観測 | 約40年 |\n", ""),
    ("②", "道路管理者の観測点の文を削る（外挿の否定は次段落の現地測量で足りる）",
     "計画の図にある道路管理者の観測点も回帰に使われず、直線より3〜4割低い。", ""),
    ("②", "キャプションを短縮する",
     "図2 山麓6観測所からの標高外挿と、火口高度の実測との食い違い（積雪水量）。",
     "図2 標高外挿と火口高度の実測の食い違い。"),
    ("③", "「2年・10年超過確率には足りる。」を削る（次文の100年の記述が役割を引き継ぐ）",
     "2年・10年超過確率には足りる。", ""),
    ("③", "キャプションを短縮する",
     "図3 消雪日を特定できる年数の実測（8火山・カタログ集計）。",
     "図3 消雪日を特定できる年数の実測（8火山）。"),
    ("①", "気象庁336地点の文を削る（同じ事実は④にある）",
     "気象庁が積雪深を測る336地点の最高は1,292mで、火口より937〜2,916m低い。", ""),
    ("⑤", "火山災害警戒地域の句を落として置換する（削ると述語が消えて文が破断する）",
     "緊急減災対策砂防計画の対象は29火山、うち積雪火山21座、火山災害警戒地域は50火山179市町村にわたる。",
     "緊急減災対策砂防計画の対象は29火山、うち積雪火山21座である。"),
    ("⑤", "那須岳の一文を圧縮する（業務名の正式名称は落としても指示対象は残る）",
     "日光砂防事務所は2026年度の発注見通しに「那須岳火山噴火緊急減災対策検討業務」として衛星を活用した積雪深推定の検討を挙げた。",
     "日光砂防事務所は2026年度の発注見通しに那須岳での衛星による積雪深推定の検討を挙げた。"),
    ("⑤", "キャプションを短縮する",
     "図4 想定ユーザー、予算の所在、事業化の二段階と、下流で動く物量。",
     "図4 想定ユーザー、予算、事業化の二段階と下流で動く物量。"),
]


def measure(path):
    """count_chars.py の出力に「合算」列を足して返す。**判定は合算で行う**（本文だけ見て取り違えない）。"""
    out = subprocess.run([sys.executable, str(COUNTER), str(path)],
                         capture_output=True, text=True, check=True).stdout
    lines = []
    for ln in out.rstrip("\n").split("\n"):
        m = re.match(r"\s*(\d+)\s+\(図表\s+(\d+)\)\s+(.*)$", ln)
        if not m:
            lines.append(ln)
            continue
        body, fig, title = int(m.group(1)), int(m.group(2)), m.group(3)
        total = body + fig
        flag = "" if total <= 500 or "スケジュール" in title else "  ★500字超過"
        lines.append(f"  本文{body:4d}  図表{fig:4d}  合算{total:4d}{flag}  {title}")
    return "\n".join(lines)


def main():
    text = SRC.read_text()
    print("=== (A) 現状 ===")
    print(measure(SRC))

    applied = text
    for q, why, find, repl in OPS:
        if applied.count(find) < 1:
            print(f"!! 手順が当たらない（本文が変わった可能性）: {q} {why}\n   探した文字列: {find[:40]}…")
            continue
        applied = applied.replace(find, repl, 1)
    TMP.write_text(applied)
    print("=== (B) 手順を適用した結果 ===")
    print(measure(TMP))
    print("手順の一覧:")
    for i, (q, why, _, _) in enumerate(OPS, 1):
        print(f"  {i}. {q} {why}")
    if "--write" not in sys.argv:
        TMP.unlink()
    else:
        print(f"\n（{TMP.name} を残した）")


if __name__ == "__main__":
    main()
