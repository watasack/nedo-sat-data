#!/usr/bin/env python3
"""R1の最後の穴（他工事による埋設物損傷の実態と原因工事の規模）を、必要な場所を全部当てて閉じる（第7巡）

第6巡で分かったこと: **この数字は高圧ガス事故年報にも電気保安統計にも無い。**
都市ガス導管を扱う経産省ガス安全小委員会は 403。**だからホストを分散させる。**

当たる先を5系統に分ける。**1系統でも当たれば R1 の生死が決まる。**

| 系統 | 当たり先 | 期待する数字 |
|---|---|---|
| A ガス（事業者側） | 東京ガスネットワーク・大阪ガスネットワーク・東邦ガスネットワークの保安ページ | 他工事による導管損傷の件数・原因 |
| B ガス（業界・官庁の別経路） | 日本ガス協会、経産省の /policy/ 側（/shingikai/ は403） | ガス事故統計 |
| C 統計の総合窓口 | e-Stat のガス事業統計・建設工事統計 | 事故件数、工事件数の規模分布 |
| D 掘削側（工事する側の統計） | 国交省の建設工事施工統計、建設業労働災害防止協会、道路占用 | **工事の規模分布そのもの**（原因工事が小規模中心かの逆側からの証拠） |
| E 他ライフライン | 日本下水道協会、日本水道協会、NTT | 他工事損傷は業種横断の問題なので、どこか1つで内訳が出ればよい |

**Dが本命である。** 「事故を起こした工事の規模」が取れなくても、
**「日本で行われている掘削を伴う工事の規模分布」**が取れれば、
当日完了の小規模工事が何割かが分かり、R1 の取りこぼし率を上から評価できる。

静的ホストはリンクを1段だけ辿る（キーワード一致のみ）。**判断はこのスクリプトがしない。**
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("r1_all"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
KEYWORDS = ("他工事", "損傷", "事故", "保安", "統計", "掘削", "埋設", "施工統計", "便覧", "占用")
DOC_EXT = (".pdf", ".xlsx", ".xls", ".csv")
MAX_DEPTH = 1

SEEDS = [
    # --- A: ガス導管事業者 ---
    ("a_tgn", "https://www.tokyo-gas.co.jp/network/"),
    ("a_tgn_hoan", "https://www.tokyo-gas.co.jp/network/safety/index.html"),
    ("a_ogn", "https://www.osakagas-network.co.jp/"),
    ("a_ogn_hoan", "https://www.osakagas-network.co.jp/safety/"),
    ("a_toho", "https://www.tohogas-network.co.jp/"),
    ("a_saibu", "https://www.saibugas.co.jp/"),
    # --- B: 業界団体・官庁の別経路 ---
    ("b_jga", "https://www.gas.or.jp/gas-life/anzen/"),
    ("b_jga_tokei", "https://www.gas.or.jp/tokei/"),
    ("b_meti_gas_policy", "https://www.meti.go.jp/policy/safety_security/industrial_safety/index.html"),
    ("b_meti_sangyo", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/index.html"),
    # --- C: e-Stat ---
    ("c_estat_gas", "https://www.e-stat.go.jp/stat-search?page=1&query=%E3%82%AC%E3%82%B9%E4%BA%8B%E6%A5%AD%E7%94%9F%E7%94%A3%E5%8B%95%E6%85%8B%E7%B5%B1%E8%A8%88"),
    ("c_estat_kensetsu", "https://www.e-stat.go.jp/stat-search?page=1&query=%E5%BB%BA%E8%A8%AD%E5%B7%A5%E4%BA%8B%E6%96%BD%E5%B7%A5%E7%B5%B1%E8%A8%88"),
    ("c_estat_top", "https://www.e-stat.go.jp/"),
    # --- D: 掘削側＝工事の規模分布（本命） ---
    ("d_mlit_sekou", "https://www.mlit.go.jp/toukeijouhou/chojou/stat-e.htm"),
    ("d_mlit_toukei", "https://www.mlit.go.jp/statistics/details/t-jyuken_list.html"),
    ("d_mlit_kensetsu", "https://www.mlit.go.jp/toukeijouhou/index.html"),
    ("d_kensaibou", "https://www.kensaibou.or.jp/"),
    ("d_mlit_senyo", "https://www.mlit.go.jp/road/road/traffic/sen-i/index.html"),
    # --- E: 他ライフライン ---
    ("e_jswa", "https://www.jswa.jp/"),
    ("e_jwwa", "https://www.jwwa.or.jp/"),
    ("e_ntt_west", "https://www.ntt-west.co.jp/"),
]

class TagStripper(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style"): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script","style") and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._cur=None; self._buf=[]
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._cur = d.get("href"); self._buf = []
    def handle_data(self, data):
        if self._cur is not None: self._buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self._cur:
            self.links.append((self._cur, "".join(self._buf).strip())); self._cur=None

def strip_tags(html):
    p = TagStripper()
    try: p.feed(html)
    except Exception: return re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t　]+", " ", "".join(p.parts)))

def interesting(href, text):
    low = (href + " " + text)
    if href.lower().endswith(DOC_EXT): return True
    return any(k in low for k in KEYWORDS)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest=[]; seen=set(); queue=[(n,u,0) for n,u in SEEDS]; i=0
    while queue and len(manifest) < 90:
        name,url,depth = queue.pop(0)
        if url in seen: continue
        seen.add(url)
        e={"name":name,"url":url,"depth":depth}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja,en;q=0.8"})
            with urllib.request.urlopen(req,timeout=60) as r:
                st,ct,body = r.status, r.headers.get("Content-Type",""), r.read()
            e.update(status=st,content_type=ct,bytes=len(body))
            low=ct.lower()
            suf=".pdf" if ("pdf" in low or url.lower().endswith(".pdf")) else (
                ".xlsx" if url.lower().endswith((".xlsx",".xls")) else ".html")
            (OUT/(name+suf)).write_bytes(body); e["file"]=name+suf
            if suf==".html":
                try: text=body.decode("utf-8")
                except UnicodeDecodeError: text=body.decode("cp932",errors="replace")
                (OUT/(name+".txt")).write_text(strip_tags(text),encoding="utf-8"); e["text_file"]=name+".txt"
                if depth < MAX_DEPTH:
                    lp=LinkParser(); lp.feed(text)
                    host=urllib.parse.urlparse(url).netloc
                    for href,label in lp.links:
                        nxt=urllib.parse.urldefrag(urllib.parse.urljoin(url,href))[0]
                        if nxt in seen or urllib.parse.urlparse(nxt).netloc != host: continue
                        if interesting(href,label):
                            i+=1; queue.append((f"{name}_l{i:03d}",nxt,depth+1))
            print(f"OK   {st} {len(body):>9,}  {url}")
        except urllib.error.HTTPError as ex:
            e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {url}")
        except Exception as ex:
            e.update(status=None,error=f"{type(ex).__name__}: {ex}"); print(f"FAIL --- {url} {ex}")
        manifest.append(e); time.sleep(1.0)
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    ok=sum(1 for m in manifest if m.get("status")==200)
    print(f"\n取得 {ok}/{len(manifest)} 件")

if __name__ == "__main__":
    main()
