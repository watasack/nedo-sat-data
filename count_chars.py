#!/usr/bin/env python3
"""様式4の設問別字数を数える。

数え方（08のチェックリスト21の規則をそのまま適用）:
  - 見出し行・引用行(>)・水平線・表の区切り行は数えない
  - 箇条書き/番号付きリストのマーカー、強調 **、表の縦線 |、バッククォートを除去
  - 残りから改行と空白を除いた文字数
表の中身は「図表1点」として本文とは別に集計する。
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "12_提出版_様式4.md"
src = open(path, encoding="utf-8").read()

sections = []
cur = None
for line in src.split("\n"):
    m = re.match(r"^(#{2,3})\s+(.*)$", line)
    if m:
        cur = {"title": m.group(2).strip(), "body": [], "table": []}
        sections.append(cur)
        continue
    if cur is None or "提出時に削除" in cur["title"]:
        continue
    if line.strip().startswith(">"):
        continue
    if re.match(r"^\s*-{3,}\s*$", line):
        continue
    if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
        continue
    (cur["table"] if line.lstrip().startswith("|") else cur["body"]).append(line)


def norm(lines):
    t = "\n".join(lines)
    t = t.replace("**", "").replace("`", "").replace("|", "")
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.M)
    return len(re.sub(r"\s+", "", t))


total = 0
for s in sections:
    b, tb = norm(s["body"]), norm(s["table"])
    if b == 0 and tb == 0:
        continue
    total += b
    print(f"{b:>6}  (表{tb:>5})  {s['title']}")
print(f"{total:>6}  合計（本文のみ・表は除く）")
