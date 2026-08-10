#!/usr/bin/env python3
"""テーマ2 未解決 C・G・E の第2バッチ ── 第1バッチの取りこぼしだけを狙う。

第1バッチ（`fetch_policy_refs.py`）で C・G・E の中核は取れた:

  C … 治水経済調査マニュアル(案)「各種資産評価単価及びデフレーター」（令和6年6月改正）で
      家屋1m²当たり評価額と1世帯当たり家庭用品評価額、砂防事業の費用便益分析マニュアル
      （令和8年2月）で被害率と公共土木施設等の比率（74.2%）
  G … 土木設計業務等委託契約書(案) 第7条＋土木設計業務等共通仕様書の「主たる部分」の定義、
      入札・契約手続きガイドライン（再委託の実績は認めない／設計共同体には実績が付く）
  E … 火山砂防計画策定指針（令和5年3月）2.7「定期的な時点更新」

残った穴は3つ:

  (1) **家屋被害額が計算できない**。マニュアルの式は「床面積 × 家屋1m²当たり評価額」で、
      床面積は業務側がメッシュ建物データから作る。1住宅当たり延べ面積の公表統計
      （総務省 住宅・土地統計調査）が要る。→ C
  (2) **ガイドラインが中部地方整備局版**。蔵王＝東北、那須岳＝関東なので、当該局の版で
      同じ規定を確認したい。共同設計方式の通達も北海道開発局版しか残らなかった。→ G
  (3) **雌阿寒岳のRTHM作成業務**が第三者の入札情報サイト経由でしか見えていない。
      発注元（北海道開発局）の公告で確認したい。→ E

第1バッチのバグも直す: 出力ファイル名がラベル由来だけだったため、**同名の別URLが上書きされた**
（治水経済の shisan_r7 が shisan_r6 に、共同設計方式の国交省版が北海道開発局版に潰れた）。
本バッチは URL のハッシュを名前に足して衝突を殺す。

出力先は policy_refs2/。トリガ: trigger-fetch-policy2 ブランチへの push
"""
import gzip
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

OUT = Path("policy_refs2")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
H = {"User-Agent": UA,
     "Accept": "text/html,application/xhtml+xml,application/pdf,application/json,*/*;q=0.8",
     "Accept-Language": "ja,en;q=0.8", "Accept-Encoding": "gzip, deflate", "Connection": "close"}
MAX_BYTES = 40 * 1024 * 1024


def Q(s):
    return urllib.parse.quote_plus(s)


SINGLE = [
    # --- C(1): 第1バッチで上書きされた資産評価単価の最新版を名指しで取る ---
    ("c2_shisan_r7", "https://www.mlit.go.jp/river/basic_info/seisaku_hyouka/gaiyou/hyouka/pdf/shisan_r7.pdf"),
    ("c2_shisan_r6", "https://www.mlit.go.jp/river/basic_info/seisaku_hyouka/gaiyou/hyouka/pdf/shisan_r6.pdf"),
    # 治水経済調査マニュアル(案)本体（24MB。第1バッチで取れているが本文側の確認用）
    ("c2_chisui_manual", "https://www.mlit.go.jp/mizukokudo/river/content/001903749.pdf"),
    # --- G(2): 国交省本省の共同設計方式の通達（第1バッチで北海道開発局版に潰れた） ---
    ("g2_kyodo_sekkei_mlit", "https://www.mlit.go.jp/chotatsu/tutatsu/03/091224-2.pdf"),
    # --- E(3): 火山噴火緊急減災対策砂防計画策定ガイドライン（指針とは別文書） ---
    ("e2_kinkyu_gaidorain", "https://www.mlit.go.jp/river/shishin_guideline/sabo/volcanopdf/kinkyugensai_guideline.pdf"),
]

