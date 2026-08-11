import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/マッチングプログラム応募回答案_株式会社グリッド.xlsx";
const previewDir =
  "/Users/abe.shuhei/Documents/NEDO_SatData/04_outputs/nedo_matching_program/previews_before_q9_balance";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 8000,
  tableMaxRows: 30,
  tableMaxCols: 8,
  tableMaxCellChars: 500,
});
console.log(summary.ndjson);

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 3000,
});
console.log(sheets.ndjson);

const sources = await workbook.inspect({
  kind: "table",
  sheetId: "出典・根拠",
  range: "A1:E20",
  maxChars: 12000,
  tableMaxRows: 20,
  tableMaxCols: 8,
  tableMaxCellChars: 500,
});
console.log(sources.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const name of [
  "応募項目一覧",
  "提出用回答案",
  "代替案・確認事項",
  "出典・根拠",
]) {
  try {
    const preview = await workbook.render({
      sheetName: name,
      autoCrop: "all",
      scale: 1.25,
      format: "png",
    });
    await fs.writeFile(
      `${previewDir}/${name}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  } catch (error) {
    console.error(`render failed for ${name}:`, error.message);
  }
}
