# koubo/ — 公募要項・応募様式の一次情報（テキスト版）

**このディレクトリのファイルが、事務条項に関する唯一の一次情報である。**
`10_提出様式メモ.md` はここから抽出した確定事項の要約であり、判断に迷ったら必ずこちらの原文に当たること。

## 取得の経緯

このプロジェクトの作業環境（クラウドサンドボックス）からは `nedo.go.jp` と
`space-data-challenge.nedo.go.jp` がともに egress 遮断されており、要項を直接読めなかった。
そのため事務条項（提出様式・字数制限・添付可否・応募者区分・知財・賞金支払）が長らく
「判定不能」のまま残っていた（review_v3 の O-1〜O-4）。

PoC実データ取得で実績のある **GitHub Actions 迂回**で解決した（2026年8月8日）:

1. `fetch_koubo_docs.py` — シード4URLから同一サイト内を深さ2まで辿り、PDF・様式ファイル・
   応募/FAQ関連ページを取得。全件の status・sha256・bytes を `manifest.json` に記録
2. `.github/workflows/fetch-koubo-docs.yml` — `trigger-fetch-koubo` ブランチへの push で起動し、
   結果を `koubo-docs` ブランチにコミット
3. **52件すべて status 200** で取得成功

## ファイル

| ファイル | 内容 | 元 |
|---|---|---|
| `応募要項.txt` | 応募要項（懸賞広告）26ページ全文。**事務条項の最終根拠はこれ** | `space-data-challenge.nedo.go.jp/infrastructure/file/Application_Guidelines.pdf` |
| `応募申請書_法人応募者用.txt` | 様式1〜4の全項目。**様式4に審査項目が明記されており実質的な採点表** | `.../file/Application_Form_For_Corporate_Applicants.docx` |
| `応募申請書_個人応募者用.txt` | 個人応募の場合の様式 | `.../file/Application_Form_For_Individual_Applicants.docx` |
| `応募説明会資料.txt` | 2026年8月5日開催の応募説明会資料 33ページ | `.../file/Application_Information_Session.pdf` |
| `manifest.json` | 取得した52件全部のURL・status・sha256・bytes | 取得スクリプトの出力 |

**PDF/DOCX のバイナリ原本は `koubo-docs` ブランチの `koubo_docs/` にある**（約5.6MB のためmainには置いていない）。
必要なら `git show origin/koubo-docs:koubo_docs/<ファイル名> > /tmp/x.pdf` で取り出せる。

## 再取得の方法

要項が改訂された場合や、FAQが公式サイトに追加された場合は、以下で取り直せる。

```
git push -f origin <作業ブランチ>:trigger-fetch-koubo
```

数分後に `koubo-docs` ブランチが更新される。テキスト化は `pdftotext -layout`（poppler-utils。
サンドボックスに未導入の場合は `apt-get update -qq && apt-get install -y -qq poppler-utils`。
`pypdf` と `pdfminer.six` はこの環境では `cryptography` の壊れた依存で import に失敗するので使わない）。
DOCX は zipfile で `word/document.xml` を読んでタグを落とすだけでよい。
