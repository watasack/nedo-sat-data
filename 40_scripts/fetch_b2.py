#!/usr/bin/env python3
"""B-2（ドローン熱赤外との顧客視点の競合）を、候補4件と同じ検査に掛ける

**なぜ取るか。** `review_事業性.md` の B-2 は2026年8月8日に【致命的】と判定されて以来、未閉塞のまま
提出に向かっている。しかもその根拠は**一次資料ではなく記憶**である——「ENEOS・大手化学は既に
自社ドローン運用を始めている」と固有名詞が書かれているが、出典が無い。

一方で、この独立セッションは**候補側（大屋根の風災査定）を、まさに同じ関門 G2(c) で、
PR TIMES の日付つき一次資料を取って殺した**（東京海上日動×国際航業 2023年4月ほか）。
**候補には一次資料を要求し、現行案には要求していない。** この非対称を閉じる。

取りに行くのは3系統。

| 系統 | 何を確かめるか |
|---|---|
| A 商用サービスの実在 | 国内で**プラントの保温・配管・タンクを対象とするドローン点検**が商用提供されているか。事業者名・開始年・対象 |
| B 手法としての位置づけ | **保温材下腐食（CUI）の検査手法**として赤外サーモグラフィがどう扱われているか（学術・業界・規格） |
| C 制度側の後押し | 経産省の**スマート保安**がドローン・センサをプラント保安にどう位置づけているか（G1/G2(a)の有無） |

**判断はこのスクリプトがしない。取るだけである。**
"""
import json, re, ssl, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("b2refs")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
KEYWORDS = ("ドローン", "点検", "保安", "プラント", "赤外", "サーモ", "腐食", "保温", "配管",
            "タンク", "検査", "スマート保安", "UAV", "設備")
DOC_EXT = (".pdf", ".xlsx", ".xls", ".csv")
MAX_DEPTH = 1
MAX_ITEMS = 140


def cinii(q):
    return "https://cir.nii.ac.jp/all?q=" + urllib.parse.quote(q, safe="")


def prtimes(w):
    return "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=" + urllib.parse.quote(w, safe="")


SEEDS = [
    # ===== A: 商用サービスの実在（PR TIMES は日付つきで返る） =====
    ("a_pr_drone_plant", prtimes("ドローン プラント 点検")),
    ("a_pr_drone_sekiyu", prtimes("製油所 ドローン")),
    ("a_pr_drone_sekka", prtimes("石油化学 ドローン 点検")),
    ("a_pr_eneos", prtimes("ENEOS ドローン")),
    ("a_pr_thermo_tenken", prtimes("赤外線 サーモグラフィ 設備点検")),
    ("a_pr_drone_tank", prtimes("ドローン タンク 点検")),
    ("a_pr_haikan_fushoku", prtimes("配管 腐食 点検 ドローン")),
    ("a_pr_dronebox", prtimes("ドローンポート 自動 点検")),
    ("a_pr_hoon", prtimes("保温材 腐食")),
    ("a_pr_smart_hoan", prtimes("スマート保安")),
    ("a_terra", "https://www.terra-drone.net/"),

    # ===== B: 手法としての位置づけ（学術・業界） =====
    ("b_cinii_cui", cinii("保温材下腐食 検査")),
    ("b_cinii_cui2", cinii("CUI 保温材 腐食 赤外線")),
    ("b_cinii_thermo_plant", cinii("赤外線サーモグラフィ プラント 配管 診断")),
    ("b_cinii_drone_plant", cinii("ドローン プラント 設備点検 赤外線")),
    ("b_cinii_eisei_plant", cinii("衛星 熱赤外 プラント 設備 監視")),
    ("b_jsndi", "https://www.jsndi.jp/"),
    ("b_khk", "https://www.khk.or.jp/"),

    # ===== C: 制度側（経産省は /policy/ 側なら200が返る実績あり） =====
    ("c_meti_smart_hoan", "https://www.meti.go.jp/policy/safety_security/industrial_safety/index.html"),
    ("c_meti_sangyo", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/index.html"),
    ("c_meti_hoan_dx", "https://www.meti.go.jp/policy/safety_security/industrial_safety/smart_hoan/index.html"),
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
            with urllib.request.urlopen(req, timeout=90) as r:
                st, ct, body = r.status, r.headers.get("Content-Type", ""), r.read()
            e.update(status=st, content_type=ct, bytes=len(body))
            suf = ".pdf" if ("pdf" in ct.lower() or url.lower().endswith(".pdf")) else ".html"
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
