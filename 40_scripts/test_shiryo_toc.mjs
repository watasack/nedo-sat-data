#!/usr/bin/env node
// 説明資料（60_shiryo/日本気象協会_ご説明.html）の目次を検査する。
//
//   node 40_scripts/test_shiryo_toc.mjs
//
// 見るのは2つ。
//   (1) 資料内のすべての内部リンク（href="#..."）が実在するidに解決するか。
//       目次は節と図を名前で引くので、図番号を振り直したときに最初に壊れるのがここである。
//   (2) 「いま画面にある節を印す」JSの分岐（markToc）。スクロール位置を差し替えて、
//       画面上から1/3の線がどの節にあるかで aria-current が動くことを確かめる。
//       レビューアはJSを見ない／Browser pane は file:// で script-src none／
//       公開後の Artifact は cross-origin の iframe なので、実ページでは確かめられない。
import fs from "node:fs";
import path from "node:path";

const ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const html = fs.readFileSync(path.join(ROOT, "60_shiryo/日本気象協会_ご説明.html"), "utf8");

let fail = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok " : "  NG ") + msg); if (!cond) fail++; };

// ---- (1) 内部リンクの解決 ----
const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map((x) => x[1]));
const hrefs = [...new Set([...html.matchAll(/href="#([^"]+)"/g)].map((x) => x[1]))];
const dead = hrefs.filter((h) => !ids.has(h));
console.log(`内部リンク ${hrefs.length} 件（うち目次から ${
  [...html.matchAll(/<nav class="toc"[\s\S]*?<\/nav>/g)][0][0].match(/href="#/g).length} 件）`);
ok(dead.length === 0, `参照切れ 0 件${dead.length ? "（" + dead.join(", ") + "）" : ""}`);

// 目次が引いている節と図が、本文側にその順で並んでいるか
const nav = html.match(/<nav class="toc"[\s\S]*?<\/nav>/)[0];
const tocTargets = [...nav.matchAll(/href="#([^"]+)"/g)].map((x) => x[1]);
const posOf = (id) => html.indexOf(`id="${id}"`, html.indexOf("</nav>"));
const positions = tocTargets.map(posOf);
ok(positions.every((p) => p > 0), "目次のすべての行き先が本文にある");
ok(positions.every((p, i) => i === 0 || p > positions[i - 1]),
  "目次の並びが本文の並びと同じ（読み上げる順に置いてある）");

// ---- (2) markToc の分岐 ----
const m = html.match(/\/\* -+ 目次: いま画面にある節を印す[\s\S]*?\n    markToc\(\);\n  \}/);
if (!m) { console.error("目次のJSが見つからない（節のコメントを変えたら、この正規表現も直す）"); process.exit(2); }

const secIds = [...nav.matchAll(/class="sec">\s*\n\s*<a href="#([^"]+)"/g)].map((x) => x[1]);
if (secIds.length < 2) { console.error("目次の節が読めない"); process.exit(2); }

// 最小DOMシム。節の top はテストから差し替える
const tops = new Map(secIds.map((id, i) => [id, i * 1000]));   // 0, 1000, 2000...
const mkLink = (id) => ({
  _a: {}, _href: "#" + id,
  getAttribute(k) { return k === "href" ? this._href : (this._a[k] ?? null); },
  setAttribute(k, v) { this._a[k] = v; },
  removeAttribute(k) { delete this._a[k]; },
});
const links = secIds.map(mkLink);
const secs = new Map(secIds.map((id) => [id, {
  getBoundingClientRect() { return { top: tops.get(id) }; },
}]));

const listeners = [];
const document = {
  querySelectorAll(sel) {
    if (sel === ".toc .sec > a") return links;
    throw new Error("想定外のセレクタ: " + sel);
  },
  getElementById(id) { return secs.get(id) ?? null; },
};
const window = {
  innerHeight: 900,
  addEventListener(t, f) { listeners.push([t, f]); },
};
new Function("document", "window", m[0].replace(/^\s*\/\*[\s\S]*?\*\//, ""))(document, window);

const current = () => links.findIndex((a) => a.getAttribute("aria-current") === "true");
const scrollTo = (shift) => {
  secIds.forEach((id, i) => tops.set(id, i * 1000 - shift));
  listeners.filter(([t]) => t === "scroll").forEach(([, f]) => f());
};

console.log(`\n目次の現在位置（節 ${secIds.length} 個・判定線は画面上から ${window.innerHeight / 3} px）`);
ok(current() === 0, "先頭では第1節が印される");
ok(links.filter((a) => a.getAttribute("aria-current") === "true").length === 1,
  "印は常に1つだけ");
scrollTo(800);        // 第2節の top = 200 < 300 → 第2節
ok(current() === 1, "第2節が判定線を越えたら第2節に移る");
scrollTo(750);        // 第2節の top = 250 < 300 → まだ第2節
ok(current() === 1, "判定線を越える直前は前の節のまま");
scrollTo(650);        // 第2節の top = 350 > 300 → 第1節
ok(current() === 0, "上に戻ると印も戻る");
scrollTo(1e6);        // 全節が画面上へ
ok(current() === secIds.length - 1, "最後まで送ると最終節が印される");
ok(links.filter((a) => a.getAttribute("aria-current") === "true").length === 1,
  "どこでも印は1つだけ");

console.log(fail ? `\n${fail} 件失敗` : "\n全件通過");
process.exit(fail ? 1 : 0);