INDEX = [
    # --- C(1): 住宅・土地統計調査（1住宅当たり延べ面積） ---
    ("c2_jutaku_toukei", "https://www.stat.go.jp/data/jyutaku/index.html"),
    ("c2_jutaku_2023", "https://www.stat.go.jp/data/jyutaku/2023/index.html"),
    # --- G(2): 関東・東北地方整備局の建設コンサルタント業務の入札契約 ---
    ("g2_ktr_gijutsu", "https://www.ktr.mlit.go.jp/gijyutu/index00000024.html"),
    ("g2_thr_nyuusatu_gyoumu", "https://www.thr.mlit.go.jp/nyuusatu/keiyakujouhou/index.html"),
    ("g2_ktr_nyuusatu_top", "https://www.ktr.mlit.go.jp/nyuusatu/index.html"),
    # --- E(3): 北海道開発局 釧路開発建設部（雌阿寒岳のRTHM作成業務の発注元） ---
    ("e2_kushiro", "https://www.hkd.mlit.go.jp/ks/index.html"),
    ("e2_hkd_nyuusatsu", "https://www.hkd.mlit.go.jp/ky/ky/keiyaku/index.html"),
]

QUERIES = [
    ("c2", '住宅・土地統計調査 1住宅当たり延べ面積 都道府県 山形'),
    ("c2", '治水経済調査マニュアル 各種資産評価単価及びデフレーター 令和7年'),
    ("g2", '関東地方整備局 建設コンサルタント業務等 入札・契約手続きガイドライン'),
    ("g2", '東北地方整備局 設計共同体 取扱い 建設コンサルタント業務'),
    ("g2", '土木設計業務等共通仕様書 第1128条 主たる部分 再委託'),
    ("e2", '雌阿寒岳火山噴火リアルタイムハザードマップ作成外業務 公告'),
    ("e2", '火山噴火緊急減災対策砂防計画 策定ガイドライン 時点更新'),
]
SEARCH = []
for i, (tag, q) in enumerate(QUERIES):
    # 通番で名前を作る（`hash()` はプロセスごとに変わるので再現しない）
    SEARCH.append((f"{tag}_ddg_{i}", "https://html.duckduckgo.com/html/?q=" + Q(q)))
    SEARCH.append((f"{tag}_bing_{i}", "https://www.bing.com/search?q=" + Q(q)))

LINK_KEY = re.compile(
    r"延べ面積|住宅|統計表|結果の概要|資産評価|評価単価|デフレーター|マニュアル|"
    r"共同設計|設計共同体|再委託|共通仕様書|委託契約|ガイドライン|入札|契約|公告|業務|"
    r"リアルタイム|ハザードマップ|火山|砂防|緊急減災|時点更新|令和")
DOC_EXT = (".pdf", ".csv", ".xls", ".xlsx")
GOV = re.compile(r"://[^/]*\.(go\.jp|lg\.jp|or\.jp|ac\.jp)(/|$)")


