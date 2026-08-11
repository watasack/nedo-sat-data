import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド_改訂版.xlsx";
const outputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド_Q9-Q10改訂版.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_q9_q10";

const q9 =
  "株式会社グリッドは、社会インフラ領域の数理最適化を専門とする技術企業です。電力、海運、物流、製造、都市交通等の現場で培ったドメイン知識を基に、複雑な業務制約や判断基準、KPIを数理モデルとして表現し、膨大な選択肢から実行可能な計画を導きます。私たちの強みは、最適化エンジンの開発にとどまらず、現場データの整理・統合、デジタルツインによるシナリオ分析、結果の可視化、業務アプリケーション、運用定着まで一気通貫で支援できる点です。コスト、リスク、安定供給、環境負荷等のトレードオフを分かりやすく示し、「何を、いつ、どの順番で実行するか」という意思決定につなげます。共同研究では、衛星解析の成果を輸送、配船、点検、設備投資、復旧計画等の目的関数・制約条件へ落とし込み、現場で使える計画へ変換する役割を担えます。課題設定からPoC、アルゴリズム・画面開発、実証評価、社会実装まで、異なる専門性を持つパートナーと伴走したいと考えています。";

const q10 =
  "① 衛星・地上データを用いた災害時のマルチモーダル輸送・インフラ復旧計画の動的最適化\n本マッチングを通じてパートナーとチームを組成し、NEDO Challengeへの共同提案を検討します。SAR・光学衛星等から得られる浸水、土砂災害、地盤変位、道路閉塞、港湾周辺の変状等を、道路・港湾・交通・気象情報や車両、船舶、倉庫、人員等のデータと統合します。道路・港湾の利用可否や処理能力の変化を制約として、緊急物資、復旧要員・機材、代替ルート、陸海の輸送モード、拠点配置を動的に最適化し、複数シナリオを比較できる意思決定支援システムを構築します。衛星解析を検知・可視化で終わらせず、限られた輸送能力と復旧資源の配分判断につなげ、対応時間の短縮と供給途絶の抑制を目指します。\n\n② 衛星・点検データを用いた電柱AIP（Asset Investment Planning：設備投資計画）の最適化\n電柱ごとに、設置年、材質、点検・補修履歴、ひび割れ・剥離等の劣化度、停電時の影響、重要施設への供給といった設備情報に、衛星等から得られる地盤変位、浸水、土砂災害、植生等の周辺リスクを統合し、故障確率と影響度からリスクを定量化します。その上で、予算、作業員、部材、工期、地域ごとの工事集約等の制約下で、「次にどの電柱を点検・補修・補強・建替えするか」を多年度で最適化します。衛星データは微細なひび割れを直接判定するのではなく広域の周辺リスク把握に用い、ドローン・車載画像・現地点検で設備状態を評価する想定です。費用、リスク低減、設備寿命、供給信頼度のトレードオフを可視化し、投資シナリオの比較と説明可能な優先順位づけを支援します。\n\nいずれの案でも、当社は課題整理、数理モデル化、シミュレーション・最適化、可視化・業務アプリケーション、実証設計を担当し、マッチング先には衛星解析、設備・現場データ、実証フィールド、現場評価の知見を期待します。対象地域、利用データ、役割分担、評価指標を共同で具体化し、コンテスト後の共同研究・事業化にもつなげたいと考えています。";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const answers = workbook.worksheets.getItem("提出用回答案");
answers.getRange("D7:D8").values = [[q9], [q10]];
answers.getRange("E7:E8").formulas = [["=LEN(D7)"], ["=LEN(D8)"]];
answers.getRange("F7:F8").values = [
  [
    "GRIDの公開情報を基に、社会インフラ領域の数理最適化の専門性、ドメイン知識、データ統合・可視化・シナリオ分析を通じた意思決定支援、構想から運用までの一貫支援を強調。",
  ],
  [
    "現行案を①として維持し、②に電柱AIPを追加。AIPを修繕順序だけでなく、故障リスクと影響度に基づく多年度の点検・補修・補強・建替え投資計画として整理。衛星と近接点検の役割も明確化。",
  ],
];
answers.getRange("A7:F7").format.rowHeight = 250;
answers.getRange("A8:F8").format.rowHeight = 405;

