import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const outputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド_改訂版.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_revised";

const q10 =
  "本マッチングを通じてパートナーとチームを組成し、「衛星・地上データを用いた災害時のマルチモーダル輸送・インフラ復旧計画の動的最適化」をNEDO Challengeに共同提案したいと考えています。SAR・光学衛星等による浸水、土砂災害、地盤変位、道路閉塞、港湾周辺の変状等の解析結果を、PLATEAU、道路・港湾・交通情報、気象、車両・船舶・倉庫・人員等の地上データと統合します。その上で、道路・港湾の利用可否や処理能力の変化を制約条件として、緊急物資、復旧要員・機材、代替輸送ルート、陸海の輸送モード、拠点配置を動的に最適化し、複数シナリオを比較できる意思決定支援システムを構築します。当社は課題整理、数理モデル化、シミュレーション・最適化エンジン、業務アプリケーション開発を担い、マッチング先には衛星解析、現場データ、実証フィールド、現場評価のいずれかを担っていただく想定です。応募段階では対象地域・災害種別、利用データ、役割分担、評価指標、開発計画を共同で具体化し、一次審査通過後はプロトタイプを開発して過去災害データによる再現検証と現場評価を行います。衛星解析を検知・可視化で終わらせず、限られた輸送能力と復旧資源の具体的な配分判断へつなげ、対応時間の短縮、供給途絶の抑制、現場負荷の軽減を目指します。コンテスト後も、共同研究、実証拡大、サービス化へ継続して取り組みたいと考えています。";

const q11 =
  "【共同応募に関する必須要件】\n・本マッチングを、NEDO Challengeへのチーム応募を具体化する機会と捉え、応募期限までに提案内容、応募体制、代表者、役割分担、開発・評価計画を協議できる方。\n・以下の①または②の専門性・環境を提供できる大学、研究機関、企業、自治体・事業者の方。\n①衛星データ技術：SARまたは光学衛星を用いた浸水・土砂災害・地盤変位・道路閉塞・構造物／周辺環境の変化検知に知見があり、解析結果の精度、不確実性、更新頻度を説明できること。\n②現場・データ：道路、港湾、物流、自治体、防災、インフラ管理の実務知見を持ち、対象施設・地域の台帳、交通・運用実績、過去災害・対応記録、制約条件等を可能な範囲で共有し、実証フィールドまたは現場評価に協力できること。\n\n【歓迎要件】\n・PLATEAU、GIS、地上センサ、気象・交通データとの統合、被害推定、データAPI化に知見がある方。\n・コンテスト後の共同研究・事業化も見据え、知財、データ利用条件、成果公表等を協議できる方。\n\n【想定する役割と進め方】\n当社は課題整理、数理モデル化、シミュレーション・最適化エンジン、業務アプリケーション、実証設計を担当します。マッチング先には衛星解析または現場知見・検証環境の提供を期待します。初期は週1回・60分程度のオンライン打合せと各者1名以上の担当者配置を目安に、応募期限までに共同提案の骨子と実施体制をまとめることを希望します。";

const q12 =
  "正式な共同応募に先立ち、初回協議で提案テーマ、応募代表者・参加メンバー、各者の役割、応募書類の作成分担、一次審査通過後に投入可能な人員・開発環境を確認したいと考えています。その上で、①背景知財と共同開発で生じる成果知財の帰属・利用条件、②データの利用目的・保管場所・アクセス権・削除方法、③成果公表・対外発表、④開発・実証費用の負担、⑤コンテスト後の共同研究・事業化方針を協議できれば幸いです。施設情報、運用データ、未公開アルゴリズム等の機密情報を共有する場合は、共有前に必要に応じて相互の秘密保持契約（NDA）を締結します。当社はプロジェクト責任者、最適化／AI担当、データ・アプリケーション担当を中心とする体制を想定し、衛星解析担当および現場・評価担当と一体で進めます。機微なインフラ情報については、匿名化・集約化や閉域／指定環境での解析にも対応を検討します。共同応募、データ提供、対外公表は各社・各機関の社内手続きと承認を前提とし、マッチング後、応募期限を踏まえて速やかに合意事項を整理したいと考えています。";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const answers = workbook.worksheets.getItem("提出用回答案");