def _read(r):
    d = r.read()
    enc = (r.headers.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            d = gzip.decompress(d)
        elif enc == "deflate":
            d = zlib.decompress(d, -zlib.MAX_WBITS)
    except Exception:
        pass
    return d


def safe(s, url, fallback):
    """第1バッチの上書き事故対策: ラベルに URL のハッシュを足して一意にする。"""
    s = re.sub(r"[^0-9A-Za-z぀-ヿ一-鿿]+", "_", (s or "").strip())[:50].strip("_") or fallback
    return f"{s}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def fetch(name, url):
    rec = {"name": name, "url": url}
    try:
        req = urllib.request.Request(url, headers=H)
        with urllib.request.urlopen(req, timeout=90) as r:
            if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
                rec["status"] = r.status
                rec["skipped"] = "too_large_declared"
                return rec
            body = _read(r)
            rec["status"] = r.status
            rec["final_url"] = r.geturl()
            ctype = (r.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        return rec
    except Exception as e:
        rec["error"] = repr(e)
        return rec

    if len(body) > MAX_BYTES:
        rec["skipped"] = f"too_large_actual:{len(body)}"
        return rec

    is_pdf = body[:5] == b"%PDF"
    ext = ".pdf" if (is_pdf or "pdf" in ctype or url.lower().endswith(".pdf")) else (
        ".json" if "json" in ctype else ".html")
    p = OUT / (name + ext)
    p.write_bytes(body)
    rec["bytes"] = len(body)

    if ext == ".pdf":
        try:
            subprocess.run(["pdftotext", "-layout", str(p), str(p.with_suffix(".txt"))],
                           check=True, capture_output=True, timeout=300)
        except Exception as e:
            rec["pdftotext"] = repr(e)
    elif ext == ".html":
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body.decode("utf-8", "replace"),
                   flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", "\n", t)
        p.with_suffix(".txt").write_text(re.sub(r"\n{3,}", "\n\n", t))
    return rec


def links_of(rec, base):
    p = OUT / (rec["name"] + ".html")
    if not p.exists():
        return []
    html = p.read_bytes().decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        full = urllib.parse.urljoin(rec.get("final_url") or base, href)
        if "duckduckgo.com/l/" in full:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(full).query).get("uddg")
            if q:
                full = q[0]
        out.append((full, re.sub(r"\s+", " ", label).strip()))
    return out


def crawl(name, url, man, seen, depth2=8, per=6):
    r = fetch(name, url)
    man.append(r)
    kids = []
    for full, label in links_of(r, url):
        if full in seen:
            continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        if full.lower().endswith(DOC_EXT):
            man.append(fetch(f"{name}__{safe(label, full, 'd')}", full))
        else:
            kids.append((full, label))
    for full, label in kids[:depth2]:
        n2 = f"{name}__{safe(label, full, 'sub')}"
        r2 = fetch(n2, full)
        man.append(r2)
        c = 0
        for f3, l3 in links_of(r2, full):
            if f3 in seen or not f3.lower().endswith(DOC_EXT):
                continue
            if not (LINK_KEY.search(l3) or LINK_KEY.search(urllib.parse.unquote(f3))):
                continue
            seen.add(f3)
            man.append(fetch(f"{n2}__{safe(l3, f3, 'd')}", f3))
            c += 1
            if c >= per:
                break


def harvest(name, url, man, seen, per=8):
    r = fetch(name, url)
    man.append(r)
    c = 0
    for full, label in links_of(r, url):
        if full in seen:
            continue
        if not (GOV.search(full) or full.lower().endswith(".pdf")):
            continue
        if not (LINK_KEY.search(label) or LINK_KEY.search(urllib.parse.unquote(full))):
            continue
        seen.add(full)
        man.append(fetch(f"{name}__{safe(label, full, 'hit')}", full))
        c += 1
        if c >= per:
            break


KEYS = {
    "c2": re.compile(r"延べ面積|1住宅当たり|一住宅当たり|評価額|原単位|資産評価|デフレーター"),
    "g2": re.compile(r"再委託|主たる部分|設計共同体|共同設計|業務実績|有資格|参加資格|1128"),
    "e2": re.compile(r"リアルタイムハザードマップ|時点更新|見直し|改定|緊急減災|公告|業務"),
}


def digest():
    for tag, key in KEYS.items():
        hits = []
        for t in sorted(OUT.glob("*.txt")):
            if t.name.startswith("_") or not t.name.startswith(tag + "_"):
                continue
            rows = t.read_text(errors="replace").split("\n")
            for i, ln in enumerate(rows):
                if not key.search(ln):
                    continue
                ctx = [x.rstrip() for x in rows[max(0, i - 2):i + 3] if x.strip()]
                hits.append(f"[{t.name} L{i}] " + " / ".join(ctx))
        OUT.joinpath(f"_digest_{tag}.txt").write_text("\n".join(hits[:800]))
        print(f"digest {tag}: {len(hits)}")


def main():
    OUT.mkdir(exist_ok=True)
    man = []
    for n, u in SINGLE:
        man.append(fetch(n, u))
    seen = set()
    for n, u in INDEX:
        try:
            crawl(n, u, man, seen)
        except Exception as e:
            man.append({"name": n, "url": u, "error": "crawl:" + repr(e)})
    for n, u in SEARCH:
        try:
            harvest(n, u, man, seen)
        except Exception as e:
            man.append({"name": n, "url": u, "error": "harvest:" + repr(e)})
    OUT.joinpath("manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    digest()
    print("ok:", sum(1 for m in man if m.get("status") == 200), "/", len(man))


if __name__ == "__main__":
    main()
