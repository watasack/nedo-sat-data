#!/usr/bin/env python3
"""降灰テーマ（テーマ2候補）の一次情報取得スクリプト

GitHub Actions ランナー上で実行する想定。サンドボックスからは bousai.go.jp /
jsece.or.jp / jma.go.jp などが egress 遮断（CONNECT に 403）されているため、
制限のない Actions で取得して ashfall-refs ブランチに置く。

- URL 直指定。1件失敗しても止めない。結果は manifest.json に記録
- PDF は pdftotext -layout でテキスト化（ワークフロー側で poppler-utils を入れる）
"""

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path("ashfall_refs")
UA = "Mozilla/5.0 (compatible; research-fetch/1.0)"

URLS = [
    # --- 中央防災会議 大規模噴火時の広域降灰対策検討WG（令和2年4月報告） ---
    ("bousai_honbun", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/syutohonbun.pdf"),
    ("bousai_shiryo02_閾値の考え方", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/syutoshiryo_02.pdf"),
    ("bousai_sanko01_火山灰の特徴", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/syutosanko_01.pdf"),
    ("bousai_2019322_ライフライン影響想定", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/2019322siryo1-2.pdf"),
    ("bousai_20180911_被害想定項目", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/20180911siryo3.pdf"),
    ("bousai_4kai_sanko1", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/4kai_shiryo1_sanko1.pdf"),
    ("bousai_1kai_gijiroku", "https://www.bousai.go.jp/kazan/kouikikouhaiworking/pdf/kentokai1kai_gijiroku.pdf"),
    # --- 砂防学会 2019: 衛星SARによる降灰分布把握 ---
    ("jsece2019_SAR降灰分布", "https://www.jsece.or.jp/event/conf/abstract/2019/pdf/349.pdf"),
    ("jstage_sabo_72_6", "https://www.jstage.jst.go.jp/article/sabo/72/6/72_18/_pdf"),
    # --- 産総研 衛星リモセンによる火山活動評価 ---
    ("gsj_openfile470", "https://www.gsj.jp/data/openfile/no0470/0470-6.pdf"),
    # --- 気象庁 桜島降下火山灰 / 降灰予報 ---
    ("jma_sakurajima_降下火山灰", "https://www.jma.go.jp/jma/kishou/shingikai/ccpve/Report/023/kaiho_023_04.pdf"),
    # --- 千葉県 降灰対策指針（閾値の二次引用として） ---
    ("chiba_降灰対策指針", "https://www.pref.chiba.lg.jp/bousai/saigaitaisaku/kouhai/documents/kouhaishishin-r403.pdf"),
    # --- 降灰対策に資する施策・研究の方向性（国の研究計画。競合の有無） ---
    ("bousai_施策研究の方向性", "https://www.bousai.go.jp/kazan/taisakukaigi/pdf/dai9kai/20190423siryo3_2.pdf"),
    # --- 気象庁 降灰予報の高度化検討会（2025） ---
    ("jma2025_降灰予報検討会02", "https://www.jma.go.jp/jma/kishou/shingikai/kentoukai/2025kouhai/02/gijiyoushi_02.pdf"),
    ("jma2025_降灰予報検討会02_資料", "https://www.jma.go.jp/jma/kishou/shingikai/kentoukai/2025kouhai/02/99-1.pdf"),
    ("jma2025_降灰予報検討会03", "https://www.jma.go.jp/jma/kishou/shingikai/kentoukai/2025kouhai/03/gijiyoushi_03.pdf"),
    # --- 次世代火山研究推進事業 課題D-2（リアルタイム火山灰ハザード評価） ---
    ("kazanpj_D2", "https://kazan-pj.bosai.go.jp/research/d/d2"),
    # --- 御嶽山2014 降灰分布（現地実測。検証用正解データ） ---
    ("ontake2014_降灰分布", "https://www.data.jma.go.jp/svd/vois/data/tokyo/STOCK/kaisetsu/CCPVE/Report/119/kaiho_119_16.pdf"),
    # --- 新燃岳2011 降灰の特徴（都城高専） ---
    ("shinmoe2011_降灰の特徴", "https://www.miyakonojo-nct.ac.jp/library/data/48_13.pdf"),
    # --- 気象研 新燃岳2011 ---
    ("mri_shinmoe2011", "https://www.mri-jma.go.jp/Topics/H23/Happyoukai2011/2011Happyou03.pdf"),
]


def fetch(name, url):
    rec = {"name": name, "url": url}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
            rec["status"] = r.status
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["error"] = str(e)
        return rec
    except Exception as e:  # noqa: BLE001
        rec["status"] = 0
        rec["error"] = repr(e)
        return rec

    ext = ".pdf" if url.lower().endswith(".pdf") or body[:4] == b"%PDF" else ".bin"
    path = OUT / f"{name}{ext}"
    path.write_bytes(body)
    rec["bytes"] = len(body)
    rec["file"] = str(path)

    if ext == ".pdf":
        txt = OUT / f"{name}.txt"
        try:
            subprocess.run(
                ["pdftotext", "-layout", str(path), str(txt)],
                check=True, capture_output=True, timeout=180,
            )
            rec["text"] = str(txt)
            rec["text_chars"] = len(txt.read_text(errors="replace"))
        except Exception as e:  # noqa: BLE001
            rec["text_error"] = repr(e)
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = [fetch(n, u) for n, u in URLS]
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"取得成功 {ok}/{len(manifest)}")
    for m in manifest:
        print(m.get("status"), m.get("name"), m.get("bytes", ""), m.get("error", ""))


if __name__ == "__main__":
    main()
