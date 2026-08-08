#!/usr/bin/env python3
"""NEDO応募PoC用データ一括ダウンロードスクリプト（Claude Code / ローカル実行用）

やること:
  1) Open-Meteo: 川崎臨海部の時別気象 2020-2025（気温・降水・雲量・風速）→ CSV
  2) Landsat 8/9 Collection2 Level-2 地表面温度(ST_B10): 京浜臨海部を雲量<20%で
     四半期ごとに1シーン選定し、対象範囲だけ切り出した小さなGeoTIFFで保存
  3) すべて poc_data/ に格納し poc_data.zip に圧縮

実行: python3 download_poc_data.py
依存: 自動インストール（requests, pystac-client, planetary-computer, rasterio）
出力: poc_data.zip（合計 数十MB程度）→ これをCoworkの会話にアップロードしてください
"""
import subprocess, sys, os, json, zipfile

def ensure(pkgs):
    for p in pkgs:
        try:
            __import__(p.replace("-", "_"))
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", p])

ensure(["requests", "pystac-client", "planetary-computer", "rasterio"])
import requests, planetary_computer, rasterio
from pystac_client import Client
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

OUT = "poc_data"
os.makedirs(OUT, exist_ok=True)
BBOX = (139.60, 35.40, 139.84, 35.60)  # 京浜臨海部（川崎・横浜・鶴見・扇島・浮島）

# ---------- 1) Open-Meteo ----------
print("[1/2] Open-Meteo 気象データ...")
url = ("https://archive-api.open-meteo.com/v1/archive"
       "?latitude=35.53&longitude=139.70&start_date=2020-01-01&end_date=2025-12-31"
       "&hourly=temperature_2m,precipitation,cloud_cover,wind_speed_10m"
       "&timezone=Asia%2FTokyo&format=csv")
r = requests.get(url, timeout=120)
r.raise_for_status()
wpath = f"{OUT}/openmeteo_kawasaki_hourly_2020-2025.csv"
open(wpath, "wb").write(r.content)
print(f"  -> {wpath} ({len(r.content)//1024} KB)")

# ---------- 2) Landsat ST_B10（切り出し） ----------
print("[2/2] Landsat C2L2 地表面温度...")
cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                  modifier=planetary_computer.sign_inplace)
search = cat.search(collections=["landsat-c2-l2"], bbox=BBOX,
                    datetime="2023-01-01/2026-08-01",
                    query={"eo:cloud_cover": {"lt": 20}, "platform": {"in": ["landsat-8", "landsat-9"]}})
items = sorted(search.item_collection(), key=lambda it: it.datetime)
print(f"  候補 {len(items)} シーン")
# 四半期ごとに最も雲の少ない1シーンを選定
by_q = {}
for it in items:
    q = (it.datetime.year, (it.datetime.month - 1)//3)
    if q not in by_q or it.properties["eo:cloud_cover"] < by_q[q].properties["eo:cloud_cover"]:
        by_q[q] = it
picked = [by_q[q] for q in sorted(by_q)]
print(f"  選定 {len(picked)} シーン（四半期ごと）")
manifest = []
for it in picked:
    href = it.assets["lwir11"].href if "lwir11" in it.assets else it.assets["ST_B10"].href
    date = it.datetime.strftime("%Y%m%d")
    dst = f"{OUT}/{date}_{it.properties['platform']}_ST_B10_keihin.tif"
    with rasterio.open(href) as src:
        wb = transform_bounds("EPSG:4326", src.crs, *BBOX)
        win = from_bounds(*wb, src.transform).round_offsets().round_lengths()
        data = src.read(1, window=win)
        prof = src.profile.copy()
        prof.update(height=data.shape[0], width=data.shape[1],
                    transform=src.window_transform(win), compress="deflate")
        with rasterio.open(dst, "w", **prof) as w:
            w.write(data, 1)
    manifest.append(dict(file=os.path.basename(dst), datetime=str(it.datetime),
                         cloud=it.properties["eo:cloud_cover"], platform=it.properties["platform"],
                         note="DN→K変換: DN*0.00341802+149.0, nodata=0"))
    print(f"  -> {dst} 雲量{it.properties['eo:cloud_cover']:.0f}%")
json.dump(manifest, open(f"{OUT}/landsat_manifest.json", "w"), indent=1)

# ---------- 圧縮 ----------
with zipfile.ZipFile("poc_data.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in os.listdir(OUT):
        z.write(f"{OUT}/{f}", f"poc_data/{f}")
print(f"\n完了: poc_data.zip ({os.path.getsize('poc_data.zip')//(1024*1024)} MB)")
print("→ このzipをCoworkの会話にアップロードしてください")
