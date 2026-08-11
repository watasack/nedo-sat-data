import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const outputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド_除排雪案追加版.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_snow";

const q10 =
  "① 衛星・地上データを用いた災害時のマルチモーダル輸送・インフラ復旧計画の動的最適化\n本マッチングを通じてパートナーとチームを組成し、NEDO Challengeへの共同提案を検討します。SAR・光学衛星等から得られる浸水、土砂災害、地盤変位、道路閉塞、港湾周辺の変状等を、道路・港湾・交通・気象情報や車両、船舶、倉庫、人員等のデータと統合します。道路・港湾の利用可否や処理能力の変化を制約として、緊急物資、復旧要員・機材、代替ルート、陸海の輸送モード、拠点配置を動的に最適化し、複数シナリオを比較できる意思決定支援システムを構築します。衛星解析を検知・可視化で終わらせず、限られた輸送能力と復旧資源の配分判断につなげ、対応時間の短縮と供給途絶の抑制を目指します。\n\n② 衛星・点検データを用いた電柱AIP（Asset Investment Planning：設備投資計画）の最適化\n電柱ごとに、設置年、材質、点検・補修履歴、ひび割れ・剥離等の劣化度、停電時の影響、重要施設への供給といった設備情報に、衛星等から得られる地盤変位、浸水、土砂災害、植生等の周辺リスクを統合し、故障確率と影響度からリスクを定量化します。その上で、予算、作業員、部材、工期、地域ごとの工事集約等の制約下で、「次にどの電柱を点検・補修・補強・建替えするか」を多年度で最適化します。衛星データは微細なひび割れを直接判定するのではなく広域の周辺リスク把握に用い、ドローン・車載画像・現地点検で設備状態を評価する想定です。費用、リスク低減、設備寿命、供給信頼度のトレードオフを可視化し、投資シナリオの比較と説明可能な優先順位づけを支援します。\n\n③ 衛星・地上データを用いた広域除排雪リソースの動的最適化\n衛星による広域の積雪分布・積雪深、気象予報、路面・交通情報、除雪車の位置・稼働状況を統合し、除雪車、作業員、融雪剤をどの地域へ配分するか、どの道路をどの順番で除雪するか、どの雪捨て場へ搬送するかを動的に最適化します。衛星データは道路一本単位の積雪を直接判定するのではなく、観測地点が少ない山間部を含む広域状況の把握と予測補正に利用し、車載・路面センサー等で道路単位の状態を補完します。病院、消防署、避難所、物流拠点等へのアクセス確保、自治体・管理区間を越えた応援車両の配分、ドライバーの勤務、車線数、梯団走行、雪捨て場容量等を制約として、豪雪時の道路啓開時間、走行不能区間、燃料・融雪剤使用量の削減を目指します。\n\nいずれの案でも、当社は課題整理、数理モデル化、シミュレーション・最適化、可視化・業務アプリケーション、実証設計を担当し、マッチング先には衛星解析、設備・現場データ、実証フィールド、現場評価の知見を期待します。対象地域、利用データ、役割分担、評価指標を共同で具体化し、コンテスト後の共同研究・事業化にもつなげたいと考えています。";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const answers = workbook.worksheets.getItem("提出用回答案");
answers.getRange("D8").values = [[q10]];
answers.getRange("E8").formulas = [["=LEN(D8)"]];
answers.getRange("F8").values = [[
  "現行の①災害時輸送・復旧、②電柱AIPに、③広域除排雪を追加。③は衛星を広域の積雪把握と予測補正に用い、道路単位の状態は車載・路面センサーで補完する構成とした。",
]];
answers.getRange("A8:F8").format.rowHeight = 405;

const items = workbook.worksheets.getItem("応募項目一覧");
items.getRange("F8:G8").values = [[
  "①災害時のマルチモーダル輸送・復旧計画、②電柱AIP、③広域除排雪リソースの3案を提示。③は積雪・気象・道路・車両データから、除雪順序と車両・人員・融雪剤の配分を動的に最適化する。",
  "衛星は広域積雪の把握と予測補正に用い、道路一本単位の状態は車載・路面センサー等で補完する。重要施設へのアクセス、応援車両、勤務、梯団走行、雪捨て場容量も制約に含める。",
]];

const alternatives = workbook.worksheets.getItem("代替案・確認事項");
alternatives.getRange("A8:F8").values = [[
  "反映案",
  "Q10",
  "広域除排雪型",
  "衛星・気象・道路・車両データを統合し、除雪車・人員・融雪剤の地域配分、除雪順序、雪捨て場への搬送を動的に最適化。",
  "反映済",
  "衛星は広域状況の把握と予測補正、道路単位は車載・路面センサーで補完。自治体を越えた応援配分や重要施設へのアクセス確保まで扱う。",
]];

const sources = workbook.worksheets.getItem("出典・根拠");
sources.getRange("A17:E17").copyTo(sources.getRange("A18:E20"), "all");
sources.getRange("A18:E20").values = [
  [
    "JAXA公式サイト",
    "積雪・雪氷プロダクト",
    "衛星観測から積雪域、積雪深、積雪水量等の広域情報を提供。除排雪案では道路単位の判定ではなく、広域状況の把握と予測補正に利用する。",
    "Q10③",
    "https://earth.jaxa.jp/ja/data/products/snow-cover/index.html",
  ],
  [
    "米国連邦道路庁（FHWA）",
    "Dynamic Snowplow Routing",
    "車両位置、積雪深、気象、交通等を用い、交通影響を抑える除雪ルートを動的に最適化する考え方。",
    "Q10③",
    "https://ops.fhwa.dot.gov/publications/fhwahop20060/ch5.htm",
  ],
  [
    "国土交通省 PLATEAU",
    "降雪・積雪・融雪シミュレーション",
    "気象・積雪モデルと都市データを用い、除雪優先度や資源配分の判断を支援するユースケース。",
    "Q10③",
    "https://www.mlit.go.jp/plateau/use-case/uc25-01/",
  ],
];
sources.getRange("A18:E20").format.wrapText = true;
sources.getRange("A18:E20").format.verticalAlignment = "top";
sources.getRange("A18:E20").format.rowHeight = 60;

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

for (const [sheetId, range] of [
  ["提出用回答案", "A8:F8"],
  ["代替案・確認事項", "A7:F9"],
  ["出典・根拠", "A17:E20"],
]) {
  const result = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    maxChars: 24000,
    tableMaxRows: 10,
    tableMaxCols: 6,
    tableMaxCellChars: 10000,
  });
  console.log(result.ndjson);
}

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
