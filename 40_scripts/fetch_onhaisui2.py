#!/usr/bin/env python3
"""温排水案のG8の逃げ道を、別経路で確定させる（第2巡）

第1巡は `assess.env.go.jp` と `env.go.jp/policy/assess/` が**403**で決定打が取れなかった。
そこで経路を3系統に変える。

**問いは1つ**——**「第三者が測り、費用は自己申告者が負担する」という構図が、制度として存在するか。**

| 系統 | 何を | なぜ |
|---|---|---|
| **A. 条文そのもの** | e-Gov の**API**（`elaws.e-gov.go.jp/api/1/lawdata/...`）で環境影響評価法・電気事業法の条文を直接取る | 第1巡でHTMLは800バイトのJSシェルだった。**APIならXMLが返る** |
| **B. 対照例（決定的）** | **土壌汚染対策法の指定調査機関**——汚染調査は環境大臣が指定した第三者機関が行い、**費用は土地所有者が負担する**。計量法の定期検査、建築物の定期報告も同型 | **「第三者が測り当事者が払う」制度が日本に実在することの証明**。存在すれば、アセスの事後調査に同じ型が無いことが「制度設計の選択」として確定する |
| **C. 実務** | 電力会社の温排水調査の実例と、立地県の安全協定・公害防止協定 | 協定に第三者検証条項があれば逃げ道になる |
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
OUT = Path("onhaisui2"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
SEEDS = [
    # A. 条文（e-Gov API）
    ("law_assess_api", "https://elaws.e-gov.go.jp/api/1/lawdata/%E5%B9%B3%E6%88%90%E4%B9%9D%E5%B9%B4%E6%B3%95%E5%BE%8B%E7%AC%AC%E5%85%AB%E5%8D%81%E4%B8%80%E5%8F%B7"),
    ("law_dojo_api", "https://elaws.e-gov.go.jp/api/1/lawdata/%E5%B9%B3%E6%88%90%E5%8D%81%E4%BA%94%E5%B9%B4%E6%B3%95%E5%BE%8B%E7%AC%AC%E4%B8%83%E5%8D%81%E4%B8%80%E5%8F%B7"),
    ("law_list_api", "https://elaws.e-gov.go.jp/api/1/lawlists/1"),
    # B. 対照例：第三者が測り当事者が払う制度
    ("dojo_shitei", "https://www.env.go.jp/water/dojo/"),
    ("dojo_shitei2", "https://www.env.go.jp/water/dojo/law-tsuchi.html"),
    ("keiryo", "https://www.meti.go.jp/policy/economy/hyojun/techno_infra/00_top.html"),
    # C. 実務：電力の温排水調査と立地県の協定
    ("kepco_env", "https://www.kepco.co.jp/energy_supply/energy/nuclear_power/"),
    ("kyuden_env", "https://www.kyuden.co.jp/environment_index.html"),
    ("yonden_env", "https://www.yonden.co.jp/energy/atom/index.html"),
    ("fukui_kyotei", "https://www.pref.fukui.lg.jp/doc/genshi/"),
    ("saga_kyotei", "https://www.pref.saga.lg.jp/kiji00325541/index.html"),
    ("nra_top", "https://www.nra.go.jp/"),
]
CINII = "https://cir.nii.ac.jp/all?q={q}"
QUERIES = [("shitei_chosa","土壌汚染 指定調査機関 第三者"),("onhaisui_kyotei","温排水 協定 監視 漁業")]
class TS(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,t,a):
        if t in("script","style"): self.skip+=1
    def handle_endtag(self,t):
        if t in("script","style") and self.skip: self.skip-=1
    def handle_data(self,d):
        if not self.skip: self.parts.append(d)
def strip_tags(h):
    p=TS()
    try: p.feed(h)
    except Exception: return re.sub(r"<[^>]+>"," ",h)
    return re.sub(r"\n\s*\n+","\n",re.sub(r"[ \t　]+"," ","".join(p.parts)))
def save(n,u,man):
    e={"name":n,"url":u}
    try:
        r=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja,en;q=0.8"})
        with urllib.request.urlopen(r,timeout=90) as resp:
            st,ct,body=resp.status,resp.headers.get("Content-Type",""),resp.read()
        e.update(status=st,content_type=ct,bytes=len(body))
        low=ct.lower()
        suf=".xml" if ("xml" in low) else (".pdf" if "pdf" in low else ".html")
        (OUT/(n+suf)).write_bytes(body); e["file"]=n+suf
        try: t=body.decode("utf-8")
        except UnicodeDecodeError: t=body.decode("cp932",errors="replace")
        (OUT/(n+".txt")).write_text(strip_tags(t) if suf!=".xml" else t,encoding="utf-8")
        e["text_file"]=n+".txt"
        print(f"OK   {st} {len(body):>9,}  {u[:70]}")
    except urllib.error.HTTPError as ex:
        e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {u[:70]}")
    except Exception as ex:
        e.update(status=None,error=str(ex)[:60]); print(f"FAIL --- {u[:70]}")
    man.append(e); time.sleep(1.2)
def main():
    OUT.mkdir(parents=True,exist_ok=True); man=[]
    for n,u in SEEDS: save(n,u,man)
    for k,q in QUERIES: save(f"q_{k}",CINII.format(q=urllib.parse.quote(q)),man)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n取得 {sum(1 for m in man if m.get('status')==200)}/{len(man)} 件")

if __name__ == "__main__":
    main()
