#!/usr/bin/env python3
"""生存4件の急所（各1件）を一次資料で閉じる ── 差し替え検証の独立セッション用

18_テーマ代替案の検討.md 4.16節で生き残った4候補は、それぞれ「未取得1件」まで死因が絞れている。
その1件を取りに行く。**判断はこのスクリプトがしない。取るだけである。**

| 系統 | 候補 | 急所（これ1つで生死が決まる） | 当たり先 |
|---|---|---|---|
| A | S1' 造成・盛土の「いつ」の遡及特定 | 「いつ」を要する意思決定が**予算として**存在するか。監督処分（是正命令）が日付を要さないなら型①で死ぬ | e-Gov法令API（盛土規制法の条文）＋国交省の施行状況 |
| B | 街区スケールの地盤沈下の遡及提示 | **国土地理院が干渉SARの定常解析を全国公表していないか**。していれば「所管官庁の内製」で即死 | gsi.go.jp は全URLがJSシェル7,381バイト → **別ホスト（vldb / maps / fnc）と mlit 側の報道発表**で迂回 |
| C | 大屋根の風災査定 | **損保のリスクエンジニアリング内製の有無** | 損保系RM3社のサイト＋PR TIMES＋損保協会 |
| D | 砂防堰堤の堆砂率 | **砂防関係施設点検要領に堆砂状況が入っているか**。入っていれば制度が届けている | 国交省 河川局の指針・ガイドライン（mlit は有効URLなら200） |

塞がっている経路（既知。ここへは行かない）: meti.go.jp/shingikai/＝403、assess.env.go.jp＝403、
NETIS＝403、Mojeek＝403、官公需情報ポータル＝接続不可、DuckDuckGo＝bot判定202、KAKEN＝JSシェル。
gsi.go.jp は `ssl.OP_LEGACY_SERVER_CONNECT` で200が返るが中身がJSシェルなので、**別ホストで当てる。**
"""
import json, re, ssl, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path("kyusho4")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
KEYWORDS = ("点検", "要領", "堆砂", "砂防", "維持管理", "盛土", "造成", "規制法", "監督処分",
            "施行", "干渉SAR", "InSAR", "地盤変動", "地盤沈下", "衛星", "屋根", "風災", "査定",
            "リスクエンジニアリング", "統計", "処分", "違反")
DOC_EXT = (".pdf", ".xlsx", ".xls", ".csv")
MAX_DEPTH = 1
MAX_ITEMS = 120

def egov(lawnum):
    return "https://elaws.e-gov.go.jp/api/1/lawdata/" + urllib.parse.quote(lawnum, safe="")

def cinii(q):
    return "https://cir.nii.ac.jp/all?q=" + urllib.parse.quote(q, safe="")

def prtimes(w):
    return "https://prtimes.jp/main/action.php?run=html&page=searchkey&search_word=" + urllib.parse.quote(w, safe="")