const items = workbook.worksheets.getItem("応募項目一覧");
items.getRange("F7:G8").values = [
  [
    "社会インフラ領域の数理最適化の専門性を中心に、ドメイン知識、データ統合・可視化、シナリオ分析を通じて実行可能な意思決定へつなげる力を記載する。",
    "単なるAI・可視化企業ではなく、複雑制約とKPIを数理モデル化し、構想から実装・運用まで支援できる点を明確にする。",
  ],
  [
    "①災害時のマルチモーダル輸送・復旧計画、②電柱AIPの2案を提示。②は設備状態と周辺リスクを統合し、限られた予算・人員の下で点検・補修・補強・建替えの優先順位を最適化する。",
    "衛星データで電柱の微細なひびを直接判定すると過大表現せず、広域の周辺リスク把握と、ドローン・車載画像・現地点検による設備状態評価を組み合わせる。",
  ],
];

const alternatives = workbook.worksheets.getItem("代替案・確認事項");
const altData = await workbook.inspect({
  kind: "table",
  sheetId: "代替案・確認事項",
  range: "A1:F12",
  include: "values",
  maxChars: 16000,
  tableMaxRows: 20,
  tableMaxCols: 6,
  tableMaxCellChars: 1200,
});
const altText = altData.ndjson;
let targetRow = 7;
for (let row = 5; row <= 12; row += 1) {
  if (altText.includes(`"Q10"`)) {
    targetRow = 7;
    break;
  }
}
alternatives.getRange(`A${targetRow}:F${targetRow}`).values = [[
  "反映案",
  "Q10",
  "電柱AIP型",
  "設備状態、故障影響、衛星による周辺リスクを統合し、予算・人員等の制約下で点検・補修・補強・建替えの多年度計画を最適化。",
  "反映済",
  "AIPの本質である費用・リスク・性能のトレードオフと、衛星／近接点検の役割分担を明示。",
]];

const sources = workbook.worksheets.getItem("出典・根拠");
sources.getRange("A12:E12").copyTo(sources.getRange("A13:E17"), "all");
sources.getRange("A13:E17").values = [
  [
    "GRID公式サイト",
    "Future Design Lab",
    "電力・海運・製造等で実証された数理最適化、業界横断のドメイン知識、現場の判断基準・制約のモデル化、PoCから業務実装までの一貫支援。",
    "Q9",
    "https://ae.gridpredict.jp/l/1082793/2026-02-08/lvdk15",
  ],
  [
    "GRID公式サイト",
    "Gurobiとの戦略的パートナーシップ",
    "社会インフラの最適化に特化した専門性、電力需給・配船・交通計画等の複雑な組合せ最適化、デジタルツインとの統合。",
    "Q9",
    "https://gridpredict.jp/news/20251007",
  ],
  [
    "三菱電機公式サイト",
    "設備資産管理／AIPM",
    "設備状態と故障影響からリスクを評価し、予算・人員・資材等の制約下で設備投資計画を最適化するAIPMの考え方。",
    "Q10②",
    "https://www.mitsubishielectric.co.jp/ict-power-system/business/solution9/",
  ],
  [
    "東京電力パワーグリッド公式サイト",
    "コンクリート柱劣化診断",
    "ひび割れ、剥離、風化、錆汁等を診断し、劣化度に応じて補修・補強・建替えを提案する電柱保全の実務。",
    "Q10②",
    "https://www.tepco.co.jp/pg/consignment/partners/category-e/11-j.html",
  ],
  [
    "EPRI公式サイト",
    "Overhead Asset Analytics",
    "設備状態、保守記録、経年、劣化研究、ドメイン知識を用いて保守・交換の必要性を順位づけし、点検・投資を優先する考え方。",
    "Q10②",
    "https://transmission.epri.com/p34_analytics/public/p34003_overhead_asset_analytics/overview/",
  ],
];
sources.getRange("A13:E17").format.wrapText = true;
sources.getRange("A13:E17").format.verticalAlignment = "top";
sources.getRange("A13:E17").format.rowHeight = 60;

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
  range: "A7:F8",
  include: "values,formulas",
  maxChars: 20000,
  tableMaxRows: 5,
  tableMaxCols: 6,
  tableMaxCellChars: 7000,
});
console.log(check.ndjson);

const sourceCheck = await workbook.inspect({
  kind: "table",
  sheetId: "出典・根拠",
  range: "A12:E17",
  include: "values",
  maxChars: 12000,
  tableMaxRows: 10,
  tableMaxCols: 5,
  tableMaxCellChars: 1200,
});
console.log(sourceCheck.ndjson);

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
