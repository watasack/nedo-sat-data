#!/usr/bin/env python3
"""R1の決定的な穴＝「他工事による損傷の原因工事の規模別内訳」を取る（第5巡）

第4巡で R1（線状インフラの第三者行為監視）が第8の関門を通ったが、残った即死条件が
**「原因工事が小規模中心なら、当日完了の掘削を21%しか取れないので価値が出ない」**である。
第4巡で取った官庁ページのリンクを辿って、統計の実体に届く経路を特定したのでそこを直接叩く。

- 電気保安統計（経産省）: 電気事故の件数と原因別内訳。**他物件・他工事による損傷**の行があるはず
- 高圧ガス事故統計（高圧ガス保安協会）: 高圧ガス事故の原因別
- 事故・防災情報（経産省 電力安全課）
- あわせて **LiveEO / OrbitalEye の国内展開**を PR TIMES の検索で当てる（国内展開があれば必ず出る）

`trigger-fetch-r1s` → `r1-stats` ブランチ。**判断はこのスクリプトがしない。**
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("r1_stats"); UA = "Mozilla/5.0 (compatible; nedo-applicant-fetch/1.0)"
SEEDS = [
    ("denki_hoan_toukei", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/detail/denkihoantoukei.html"),
    ("denki_setsubi_jiko", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/electric/detail/setsubi_jiko.html"),
    ("khk_hpg_stats", "http://www.khk.or.jp/public_information/incident_investigation/hpg_incident/statistics_material.html"),
    ("khk_lpg_stats", "http://www.khk.or.jp/public_information/incident_investigation/lpg_incident/statistics_material.html"),
    ("meti_gas_anzen", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/gas/"),
    ("meti_hipregas", "https://www.meti.go.jp/policy/safety_security/industrial_safety/sangyo/hipregas/index.html"),
    ("nite_jiko", "https://www.nite.go.jp/gcet/index.html"),
    # LiveEO / OrbitalEye の国内展開（PR TIMES の検索は静的HTMLで返る）
    ("pr_liveeo", "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=LiveEO"),
    ("pr_takoji", "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=%E4%BB%96%E5%B7%A5%E4%BA%8B%20%E8%A1%9B%E6%98%9F"),
    ("pr_maisetsu", "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=%E5%9F%8B%E8%A8%AD%E7%AE%A1%20%E8%A1%9B%E6%98%9F"),
    ("v_liveeo_sol", "https://www.live-eo.com/solutions"),
    ("v_liveeo_about", "https://www.live-eo.com/about"),
]
class TS(HTMLParser):
    def __init__(s): super().__init__(); s.parts=[]; s.skip=0
    def handle_starttag(s,t,a):
        if t in ("script","style"): s.skip+=1
    def handle_endtag(s,t):
        if t in ("script","style") and s.skip: s.skip-=1
    def handle_data(s,d):
        if not s.skip: s.parts.append(d)
def strip(h):
    p=TS()
    try: p.feed(h)
    except Exception: return re.sub(r"<[^>]+>"," ",h)
    return re.sub(r"\n\s*\n+","\n",re.sub(r"[ \t　]+"," ","".join(p.parts)))
def save(name,url,man):
    e={"name":name,"url":url}
    try:
        r=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*","Accept-Language":"ja,en;q=0.8"})
        with urllib.request.urlopen(r,timeout=60) as resp:
            st,ct,body=resp.status,resp.headers.get("Content-Type",""),resp.read()
        e.update(status=st,content_type=ct,bytes=len(body))
        suf=".pdf" if "pdf" in ct.lower() else ".html"
        (OUT/(name+suf)).write_bytes(body); e["file"]=name+suf
        if suf==".html":
            try: t=body.decode("utf-8")
            except UnicodeDecodeError: t=body.decode("cp932",errors="replace")
            (OUT/(name+".txt")).write_text(strip(t),encoding="utf-8"); e["text_file"]=name+".txt"
            # 統計ページ内のPDF/Excelリンクを控える（次巡の種）
            e["doc_links"]=sorted(set(urllib.parse.urljoin(url,h) for h in re.findall(r'href="([^"]+\.(?:pdf|xlsx?|csv))"',t,re.I)))[:40]
        print(f"OK   {st} {len(body):>9,}  {url}")
    except urllib.error.HTTPError as ex:
        e.update(status=ex.code,error=f"HTTPError {ex.code}"); print(f"FAIL {ex.code} {url}")
    except Exception as ex:
        e.update(status=None,error=f"{type(ex).__name__}: {ex}"); print(f"FAIL --- {url} {ex}")
    man.append(e); time.sleep(1.5)
def main():
    OUT.mkdir(parents=True,exist_ok=True); man=[]
    for n,u in SEEDS: save(n,u,man)
    # 1巡目で見つかった統計本体（PDF/Excel）を自動で追いかける
    docs=[]
    for e in man:
        for d in e.get("doc_links",[])[:8]:
            if any(k in d.lower() for k in ("toukei","jiko","statistic","incident","hoan")): docs.append(d)
    for i,d in enumerate(sorted(set(docs))[:20]): save(f"doc_{i:02d}",d,man)
    (OUT/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2),encoding="utf-8")
    ok=sum(1 for m in man if m.get("status")==200)
    print(f"\n取得 {ok}/{len(man)} 件")
