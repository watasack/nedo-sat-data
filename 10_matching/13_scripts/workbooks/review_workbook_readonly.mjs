import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const overview = await workbook.inspect({
  kind: "workbook,sheet",
  include: "id,name",
  maxChars: 6000,
});
console.log(overview.ndjson);

for (const [sheetId, range] of [
  ["応募項目一覧", "A1:G13"],
  ["提出用回答案", "A1:F13"],
  ["代替案・確認事項", "A1:F12"],
  ["出典・根拠", "A1:E20"],
]) {
  const result = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    maxChars: 45000,
    tableMaxRows: 25,
    tableMaxCols: 8,
    tableMaxCellChars: 12000,
  });
  console.log(result.ndjson);
}

const formulas = await workbook.inspect({
  kind: "formula",
  maxChars: 10000,
  options: { maxResults: 100 },
});
console.log(formulas.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
  maxChars: 4000,
});
console.log(errors.ndjson);
