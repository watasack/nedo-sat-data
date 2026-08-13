# -*- coding: utf-8 -*-
"""面談用の説明資料（60_shiryo/日本気象協会_ご説明.html）から、先方へ送付できる
単独HTML（60_shiryo/日本気象協会_送付版.html）を作る。

    python3 40_scripts/make_shiryo_send_version.py

面談前提の文言（所要時間・画面共有のみ・単独で進めます 等）を落とし、出所欄から
社内のファイルパスを外し、charset を持つ完全なHTMLとして包み直すだけの変換である。
元の資料を直したら、これを回して送付版を作り直すこと（置換は1件でも見つからないと止まる）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "60_shiryo/日本気象協会_ご説明.html")
DST = os.path.join(ROOT, "60_shiryo/日本気象協会_送付版.html")

s = open(SRC, encoding="utf-8").read()

REPL = [
    # ---- 面談前提の文言 ----
    ('aria-label="本日の道順"', 'aria-label="目次"'),
    ('<p class="tochd">本日の道順</p>', '<p class="tochd">目次</p>'),
    ('その部分でお力をお借りできないかと考えて本日ご相談に伺いました。',
     'その部分でお力をお借りできないかと考えております。'),
    ('''    <p class="lede" style="margin-top:.7rem">
      通してご覧いただくのは<strong>図7枚＋各テーマ冒頭の見取り図2枚で、10〜15分</strong>です（目次の順に進みます）。
    </p>
''', ''),
    ('''      宛先: 一般財団法人日本気象協会 御中　／　作成: 株式会社GRID　／　2026年8月13日 第21版<br>
      位置づけ: 初回の情報交換（この場でのご判断は求めません）　／　取扱い: 面談での画面共有のみ（配布いたしません）''',
     '''      宛先: 一般財団法人日本気象協会 御中　／　作成: 株式会社GRID　／　2026年8月13日<br>
      位置づけ: 初回の情報交換の段階です　／　取扱い: 貴協会内でのご検討にご利用ください（第三者への再配布はお控えください）'''),
    ('<strong>本日いちばんご相談したいのはこの図です</strong>——',
     '<strong>とくにご相談したいのがこの図です</strong>——'),
    ('【補足】同じことを実データで — 通しでは飛ばします',
     '【補足】同じことを実データで確かめたもの'),
    ('''          <strong>費用を伴う形（受託・共同研究）になる場合は、規模と時期を別途ご相談させてください。</strong>本日は「どういう観測なら現実的か」までで結構です。''',
     '''          <strong>費用を伴う形（受託・共同研究）になる場合は、規模と時期を別途ご相談させてください。</strong>'''),
    # 「単独で進めます」の行を削除
    ('''      <div class="row">
        <span class="h">応募は単独で進めます</span>
        <span class="t">両テーマとも、<strong>貴協会のご協力が無くても提出でき、プロトタイプ開発まで進められる</strong>状態にあります。ご協力でよくなるのは精度と説得力であって、成否ではありません。</span>
      </div>
''', ''),
    ('    2026年8月13日 第21版／ 作成: 株式会社GRID　／　取扱い: 面談での画面共有のみ',
     '    2026年8月13日／ 作成: 株式会社GRID　／　取扱い: 貴協会内でのご検討にご利用ください'),
    ('一般財団法人日本気象協会の気象コンサルティング顧客', '貴協会の気象コンサルティング顧客'),

    # ---- 社内向けの呼称 → 対外的な呼称 ----
    ('提出物に書いた 0.92 とほぼ一致する水準', '応募提案書に書いた 0.92 とほぼ一致する水準'),
    ('title="提出物の公表値 0.92"', 'title="応募提案書の公表値 0.92"'),
    ('いずれも提案書にもそのまま書いています。', 'いずれも応募提案書にそのまま書いています。'),
    ('提出物が書いている 36.0 → 7.7 K は', '応募提案書に書いている 36.0 → 7.7 K は'),

    # ---- 出所欄: 社内のファイルパス・スクリプト名を落とし、何から出た値かを日本語で書く ----
    ('20_theme1_保温劣化監視/12_提出版_様式4.md（②課題・⑤実用化）／07_PoC中間結果.md／poc1_results.json（signals ＝ +1 K を置いたときの輝度温度への写り）',
     '応募提案書（②課題・⑤実用化）／自前計算（+1 K を置いたときの輝度温度への写り）'),
    ('poc1_results.json（budget, signals）／poc5_results.json（band_physics ＝ 実帯域3.7–4.95µmでの再計算）／poc6_results.json（sibling_noise_vs_distance）。',
     '自前計算（誤差バジェットと信号／実帯域3.7–4.95µmでの再計算／兄弟差分σの離隔距離依存）。'),
    ('''<span class="src">20_theme1_保温劣化監視/poc/data/*_ST_B10_keihin.tif（Landsat Collection 2 L2 の ST_B10 ＝ 放射率補正済みの地表温度。DN×0.00341802+149.0 [K]。TIRS原分解能100 m→30 m格子）。
              AOIは poc4_pipeline.py の AOIS と同一（±数百mの概略）。表示の物差しは各シーンの2〜98パーセンタイル、全景パネルは2×2平均に間引いて表示</span>''',
     '''<span class="src">Landsat Collection 2 L2 の ST_B10（放射率補正済みの地表温度。DN×0.00341802+149.0 [K]。TIRS原分解能100 m→30 m格子）。
              AOIは±数百mの概略。表示の物差しは各シーンの2〜98パーセンタイル、全景パネルは2×2平均に間引いて表示</span>'''),
    ('''<span class="src">poc4_results_real.json（spread_K, series_vs_urban_ref_K ＝ 鶴見区参照面・全14シーン有効）。
          集約はAOI内の10–90パーセンタイルのトリム平均。生成は 40_scripts/make_shiryo_realdata_figs.py の fig_t1_diff()。''',
     '''<span class="src">自前計算（実Landsat 14シーン・鶴見区参照面。全14シーンが有効）。
          集約はAOI内の10–90パーセンタイルのトリム平均。'''),
    ('<p class="src">poc1_results.json ／ poc3_results.json ／ poc4_results_real.json（実Landsat 14シーン・鶴見区参照面）／ poc6_results.json ／ poc7_results.json</p>',
     '<p class="src">いずれも自前計算（誤差バジェット／実気象2020–2025／実Landsat 14シーン・鶴見区参照面／実Landsat・代用資産11,422個／モンテカルロ160対160）</p>'),
    ('''<span class="src">30_theme2_ライフライン復旧/01_検討経緯.md 8.4〜8.6節（蔵王火山噴火緊急減災対策砂防計画 表2-13/2-14 からの自前導出）／
          30_theme2_ライフライン復旧/poc/src/t2_damage_value.py（濁川の諸元）／気象庁の観測所一覧からの自前集計</span>''',
     '''<span class="src">蔵王火山噴火緊急減災対策砂防計画 表2-13/2-14 からの自前導出（濁川の諸元を含む）／
          気象庁の観測所一覧からの自前集計</span>'''),
    ('<span class="src">01_検討経緯.md 8.4〜8.7節（一次資料）／t2_return_period.json（vs_current_practice）</span>',
     '<span class="src">蔵王火山噴火緊急減災対策砂防計画ほか一次資料／自前計算（現行手法との比較）</span>'),
    ('''<span class="src">t2_snowmap_circle_r3km.json（円_半径3km.年別 ＝ 画素中央値・決定率）／t2_snowmap_results.json（years.*.dates, gap_median_days。<strong>「観測日 N 日」は dates を日付でユニーク化した数</strong>）／
          poc/data/snowmap/snow_doy_*.npy を 40_scripts/make_shiryo_realdata_figs.py で描画。円の集計は 30_theme2_ライフライン復旧/poc/src/t2_snowmap_circle.py。''',
     '''<span class="src">自前計算（火口から半径3 kmの円での画素中央値・決定率、および年別の観測日と挟み込み間隔。<strong>「観測日 N 日」は観測日を日付でユニーク化した数</strong>）。''' ),
    ('<span class="n">poc6_results.json（operating_point・実Landsat・ランク1季節モデル後）</span>',
     '<span class="n">自前計算（実Landsat・ランク1季節モデル後の運用点）</span>'),
    ('<span class="n">poc7_results.json（+1 K・160対160・ブートストラップ90%区間）</span>',
     '<span class="n">自前計算（モンテカルロ +1 K・160対160・ブートストラップ90%区間）</span>'),
    ('<span class="n">t2_meltout_accuracy.json（実測係数 0.217）／t2_return_period.json（信号 7.1日）</span>',
     '<span class="n">自前計算（間引き実験による実測係数 0.217／年々変動の信号 7.1 日）</span>'),
    ('<p class="src">t2_snowmap_results.json ／ t2_snowmap_circle_r3km.json（火口半径3kmの円での集計）／ t2_meltout_accuracy.json ／ t2_return_period.json</p>',
     '<p class="src">いずれも自前計算（消雪日マップ9年分／火口から半径3 kmの円での集計／間引き実験／ブートストラップ4,000反復）</p>'),
    ('''    テーマ①: poc1_results.json（誤差バジェット）／poc3_results.json（実気象2020-2025）／poc4_results_real.json（実Landsat 14シーン）／poc6_results.json（実Landsat・代用資産11,422個）／poc7_results.json（モンテカルロ160対160）<br>
    テーマ②: t2_snowmap_results.json（消雪日マップ9年）／t2_snowmap_circle_r3km.json（火口半径3kmの円での集計）／t2_meltout_accuracy.json（間引き実験）／t2_return_period.json（ブートストラップ4,000反復）<br>''',
     '''    テーマ①: 誤差バジェット／実気象2020–2025／実Landsat 14シーン／実Landsat・代用資産11,422個／モンテカルロ160対160<br>
    テーマ②: 消雪日マップ9年分／火口から半径3 kmの円での集計／間引き実験／ブートストラップ4,000反復<br>'''),
]

for old, new in REPL:
    n = s.count(old)
    if n < 1:
        sys.stderr.write("!! %d hits: %r\n" % (n, old[:70]))
        sys.exit(1)
    s = s.replace(old, new)

# タイトル差し替え
s = s.replace("<title>検討中の2テーマと、残っている不確定項 — 日本気象協会さまへのご説明</title>",
              "<title>検討中の2テーマと、残っている不確定項 — 日本気象協会さまへのご説明（株式会社GRID）</title>", 1)

# 単独のHTMLとして開けるように包む（charset が無いと文字化けする）
head = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  img, svg { display: block; max-width: 100%; }
</style>
"""
# <title> と <style> を head に入れ、共有SVG定義から後ろを body に置く
i = s.index("<!-- ==== 図で共有する定義")
headpart, bodypart = s[:i], s[i:]
out = head + headpart + "</head>\n<body>\n" + bodypart + "\n</body>\n</html>\n"

open(DST, "w", encoding="utf-8").write(out)
print("wrote", DST, len(out))