answers.getRange("D8:D10").values = [[q10], [q11], [q12]];
answers.getRange("F8:F10").values = [
  [
    "本制度の目的に合わせ、マッチング先とのチーム組成とNEDO Challengeへの共同提案を冒頭で明示。応募時と一次審査通過後の進め方、各者の役割も具体化。",
  ],
  [
    "専門性だけでなく、共同応募の意思、応募期限までに決める事項、想定役割・コミットメントを明示し、チーム候補が適合性を判断しやすく整理。",
  ],
  [
    "一般的な共同研究条件に加え、応募代表者、書類分担、一次審査通過後の体制、費用負担など、共同応募前に合意すべき事項を明確化。",
  ],
];
answers.getRange("A13").values = [[
  "提出前に確認：①衛星データの直接利用実績が別途あればQ7に追記、②事例数値の外部開示可否、③Q10の対象災害・実証地域、④共同応募の代表者・参加メンバー・応募書類分担、⑤Q11の週次コミットメント、⑥Q12の社内標準契約・知財・情報セキュリティ要件。",
]];

const items = workbook.worksheets.getItem("応募項目一覧");
items.getRange("F8:F10").values = [
  [
    "マッチング先とチームを組成し、災害時の道路・港湾の利用可否把握と、陸海複合輸送・復旧資源配分の動的最適化を本コンテストへ共同提案する。",
  ],
  [
    "共同応募の意思を前提に、衛星解析、現場・データ、GIS／データ連携の専門性、応募期限までの役割分担・体制検討へのコミットメントを明記する。",
  ],
  [
    "共同応募前に、代表者・応募書類分担・一次審査通過後の体制・費用、NDA、データ管理、知財、成果公表、社内承認を整理する。",
  ],
];
items.getRange("A13").values = [[
  "プログラム設計上の重要ポイント：本制度は、マッチング後に直接交渉し、チームを組成してNEDO Challengeへ応募することを主目的とし、その先の共同研究・事業化につなげるものです。回答では、共同提案の内容、各者の役割、応募期限までに決める事項、一次審査通過後の開発・評価体制まで示すと、相手が参加可否を判断しやすくなります。",
]];

const alternatives = workbook.worksheets.getItem("代替案・確認事項");
alternatives.getRange("A12:F12").values = [[
  "改善提案",
  "Q10〜Q12",
  "マッチングの目的を「一般的な共同研究先探し」ではなく「本コンテストへの共同応募に向けたチーム組成」と明示する。",
  "共同提案、応募体制、役割分担、応募後の開発・評価計画を一貫して記載。",
  "反映済",
  "公式資料のプロセス（直接交渉→チーム組成→コンテスト応募→共同研究）と回答案の位置づけを一致させる。",
]];

const sources = workbook.worksheets.getItem("出典・根拠");
sources.getRange("B12:D12").values = [[
  "画像1〜3",
  "コンテスト参加を促す制度であり、マッチング後は直接交渉し、チーム組成・コンテスト応募・その先の共同研究へ進むプロセス。",
  "全体、特にQ10〜Q12",
]];

await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of [
  "応募項目一覧",
  "提出用回答案",
  "代替案・確認事項",
  "出典・根拠",
]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1.25,
    format: "png",
  });
  await fs.writeFile(
    `${previewDir}/${sheetName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const check = await workbook.inspect({
  kind: "table",
  sheetId: "提出用回答案",
  range: "A8:F10",
  include: "values,formulas",
  maxChars: 12000,
  tableMaxRows: 10,
  tableMaxCols: 6,
  tableMaxCellChars: 2500,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 4000,
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
