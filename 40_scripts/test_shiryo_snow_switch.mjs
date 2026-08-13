#!/usr/bin/env node
// 説明資料（60_shiryo/日本気象協会_ご説明.html）の図6（旧図9）「消雪日マップの年の切り替え」を検査する。
//
//   node 40_scripts/test_shiryo_snow_switch.mjs
//
// なぜ要るか: この資料のレビューア（.claude/agents/nedo-shiryo-reviewer.md）は
// 静的な突合しかできず、JSの実挙動は職掌外である。ブラウザ側も、
//   - Claude Code の Browser pane は file:// を script-src 'none' で開くので JS が動かない
//   - 公開後の Artifact は cross-origin の iframe なので中の DOM に手が届かない
// という事情で実ページの操作検査ができない。そこで最小のDOMシムを当てて分岐だけを見る。
//
// 検査するのは「どのidが inline/none になるか」だけで、見た目は見ない。
// **資料に実在するidを読んで当てる**ので、idの綴り間違いはここで落ちる。
import fs from "node:fs";
import path from "node:path";

const ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const html = fs.readFileSync(path.join(ROOT, "60_shiryo/日本気象協会_ご説明.html"), "utf8");

const m = html.match(/\/\* -+ 図6: 消雪日マップの年の切り替え[\s\S]*?\n  \}\)\(\);/);
if (!m) { console.error("図6の切り替えJSが見つからない（節のコメントを変えたら、この正規表現も直す）"); process.exit(2); }
const ids = [...new Set([...html.matchAll(/id="(snow[A-Za-z0-9]+)"/g)].map((x) => x[1]))];
const buttons = [...html.matchAll(/data-y="([^"]+)"/g)].map((x) => x[1]);
const YEARS = buttons.filter((b) => b !== "row3");

// ---- 最小DOMシム（display と aria-pressed だけ持つ） ----
const el = (id) => ({ id, style: { display: "" }, _a: {},
  setAttribute(k, v) { this._a[k] = v; }, getAttribute(k) { return this._a[k] ?? null; } });
const store = new Map(ids.map((i) => [i, el(i)]));
const btnEls = buttons.map((y) => {
  const b = el("btn" + y);
  b.setAttribute("data-y", y);
  b.closest = (sel) => (sel.includes("button") ? b : null);
  return b;
});
const steps = store.get("snowSteps") ?? el("snowSteps");
store.set("snowSteps", steps);
steps.querySelectorAll = () => btnEls;
let handler = null;
steps.addEventListener = (t, f) => { if (t === "click") handler = f; };
global.document = { getElementById: (id) => store.get(id) ?? null };

eval(m[0]);   // 対象のJSをそのまま評価する（書き写さない。書き写すと本体とずれる）

const snap = () => ({
  row3: store.get("snowRow3").style.display,
  one: store.get("snowOne").style.display,
  year: YEARS.filter((y) => store.get("snowY" + y)?.style.display === "inline"),
  ring: YEARS.filter((y) => store.get("snowRing" + y)?.style.display === "inline"),
  pressed: btnEls.filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.getAttribute("data-y")),
});
let ng = 0;
const check = (name, got, want) => {
  const a = JSON.stringify(got), b = JSON.stringify(want);
  if (a !== b) { ng++; console.log(`  NG ${name}\n     得た ${a}\n     期待 ${b}`); }
  else console.log(`  ok ${name}`);
};
const ROW3 = { row3: "inline", one: "none", year: [], ring: [], pressed: ["row3"] };
const click = (y) => handler({ target: btnEls.find((b) => b.getAttribute("data-y") === y) });

console.log(`図6の年の切り替え（${YEARS.length}年ぶんを焼き込んでいる）`);
check("既定は3年の並置", snap(), ROW3);
for (const y of YEARS) check(`${y} を押す`, (click(y), snap()), { row3: "none", one: "inline", year: [y], ring: [y], pressed: [y] });
check("3年を並べるに戻す", (click("row3"), snap()), ROW3);
handler({ target: { closest: () => null } });
check("ボタン以外を押しても状態が変わらない", snap(), ROW3);

// 焼き込みの取りこぼし（年ボタンに対応する画像・輪が無い）を機械的に見る
const missing = YEARS.filter((y) => !ids.includes("snowY" + y) || !ids.includes("snowRing" + y));
check("全ボタンに対応する図と輪がある", missing, []);

console.log(ng ? `\n失敗 ${ng} 件` : "\n全件通過");
process.exit(ng ? 1 : 0);
