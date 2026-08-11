#!/usr/bin/env python3
"""電力インフラの防災・災害対応に関する一次情報の取得スクリプト

GitHub Actions ランナー上で実行する想定。サンドボックスからは meti.go.jp /
bousai.go.jp / mlit.go.jp / occto.or.jp などが egress 遮断（CONNECT に 403）
されているため、制限のない Actions で取得して power-refs ブランチに置く。

- URL 直指定。1件失敗しても止めない。結果は manifest.json に記録
- PDF は pdftotext -layout でテキスト化（ワークフロー側で poppler-utils を入れる）
- HTML はそのまま保存（インデックスページからのリンク発見用）
"""

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path("power_refs")
UA = "Mozilla/5.0 (compatible; research-fetch/1.0)"

URLS = [
    # --- 台風15号（令和元年房総半島台風）電力レジリエンスWG ---
    ("meti_resil005_停電復旧プロセス検証", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/resilience_wg/pdf/005_04_00.pdf"),
    ("meti_resil_最終報告20200110", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/resilience_wg/pdf/20200110_report_02.pdf"),
    ("meti_resil_最終報告20200110_01", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/resilience_wg/pdf/20200110_report_01.pdf"),
    ("meti_resil009_東電振り返り", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/resilience_wg/pdf/009_04_00.pdf"),
    ("mlit_東電PG振り返り", "https://wwwtb.mlit.go.jp/kanto/content/000167401.pdf"),
    ("meti_resil_index", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/resilience_wg/index.html"),
    # --- 電力安全課 / 鉄塔・電柱WG ---
    ("meti_denryoku_anzen021_令和元年災害概要", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/pdf/021_01_00.pdf"),
    ("meti_hoanshohi003_台風15_19対応", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/pdf/003_02_00.pdf"),
    ("meti_tettou001_東電PG被害状況", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/tettou/pdf/001_03_04.pdf"),
    ("meti_tettou_index", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/tettou/index.html"),
    # --- 能登半島地震 ---
    ("meti_denki_setsubi020_能登対応", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/pdf/020_01_01.pdf"),
    ("bousai_noto_wg2_電力ガス復旧", "https://www.bousai.go.jp/jishin/noto/taisaku_wg_02/pdf/siryo2_1_3.pdf"),
    ("rikuden_能登半島地震停電復旧", "https://www.rikuden.co.jp/nw_network/notohantou.html"),
    ("rikuden_能登大雨停電復旧", "https://www.rikuden.co.jp/nw_network/noto_rain.html"),
    # --- 千葉県・内閣府の検証 ---
    ("chiba_検証報告書", "https://www.pref.chiba.lg.jp/gyoukaku/press/2019/documents/houkokusyo.pdf"),
    ("bousai_台風15号事例", "https://www.bousai.go.jp/kaigirep/houkokusho/hukkousesaku/saigaitaiou/output_html_1/pdf/201901.pdf"),
    # --- 被害想定（南海トラフ・首都直下） ---
    ("bousai_南海トラフWG6_2_1", "https://www.bousai.go.jp/jishin/nankai/taisaku_wg_02/6/pdf/2-1.pdf"),
    ("hemri_停電分科会最終報告2025", "https://www.hemri21.jp/contents/images/2025/10/4d743f2c22c660c52dfe88a9d3cd6eb8-2.pdf"),
    # --- 電力データ活用 ---
    ("meti_電力データ活用の推進2023", "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/denryoku_gas/pdf/066_07_00.pdf"),
    ("enecho_電力データ活用検討会", "https://www.enecho.meti.go.jp/category/electricity_and_gas/electric/shiryo_joho/data/0630_03.pdf"),
    ("enecho_台風と電力特集", "https://www.enecho.meti.go.jp/about/special/johoteikyo/typhoon.html"),
    # --- 北海道胆振東部地震ブラックアウト（OCCTO 検証委員会） ---
    ("occto_hokkaido_index", "https://www.occto.or.jp/iinkai/hokkaido/index.html"),
    ("occto_index_iinkai", "https://www.occto.or.jp/iinkai/index.html"),
    # --- スマート保安 ---
    ("meti_smart_hoan015_スマート保安技術", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/hoan_seido/pdf/015_03_00.pdf"),
    ("meti_電気保安スマート保安AP", "https://www.meti.go.jp/policy/safety_security/industrial_safety/smart_industrial_safety/action_plan_denki.pdf"),
    # --- 第2ラウンド: 風倒木と電柱損壊 / 森林被害 ---
    ("jstage_風倒木と電柱損壊の関係", "https://www.jstage.jst.go.jp/article/jfsc/131/0/131_176/_pdf"),
    ("chiba_台風15号森林被害緊急調査", "https://www.pref.chiba.lg.jp/shinrin/taifu15-chousakeltuka.html"),
    ("chiba_サンブスギ", "https://www.pref.chiba.lg.jp/lab-nourin/nourin/shinrinken/sanbusugi.html"),
    ("rinya_kanto_r1_15gou", "https://www.rinya.maff.go.jp/kanto/koho/saigaijoho/r1_15gou.html"),
    # --- 第2ラウンド: 塩害 ---
    ("jsnds_2018台風24号塩害", "https://www.jsnds.org/ssk/ssk_37_4_365.pdf"),
    ("rikuden_配電線塩分付着停電防止研究", "https://www.rikuden.co.jp/kenkyu/attach/topics08_01.pdf"),
    ("rtri_高圧がいしESDD", "https://www.rtri.or.jp/publish/rtrirep/2013/is5f1i000000fvif-att/1308_3.pdf"),
    ("criepi_ポリマーがいし適用動向", "https://www.jstage.jst.go.jp/article/jaesjb/65/8/65_513/_pdf"),
    # --- 第2ラウンド: 雪害 ---
    ("engineer_新潟大停電の要因と対策", "https://www.engineer.or.jp/cmty/nikkan/kasahara.pdf"),
    ("jma_niigata_2010大雪", "https://www.data.jma.go.jp/niigata/menu/saigai_NI/shosai/031_2010_shosai.pdf"),
    ("tohoku_nw_大雪停電", "https://nw.tohoku-epco.co.jp/information/1230943_2390.html"),
    # --- 第2ラウンド: 能登 / 電気設備自然災害等対策WG ---
    ("meti_denki_setsubi_index", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/index.html"),
    ("rikuden_noto", "https://www.rikuden.co.jp/nw_network/notohantou.html"),
    # --- 第2ラウンド: 停電実績（正解データ候補） ---
    ("tepco_停電履歴検索", "https://teideninfo.tepco.co.jp/day/teiden/index-j.html"),
    ("tepco_停電履歴の見方", "https://teideninfo.tepco.co.jp/mikata-j.html"),
    # --- 第2ラウンド: 深層学習による台風被害検知（先行事例の確認） ---
    ("jstage_深層学習台風被害検知", "https://www.jstage.jst.go.jp/article/jsceiii/4/3/4_867/_pdf"),
    # --- 第3ラウンド: 電中研の解説（現状と課題）と最新WG ---
    ("criepi_送配電防災減災の現状と課題", "https://www.jstage.jst.go.jp/article/jaesjb/62/4/62_203/_pdf/-char/ja"),
    ("criepi_den477_気象外力と電力設備", "https://criepi.denken.or.jp/koho/news/den477.pdf"),
    ("criepi_RAMPT_N15012", "https://criepi.denken.or.jp/jp/kenkikaku/report/detail/N15012.html"),
    ("meti_denki_setsubi025", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/025.html"),
    ("meti_denki_setsubi024", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/024.html"),
    ("meti_denki_setsubi_idx2", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/index.html"),
    ("meti_hoanshohi003_retry", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/pdf/003_02_00.pdf"),
    ("meti_tettou001_retry", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/tettou/pdf/001_03_04.pdf"),
    ("meti_denki_setsubi020_retry", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/pdf/020_01_01.pdf"),
    ("meti_denki_setsubi021_能登9月", "https://www.meti.go.jp/shingikai/sankoshin/hoan_shohi/denryoku_anzen/denki_setsubi/pdf/021_01_01.pdf"),
    ("chiba_森林被害緊急調査_retry", "https://www.pref.chiba.lg.jp/shinrin/taifu15-chousakeltuka.html"),
    ("bousai_r1typhoon15_速報21", "https://www.bousai.go.jp/updates/r1typhoon15/pdf/r1typhoon15_21.pdf"),
    ("bousai_官民衛星統合防災利用実証", "https://www.bousai.go.jp/taisaku/suishinhi/pdf/saitaku07.pdf"),
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

    is_pdf = url.lower().endswith(".pdf") or body[:4] == b"%PDF"
    ext = ".pdf" if is_pdf else ".html"
    path = OUT / f"{name}{ext}"
    path.write_bytes(body)
    rec["bytes"] = len(body)
    rec["file"] = str(path)

    if is_pdf:
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
