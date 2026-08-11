import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const outputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド_Q9修正版.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_q9_balance";

const q9 =
  "株式会社グリッドは、社会インフラ領域における数理最適化を中核的な強みとする技術企業です。電力、海運、物流、製造、都市交通等の現場で培ったドメイン知識を基に、需要予測、シミュレーション、デジタルツイン等も組み合わせ、複雑な業務制約や判断基準、KPIを反映した実行可能な計画を導きます。私たちの強みは、最適化エンジンの開発にとどまらず、現場データの整理・統合、シナリオ分析、結果の可視化、業務アプリケーション開発、運用定着まで一気通貫で支援できる点です。コスト、リスク、安定供給、環境負荷等のトレードオフを分かりやすく示し、「何を、いつ、どの順番で実行するか」という意思決定につなげます。共同研究では、衛星解析の成果を輸送、配船、点検、設備投資、復旧計画等の目的関数・制約条件へ落とし込み、現場で使える計画へ変換する役割を担えます。課題設定からPoC、アルゴリズム・画面開発、実証評価、社会実装まで、異なる専門性を持つパートナーと伴走したいと考えています。";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const answers = workbook.worksheets.getItem("提出用回答案");
answers.getRange("D7").values = [[q9]];
answers.getRange("E7").formulas = [["=LEN(D7)"]];
answers.getRange("F7").values = [[
  "数理最適化を中核的な強みとして明確にしつつ、需要予測、シミュレーション、デジタルツイン、データ統合、可視化、業務アプリケーション、運用定着まで対応できる実装力を併記。",
]];
answers.getRange("A7:F7").format.rowHeight = 250;

const items = workbook.worksheets.getItem("応募項目一覧");
items.getRange("F7:G7").values = [[
  "数理最適化を主軸に据え、需要予測・シミュレーション・デジタルツイン等を組み合わせ、データ統合から可視化・業務アプリケーション・運用定着まで一気通貫で支援できる点を記載する。",
  "「何でもできるAI企業」という曖昧な訴求を避け、衛星解析を現場で実行可能な計画へ変換できることを差別化の軸にする。一方、数理最適化専業には見えない構成とする。",
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
  ["提出用回答案", "A7:F8"],
  ["応募項目一覧", "A7:G8"],
]) {
  const result = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    maxChars: 16000,
    tableMaxRows: 4,
    tableMaxCols: 7,
    tableMaxCellChars: 6000,
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
