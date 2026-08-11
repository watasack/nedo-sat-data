import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const outputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_drone_port";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const answers = workbook.worksheets.getItem("提出用回答案");
const currentQ10 = answers.getRange("D8").values[0][0];
const proposalMarker = "\n\n④ ";
const commonMarker = "\n\nいずれの案でも、";
const proposalIndex = currentQ10.indexOf(proposalMarker);
const markerIndex = currentQ10.lastIndexOf(commonMarker);
if (proposalIndex < 0 || markerIndex < 0 || proposalIndex >= markerIndex) {
  throw new Error("Q10の④または共通段落を特定できませんでした。");
}

const siteLocationProposal =
  "\n\n④ 災害時の仮設ドローンポート配置最適化\n平時に自治体等が登録した学校、公共施設、空き地等の候補地に対し、発災後の衛星データから道路寸断、浸水、孤立地域等の状況を把握し、限られた仮設ドローンポート、充電設備、機体をどこに配置すれば、医薬品・物資輸送、状況確認、通信中継を効率的にカバーできるかを最適化します。撮像時刻、飛行可能範囲、航続距離、電源、拠点開設コスト等の制約を考慮し、候補拠点の開設優先順位、担当エリア、機体・物資の配分を提示します。衛星画像のみで離着陸可否を自動判定するのではなく、事前登録候補地を対象に発災後の状況変化を反映する意思決定支援として、実証可能性を確保します。";

const revisedQ10 =
  currentQ10.slice(0, proposalIndex) +
  siteLocationProposal +
  currentQ10.slice(markerIndex);

answers.getRange("D8").values = [[revisedQ10]];
answers.getRange("E8").formulas = [["=LEN(D8)"]];
answers.getRange("F8").values = [[
  "①災害時輸送・復旧、②電柱AIP、③広域除排雪に加え、④を仮設ドローンポート配置へ変更。事前登録候補地と発災後の衛星データを用い、開設優先順位、担当エリア、機体・物資配分を提示する現実的な意思決定支援とした。",
]];
answers.getRange("A8:F8").format.rowHeight = 430;

const items = workbook.worksheets.getItem("応募項目一覧");
items.getRange("F8:G8").values = [[
  "①災害時のマルチモーダル輸送・復旧計画、②電柱AIP、③広域除排雪、④災害時の仮設ドローンポート配置の4案を提示。④は衛星で把握した道路寸断・浸水・孤立状況を基に、候補拠点の開設と機体・物資配分を最適化する。",
  "④は衛星画像から離着陸地を新規発見するのではなく、平時に登録した候補地を対象とする。発災後の実被害を反映し、開設優先順位・担当エリア・機体配分を比較する意思決定支援として実証可能性を確保する。",
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

for (const [sheetId, range] of [
  ["提出用回答案", "A8:F8"],
  ["応募項目一覧", "A8:G8"],
]) {
  const result = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    maxChars: 22000,
    tableMaxRows: 3,
    tableMaxCols: 7,
    tableMaxCellChars: 12000,
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
