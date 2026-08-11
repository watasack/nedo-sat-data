#!/usr/bin/env python3
"""温排水案（P1）の唯一の死因 G8 に、逃げ道があるかを確定させる取得

I3担当のエージェントが16件を掃引した結果、**発電所温排水の第三者検証（P1）だけが
G1〜G7をすべて通り、物理（G4）も自前計算で通った。** 死因は G8 ただ1つ——
**自己申告している発電事業者が唯一の資金力ある買い手で、その側には自分に不利な
独立記録を買う動機が無い。** 便益を受ける漁協・住民・報道には支払能力が無く、
立地県に振ると G3（元請け問題）へ戻る。

**逃げ道は1つだけ存在する**——「**契約または制度の相手方が第三者検証を要求し、
費用を自己申告者に負担させる**」構図があるか。これがあれば、支払者＝事業者のまま
受益者＝第三者という形が制度的に成立し、G8 が外れる。

| # | 閉じたい問い | 当たり先 |
|---|---|---|
| 1 | **環境影響評価の事後調査（供用後調査）に、第三者機関の関与が制度上要求されているか** | 環境省 環境影響評価情報支援ネットワーク（`assess.env.go.jp`）の事後調査報告書と主務省令 |
| 2 | 公害防止協定・安全協定の雛形に**第三者検証条項**があるか | 立地県のサイト |
| 3 | 温排水影響調査を**誰が受注しているか**（G2(c)(d)の閉塞） | 入札記録 |

**1が無ければ P1 は永久に G8 で死ぬ。** したがってこの取得の主目的は1である。

`trigger-fetch-onhaisui` → `onhaisui-refs` ブランチ。**判断はこのスクリプトがしない。**
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("onhaisui_refs"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
KEYWORDS = ("事後調査", "温排水", "水温", "発電所", "報告書", "指針", "省令", "協定", "第三者")
SEEDS = [
    # === 1. 環境影響評価の事後調査（最重要） ===
    ("assess_top", "https://assess.env.go.jp/"),
    ("assess_houkoku", "https://assess.env.go.jp/1_seido/1-1_guide/1-1-3.html"),
    ("assess_jigo", "https://assess.env.go.jp/1_seido/1-1_guide/index.html"),
    ("assess_denki", "https://assess.env.go.jp/2_shirase/index.html"),
    ("env_assess_law", "https://www.env.go.jp/policy/assess/"),
    ("egov_assess", "https://laws.e-gov.go.jp/law/409AC0000000081"),
    # 発電所アセスの主務省令（経産省側。/policy/ 配下は200の実績あり）
    ("meti_assess", "https://www.meti.go.jp/policy/safety_security/industrial_safety/index.html"),
    ("enecho_assess", "https://www.enecho.meti.go.jp/category/electricity_and_gas/electric/anzen/"),
    # === 2. 公害防止協定・温排水の監視 ===
    ("env_mizu", "https://www.env.go.jp/water/"),
    ("env_kaiiki", "https://www.env.go.jp/water/heisa/"),
    # === 3. 温排水影響調査の受注（G2の閉塞） ===
    ("fepc_top", "https://www.fepc.or.jp/"),
    ("fepc_kankyo", "https://www.fepc.or.jp/environment/"),
]
CINII = "https://cir.nii.ac.jp/all?q={q}"
QUERIES = [
    ("onhaisui_sat", "温排水 衛星 熱赤外"),
    ("onhaisui_chosa", "温排水 拡散 調査 発電所"),
    ("jigo_chosa", "環境影響評価 事後調査 第三者"),
]

class TS(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, t, a):
        if t in ("script","style"): self.skip+=1
    def handle_endtag(self, t):
        if t in ("script","style") and self.skip: self.skip-=1
    def handle_data(self, d):
        if not self.skip: self.parts.append(d)

class LP(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.cur=None; self.buf=[]
    def handle_starttag(self, t, a):
        if t=="a": self.cur=dict(a).get("href"); self.buf=[]
    def handle_data(self, d):
        if self.cur is not None: self.buf.append(d)
    def handle_endtag(self, t):
        if t=="a" and self.cur: self.links.append((self.cur,"".join(self.buf).strip())); self.cur=None

def strip_tags(h):
    p=TS()
    try: p.feed(h)
    except Exception: return re.sub(r"<[^>]+>"," ",h)
    return re.sub(r"\n\s*\n+","\n",re.sub(r"[ \t　]+"," ","".join(p.parts)))

def save(name,url,man,depth=0,queue=None,ctr=None):
    e={"name":name,"url":url,"depth":depth}
    try:
        req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja,en;q=0.8"})
        with urllib.request.urlopen(req,timeout=60) as r:
            st,ct,body=r.status,r.headers.get("Content-Type",""),r.read()
        e.update(status=st,content_type=ct,bytes=len(body))
        suf=".pdf" if ("pdf" in ct.lower() or url.lower().endswith(".pdf")) else ".html"
        (OUT/(name+suf)).write_bytes(body); e["file"]=name+suf
        if suf==".html":
            try: t=body.decode("utf-8")
            except UnicodeDecodeError: t=body.decode("cp932",errors="replace")
            (OUT/(name+".txt")).write_text(strip_tags(t),encoding="utf-8"); e["text_file"]=name+".txt"
            if depth<1 and queue is not None:
                lp=LP(); lp.feed(t); host=urllib.parse.urlparse(url).netloc
                for href,label in lp.links:
                    nxt=urllib.parse.urldefrag(urllib.parse.urljoin(url,href))[0]
                    if urllib.parse.urlparse(nxt).netloc!=host: continue
                    if href.lower().endswith(".pdf") or any(k in (href+label) for k in KEYWORDS):
                        ctr[0]+=1; queue.append((f"{name}_l{ctr[0]:03d}",nxt,depth+1))
        print(f"OK   {st} {len(body):>9,}  {url}")
    except urllib.error.HTTPError as ex:
        e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {url}")
    except Exception as ex:
        e.update(status=None,error=f"{type(ex).__name__}: {ex}"); print(f"FAIL --- {url} {ex}")
    man.append(e); time.sleep(1.0)

def main():
    OUT.mkdir(parents=True,exist_ok=True); man=[]; seen=set()
    queue=[(n,u,0) for n,u in SEEDS]; ctr=[0]
    while queue and len(man)<70:
        n,u,d=queue.pop(0)
        if u in seen: continue
        seen.add(u); save(n,u,man,d,queue,ctr)
    for k,q in QUERIES:
        save(f"q_{k}",CINII.format(q=urllib.parse.quote(q)),man)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n取得 {sum(1 for m in man if m.get('status')==200)}/{len(man)} 件")

if __name__ == "__main__":
    main()
