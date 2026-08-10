#!/usr/bin/env python3
"""急所の第2巡 ── 第1巡で場所が特定できた原本を直接取る

第1巡（fetch_kyusho4.py / origin/kyusho4）で分かったこと:
- **急所D**: 「砂防関係施設点検要領（案）（令和7年4月）」の実URLが判明した（`sabo/sabo_tenkenyouryou_202504.pdf`）。
  第1巡で当てた `.../sabo/pdf/tenken_youryou.pdf` は404だった。**本文を取れば堆砂の扱いが確定する。**
- **急所B**: gsi.go.jp は https だと全URLがJSシェル7,381バイト。**http:// と NDL WARP を試す。**
  CiNii では「干渉SAR時系列解析…**実用化へ向けて**」（国土地理院時報）が出ており、記事本体で段階が分かる。
- **急所C**: 損保系リスクマネジメント3社のうち2社が接続不可だった。**別ドメインで当て直す。**
"""
import json, re, ssl, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("kijun")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
KEYWORDS = ("調査", "計画", "設計", "維持管理", "編", "基準", "指針", "砂防", "河川", "編）")
DOC_EXT = (".pdf", ".xlsx", ".xls", ".csv")
MAX_DEPTH = 1
MAX_ITEMS = 120

def cinii(q): return "https://cir.nii.ac.jp/all?q=" + urllib.parse.quote(q, safe="")
def prtimes(w): return "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=" + urllib.parse.quote(w, safe="")

SEEDS = [
    # 新入口の検証: 技術基準が「仮定する／みなす／既往資料による」で埋めている入力を、原文から機械的に引く
    ("k_chousa", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/chousa/index.html"),
    ("k_keikaku", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/keikaku/index.html"),
    ("k_sekkei", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/sekkei/index.html"),
    ("k_ijikanri", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/ijikanri/index.html"),
    ("k_ijikanri_sabo", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/ijikanri_sabo/index.html"),
    ("k_kousei", "https://www.mlit.go.jp/river/shishin_guideline/gijutsu/gijutsukijunn/pdf/kawasunakizyun_kousei.pdf"),
    ("k_sabo_shishin", "https://www.mlit.go.jp/river/shishin_guideline/sabo/volcanopdf/kazansabo_shishin.pdf"),
    ("k_dosekiryu", "https://www.mlit.go.jp/river/shishin_guideline/sabo/h28_04dosekiryu.html"),
]


class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self._cur = None; self._buf = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._cur = dict(attrs).get("href"); self._buf = []
    def handle_data(self, data):
        if self._cur is not None: self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self._cur:
            self.links.append((self._cur, "".join(self._buf).strip())); self._cur = None


def strip_tags(html):
    p = TagStripper()
    try: p.feed(html)
    except Exception: return re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t　]+", " ", "".join(p.parts)))


def interesting(href, text):
    low = href + " " + text
    if href.lower().endswith(DOC_EXT): return True
    return any(k in low for k in KEYWORDS)


LEGACY_CTX = ssl.create_default_context()
LEGACY_CTX.options |= 0x4


def opener_for(url):
    if "gsi.go.jp" in urllib.parse.urlparse(url).netloc:
        return urllib.request.build_opener(urllib.request.HTTPSHandler(context=LEGACY_CTX))
    return urllib.request.build_opener()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []; seen = set(); queue = [(n, u, 0) for n, u in SEEDS]; i = 0
    while queue and len(manifest) < MAX_ITEMS:
        name, url, depth = queue.pop(0)
        if url in seen: continue
        seen.add(url)
        e = {"name": name, "url": url, "depth": depth}
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja,en;q=0.8"})
            with opener_for(url).open(req, timeout=90) as r:
                st, ct, body = r.status, r.headers.get("Content-Type", ""), r.read()
            e.update(status=st, content_type=ct, bytes=len(body), final_url=r.geturl())
            low = ct.lower()
            if "pdf" in low or url.lower().endswith(".pdf"): suf = ".pdf"
            elif url.lower().endswith((".xlsx", ".xls")): suf = ".xlsx"
            else: suf = ".html"
            (OUT / (name + suf)).write_bytes(body); e["file"] = name + suf
            if suf == ".html":
                try: text = body.decode("utf-8")
                except UnicodeDecodeError: text = body.decode("cp932", errors="replace")
                (OUT / (name + ".txt")).write_text(strip_tags(text), encoding="utf-8")
                e["text_file"] = name + ".txt"
                if depth < MAX_DEPTH:
                    lp = LinkParser()
                    try: lp.feed(text)
                    except Exception: pass
                    host = urllib.parse.urlparse(url).netloc
                    for href, label in lp.links:
                        nxt = urllib.parse.urldefrag(urllib.parse.urljoin(url, href))[0]
                        if nxt in seen or urllib.parse.urlparse(nxt).netloc != host: continue
                        if interesting(href, label):
                            i += 1; queue.append((f"{name}_l{i:03d}", nxt, depth + 1))
            print(f"OK   {st} {len(body):>9,}  {url}")
        except urllib.error.HTTPError as ex:
            e.update(status=ex.code, error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {url}")
        except Exception as ex:
            e.update(status=None, error=f"{type(ex).__name__}: {ex}"); print(f"FAIL --- {url} {ex}")
        manifest.append(e); time.sleep(0.8)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == 200)
    print(f"\n取得 {ok}/{len(manifest)} 件")


if __name__ == "__main__":
    main()
