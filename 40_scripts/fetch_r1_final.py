#!/usr/bin/env python3
"""R1の決定的な数字＝電気保安統計の本体と、ガス安全小委員会の事故統計を取る（第6巡）

第5巡で電気保安統計のページから統計本体のPDF URLを特定した（それまでに取れていたのは正誤情報だけ）。
ここで取りたいのは1つ——**事故原因の分類に「他物件・他工事」がどれだけあるか**である。
R1（線状インフラの第三者行為監視）はこの数字で生死が決まる。
"""
import json, re, time, urllib.error, urllib.request
from pathlib import Path
OUT = Path("r1_final"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
SEEDS = [
    ("hoantokei_r6", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/files/r6_hoantokei.pdf"),
    ("hoantokei_r5", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/files/r5_hoantokei.pdf"),
    ("hoantokei_r4", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/files/2025_hoantokei_syusei/r4_hoantokei_r.pdf"),
    ("gas_anzen_shingikai", "https://www.meti.go.jp/shingikai/safety_security/gas_anzen/index.html"),
    ("gas_anzen_top", "https://www.meti.go.jp/shingikai/safety_security/gas_anzen/"),
]
def main():
    OUT.mkdir(parents=True, exist_ok=True); man=[]
    for name,url in SEEDS:
        e={"name":name,"url":url}
        try:
            r=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
            with urllib.request.urlopen(r,timeout=90) as resp:
                st,ct,body=resp.status,resp.headers.get("Content-Type",""),resp.read()
            e.update(status=st,bytes=len(body))
            suf=".pdf" if "pdf" in ct.lower() or url.endswith(".pdf") else ".html"
            (OUT/(name+suf)).write_bytes(body); e["file"]=name+suf
            print(f"OK {st} {len(body):,} {url}")
        except urllib.error.HTTPError as ex:
            e.update(status=ex.code,error=str(ex)); print(f"FAIL {ex.code} {url}")
        except Exception as ex:
            e.update(status=None,error=str(ex)); print(f"FAIL --- {url} {ex}")
        man.append(e); time.sleep(1.5)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    print("取得", sum(1 for m in man if m.get("status")==200), "/", len(man))

if __name__ == "__main__":
    main()
