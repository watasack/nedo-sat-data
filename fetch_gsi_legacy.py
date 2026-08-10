#!/usr/bin/env python3
"""国土地理院を「レガシー再ネゴシエーション許可」で取り直す

監査で判明: 前回 `gsi.go.jp` の5URLが全部失敗したのは403でも接続不可でもなく
**SSL: UNSAFE_LEGACY_RENEGOTIATION** だった。これは ssl.OP_LEGACY_SERVER_CONNECT で回避できる。

**この1件の取得が3つの候補の生死を同時に決める。**

| 候補 | いま何が未確定か |
|---|---|
| 街区スケールの地盤沈下（4.16節で生存） | **急所そのもの**——国土地理院が干渉SARの定常解析を全国公表していないか |
| 8A-13 地震後の宅地の永久変位（G2(a)で死亡） | **同じ前提で殺されている。** 監査は「根拠が一次資料で1件も無い」と判定した |
| 9H-15／9F-7 休廃止鉱山の堆積場 | 同型の矛盾（片方は行政が把握として死亡、片方は記録が無いとして保留） |

**同一の事実で正反対の判定を下している対**を解消するための取得である。
"""
import json, re, ssl, time, urllib.error, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("gsi_legacy"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
ctx = ssl.create_default_context()
ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
SEEDS = [
    ("gsi_top","https://www.gsi.go.jp/"),
    ("gsi_sar","https://www.gsi.go.jp/uchusokuchi/sar.html"),
    ("gsi_uchu","https://www.gsi.go.jp/uchusokuchi/uchusokuchi.html"),
    ("gsi_kanshi","https://www.gsi.go.jp/kanshi.html"),
    ("gsi_bousai","https://www.gsi.go.jp/BOUSAI/"),
    ("gsi_insar_kaiseki","https://www.gsi.go.jp/uchusokuchi/uchusokuchi41012.html"),
]
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
def main():
    import urllib.parse
    OUT.mkdir(parents=True,exist_ok=True); man=[]; seen=set()
    q=[(n,u,0) for n,u in SEEDS]; c=[0]
    while q and len(man)<45:
        n,u,d=q.pop(0)
        if u in seen: continue
        seen.add(u)
        e={"name":n,"url":u,"depth":d}
        try:
            r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja"})
            with urllib.request.urlopen(r,timeout=60,context=ctx) as resp:
                st,ct,body=resp.status,resp.headers.get("Content-Type",""),resp.read()
            e.update(status=st,bytes=len(body))
            suf=".pdf" if ("pdf" in ct.lower() or u.lower().endswith(".pdf")) else ".html"
            (OUT/(n+suf)).write_bytes(body); e["file"]=n+suf
            if suf==".html":
                try: t=body.decode("utf-8")
                except UnicodeDecodeError: t=body.decode("cp932",errors="replace")
                (OUT/(n+".txt")).write_text(strip_tags(t),encoding="utf-8"); e["text_file"]=n+".txt"
                if d<1:
                    lp=LP(); lp.feed(t)
                    for href,label in lp.links:
                        nx=urllib.parse.urldefrag(urllib.parse.urljoin(u,href))[0]
                        if urllib.parse.urlparse(nx).netloc!="www.gsi.go.jp": continue
                        if any(k in (href+label) for k in ("SAR","sar","干渉","地盤変動","地殻変動","解析","監視")):
                            c[0]+=1; q.append((f"{n}_l{c[0]:03d}",nx,d+1))
            print(f"OK   {st} {len(body):>9,}  {u}")
        except urllib.error.HTTPError as ex:
            e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {u}")
        except Exception as ex:
            e.update(status=None,error=str(ex)[:70]); print(f"FAIL --- {u}  {str(ex)[:60]}")
        man.append(e); time.sleep(1.0)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n取得 {sum(1 for m in man if m.get('status')==200)}/{len(man)} 件")

if __name__ == "__main__":
    main()
