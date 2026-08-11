#!/usr/bin/env python3
"""街区スケール沈下案の唯一の律速＝国土地理院の干渉SAR定常解析の有無を確定させる

再点検で生存した2件のうち、応募例への当たり・受益者＝支払者・無償データ・現地作業ゼロ・
較正データが顧客側（水準測量）にある の4条件が同時に立つのは10巡で初めてである。
**律速は1つだけ**——**国土地理院が干渉SARによる地盤変動の定常解析を全国で公表していないか。**
していれば「面的な答えが制度から届いている」＝ G1(a)＋G2(a) で即死する（S1が所管官庁の内製で死んだのと同型）。

第2に、自治体・環境省の地盤沈下観測（水準測量）の**点間隔**。数km間隔なら「標本 vs 面的・連続」の
逃げ道が立つが、街区間隔なら立たない。

`gsi.go.jp` は `meti.go.jp` と違い403の記録がない。
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
OUT = Path("insar_gsi"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
KEYWORDS = ("干渉SAR","地盤変動","地殻変動","地盤沈下","解析","公表","だいち","SAR")
SEEDS = [
    ("gsi_top","https://www.gsi.go.jp/"),
    ("gsi_sar","https://www.gsi.go.jp/uchusokuchi/sar.html"),
    ("gsi_chikaku","https://www.gsi.go.jp/kanshi.html"),
    ("gsi_jiban","https://www.gsi.go.jp/sokuchikijun/sokuchikijun40006.html"),
    ("gsi_insar_list","https://www.gsi.go.jp/uchusokuchi/uchusokuchi.html"),
    ("env_jiban","https://www.env.go.jp/water/jiban/"),
    ("env_jiban2","https://www.env.go.jp/water/report/index.html"),
]
CINII = "https://cir.nii.ac.jp/all?q={q}"
QUERIES = [("kinsetsu","近接施工 沈下 干渉SAR"),("insar_funso","干渉SAR 訴訟 鑑定 地盤沈下"),("yane_fusai","風災 屋根 リモートセンシング 保険")]
class TS(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,t,a):
        if t in("script","style"): self.skip+=1
    def handle_endtag(self,t):
        if t in("script","style") and self.skip: self.skip-=1
    def handle_data(self,d):
        if not self.skip: self.parts.append(d)
class LP(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.cur=None; self.buf=[]
    def handle_starttag(self,t,a):
        if t=="a": self.cur=dict(a).get("href"); self.buf=[]
    def handle_data(self,d):
        if self.cur is not None: self.buf.append(d)
    def handle_endtag(self,t):
        if t=="a" and self.cur: self.links.append((self.cur,"".join(self.buf).strip())); self.cur=None
def strip_tags(h):
    p=TS()
    try: p.feed(h)
    except Exception: return re.sub(r"<[^>]+>"," ",h)
    return re.sub(r"\n\s*\n+","\n",re.sub(r"[ \t　]+"," ","".join(p.parts)))
def save(n,u,man,d=0,q=None,c=None):
    e={"name":n,"url":u,"depth":d}
    try:
        r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja,en;q=0.8"})
        with urllib.request.urlopen(r,timeout=60) as resp:
            st,ct,body=resp.status,resp.headers.get("Content-Type",""),resp.read()
        e.update(status=st,bytes=len(body))
        suf=".pdf" if ("pdf" in ct.lower() or u.lower().endswith(".pdf")) else ".html"
        (OUT/(n+suf)).write_bytes(body); e["file"]=n+suf
        if suf==".html":
            try: t=body.decode("utf-8")
            except UnicodeDecodeError: t=body.decode("cp932",errors="replace")
            (OUT/(n+".txt")).write_text(strip_tags(t),encoding="utf-8"); e["text_file"]=n+".txt"
            if d<1 and q is not None:
                lp=LP(); lp.feed(t); host=urllib.parse.urlparse(u).netloc
                for href,label in lp.links:
                    nx=urllib.parse.urldefrag(urllib.parse.urljoin(u,href))[0]
                    if urllib.parse.urlparse(nx).netloc!=host: continue
                    if href.lower().endswith(".pdf") or any(k in (href+label) for k in KEYWORDS):
                        c[0]+=1; q.append((f"{n}_l{c[0]:03d}",nx,d+1))
        print(f"OK   {st} {len(body):>9,}  {u[:66]}")
    except urllib.error.HTTPError as ex:
        e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {u[:66]}")
    except Exception as ex:
        e.update(status=None,error=str(ex)[:50]); print(f"FAIL --- {u[:66]}")
    man.append(e); time.sleep(1.0)
def main():
    OUT.mkdir(parents=True,exist_ok=True); man=[]; seen=set(); qu=[(n,u,0) for n,u in SEEDS]; c=[0]
    while qu and len(man)<60:
        n,u,d=qu.pop(0)
        if u in seen: continue
        seen.add(u); save(n,u,man,d,qu,c)
    for k,q in QUERIES: save(f"q_{k}",CINII.format(q=urllib.parse.quote(q)),man)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n取得 {sum(1 for m in man if m.get('status')==200)}/{len(man)} 件")

if __name__ == "__main__":
    main()