SEEDS = [
    # ================= A: S1' 盛土の「いつ」 =================
    # 条文の実測。監督処分（是正命令）の要件に「いつ」が入るか、罰則が誰に向くか
    ("a_law_morido", egov("昭和三十六年法律第百九十一号")),          # 宅地造成及び特定盛土等規制法
    ("a_law_haiki", egov("昭和四十五年法律第百三十七号")),           # 廃棄物処理法（不法投棄の原因者特定）
    ("a_mlit_morido", "https://www.mlit.go.jp/toshi/web/morido.html"),
    ("a_mlit_morido2", "https://www.mlit.go.jp/toshi/toshi_tobou_fr_000023.html"),
    ("a_mlit_soutenken", "https://www.mlit.go.jp/report/press/toshi03_hh_000106.html"),
    ("a_cinii_morido_kensu", cinii("盛土規制法 監督処分 件数")),
    ("a_cinii_morido_jiki", cinii("盛土 造成 時期 特定 衛星")),

    # ================= B: 国土地理院の干渉SAR定常解析 =================
    # gsi.go.jp 本体はJSシェル。別ホストと国交省側の報道発表で当てる
    ("b_vldb_sar", "https://vldb.gsi.go.jp/sokuchi/sar/"),
    ("b_vldb_top", "https://vldb.gsi.go.jp/"),
    ("b_maps_ichiran", "https://maps.gsi.go.jp/development/ichiran.html"),
    ("b_fnc", "https://fnc.gsi.go.jp/"),
    ("b_mlit_gsi_press", "https://www.mlit.go.jp/report/press/index.html"),
    ("b_mlit_gsi", "https://www.mlit.go.jp/gsi/index.html"),
    ("b_cinii_insar_teijou", cinii("干渉SAR 時系列解析 国土地理院 地盤変動")),
    ("b_cinii_insar_zenkoku", cinii("干渉SAR 全国 地盤沈下 監視")),
    ("b_cinii_insar_jigyou", cinii("だいち2号 干渉SAR 地盤変動 定常解析")),
    ("b_env_chinka", "https://www.env.go.jp/water/jiban/chinka.html"),
    ("b_prtimes_insar", prtimes("干渉SAR")),
    ("b_prtimes_jiban", prtimes("地盤沈下 衛星")),

    # ================= C: 損保のリスクエンジニアリング内製 =================
    ("c_tokiorisk", "https://www.tokiorisk.co.jp/"),
    ("c_msad_ir", "https://rm.ms-ad-hd.com/"),
    ("c_sompo_rc", "https://www.sompo-rc.co.jp/"),
    ("c_sonpo", "https://www.sonpo.or.jp/"),
    ("c_prtimes_yane", prtimes("衛星 屋根 保険")),
    ("c_prtimes_fusai", prtimes("風災 査定")),
    ("c_prtimes_riskeng", prtimes("リスクエンジニアリング 衛星")),
    ("c_prtimes_sonpo_eisei", prtimes("損害保険 衛星画像")),
    ("c_cinii_yane_fusai", cinii("風災 屋根 損害保険 リモートセンシング")),
    ("c_cinii_hoken_eisei", cinii("損害保険 衛星画像 査定")),

    # ================= D: 砂防関係施設点検要領 =================
    ("d_mlit_sabo_guide", "https://www.mlit.go.jp/river/shishin_guideline/sabo/index.html"),
    ("d_mlit_shishin", "https://www.mlit.go.jp/river/shishin_guideline/index.html"),
    ("d_mlit_sabo", "https://www.mlit.go.jp/mizukokudo/sabo/index.html"),
    ("d_mlit_sabo2", "https://www.mlit.go.jp/river/sabo/index.html"),
    ("d_mlit_ijikanri", "https://www.mlit.go.jp/river/shishin_guideline/sabo/pdf/tenken_youryou.pdf"),
    ("d_cinii_taisha", cinii("砂防堰堤 堆砂 点検 除石")),
    ("d_cinii_taisha2", cinii("砂防関係施設 点検要領 堆砂")),
    ("d_law_sabo", egov("明治三十年法律第二十九号")),                 # 砂防法
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


# gsi.go.jp 系はレガシー再ネゴが要る（origin/gsi-legacy で実証）
LEGACY_CTX = ssl.create_default_context()
LEGACY_CTX.options |= 0x4  # OP_LEGACY_SERVER_CONNECT


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
            with opener_for(url).open(req, timeout=60) as r:
                st, ct, body = r.status, r.headers.get("Content-Type", ""), r.read()
            e.update(status=st, content_type=ct, bytes=len(body))
            low = ct.lower()
            if "pdf" in low or url.lower().endswith(".pdf"): suf = ".pdf"
            elif "xml" in low or "/lawdata/" in url: suf = ".xml"
            elif url.lower().endswith((".xlsx", ".xls")): suf = ".xlsx"
            else: suf = ".html"
            (OUT / (name + suf)).write_bytes(body); e["file"] = name + suf
            if suf in (".html", ".xml"):
                try: text = body.decode("utf-8")
                except UnicodeDecodeError: text = body.decode("cp932", errors="replace")
                (OUT / (name + ".txt")).write_text(strip_tags(text), encoding="utf-8")
                e["text_file"] = name + ".txt"
                if suf == ".html" and depth < MAX_DEPTH:
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
