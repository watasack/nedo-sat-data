#!/usr/bin/env python3
"""説明資料（60_shiryo/日本気象協会_ご説明.html）に貼る「実データ図」3点を生成する。

出力（scratchpad に SVG 断片を書き出し、HTML へ貼る）:
  fig_t1_landsat.svg  テーマ①: 実Landsat 14シーンの資産輝度温度 → 市街地参照との差
                      出所 20_theme1_保温劣化監視/poc/out/poc4_results_real.json（既定＝v2・全14シーン）
  fig_t1_image.svg    テーマ①: 実Landsat熱赤外画像そのもの（冬・夏の同一地域＋東扇島の等倍拡大）
                      出所 20_theme1_保温劣化監視/poc/data/*_ST_B10_keihin.tif
                           AOIは 20_theme1_保温劣化監視/poc/src/poc4_pipeline.py の AOIS と同一
  fig_t2_snowmap.svg  テーマ②: 蔵王・火口周辺の実消雪日マップ（既定＝2023/2019/2025の並置）と
                      9年分の中央値。年を選ぶと1枚を拡大する切替を持つ（9年すべてを焼き込み、
                      表示だけ切り替える。JSでは数値を組み立てない）
                      出所 30_theme2_ライフライン復旧/poc/data/snowmap/snow_doy_*.npy
                           30_theme2_ライフライン復旧/poc/out/t2_snowmap_results.json

依存なし（numpy/matplotlib/tifffile/pyproj を使わない）。.npy と GeoTIFF は手で読み、
PNG はパレット方式で手で書き、UTM への投影も手で実装してある。
この環境にはそれらのパッケージが入っていないため、あえてこの実装にしてある。
"""
import ast, array, base64, json, math, os, struct, zlib
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("SHIRYO_FIG_OUT", "/tmp")

# ---------------------------------------------------------------- .npy / PNG

def load_npy(path):
    with open(path, "rb") as f:
        assert f.read(6) == b"\x93NUMPY"
        maj, _ = f.read(2)
        n = 2 if maj == 1 else 4
        hlen = struct.unpack("<H" if maj == 1 else "<I", f.read(n))[0]
        hdr = ast.literal_eval(f.read(hlen).decode())
        rows, cols = hdr["shape"]
        a = array.array({"<f4": "f", "<f8": "d"}[hdr["descr"]])
        a.fromfile(f, rows * cols)
    return a, rows, cols


def png_palette(idx, w, h, palette):
    """インデックスカラーPNG（8bit・color type 3）をバイト列で返す。"""
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(idx[r * w:(r + 1) * w]) for r in range(h))
    plte = b"".join(bytes(c) for c in palette)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", plte)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# 消雪日のカラーランプ: 早い＝エンバー（資料の --accent 系）／遅い＝寒色（--unk 系）。
# 中間は白に寄せない——欠測（灰）と見分けがつかなくなるため。
RAMP = [(0.00, (150, 58, 22)), (0.27, (216, 148, 78)), (0.50, (226, 205, 168)),
        (0.73, (118, 160, 186)), (1.00, (30, 60, 84))]
MISSING = (152, 155, 160)   # 欠測。ランプのどの色とも十分に離す
OUTSIDE = (243, 243, 241)   # 火口半径3kmの外＝集計に入れない画素
DOY_MIN, DOY_MAX = 90.0, 210.0
NCOL = 200  # index 0 は欠測、index 1 は範囲外に予約
CIRCLE_R_M, PIXEL_M = 3000.0, 30.0


def ramp_rgb(t):
    t = min(max(t, 0.0), 1.0)
    for i in range(len(RAMP) - 1):
        a, ca = RAMP[i]
        b, cb = RAMP[i + 1]
        if a <= t <= b:
            u = 0.0 if b == a else (t - a) / (b - a)
            return tuple(round(ca[k] + (cb[k] - ca[k]) * u) for k in range(3))
    return RAMP[-1][1]


PALETTE = [MISSING, OUTSIDE] + [ramp_rgb(i / (NCOL - 1)) for i in range(NCOL)]


# ---------------------------------------------------------------- GeoTIFF / UTM

def read_geotiff(path):
    """Landsat ST_B10 の tiled・deflate・uint16 の GeoTIFF だけを読む最小実装。"""
    d = open(path, "rb").read()
    bo = "<" if d[:2] == b"II" else ">"
    off, = struct.unpack(bo + "I", d[4:8])
    n, = struct.unpack(bo + "H", d[off:off + 2])
    tags = {}
    for i in range(n):
        e = off + 2 + i * 12
        tag, typ, cnt = struct.unpack(bo + "HHI", d[e:e + 8])
        sz = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}.get(typ, 1)
        tot = sz * cnt
        raw = (d[e + 8:e + 8 + tot] if tot <= 4
               else d[struct.unpack(bo + "I", d[e + 8:e + 12])[0]:][:tot])
        if typ in (3, 4, 12):
            tags[tag] = struct.unpack(bo + {3: "H", 4: "I", 12: "d"}[typ] * cnt, raw)
    W, H = tags[256][0], tags[257][0]
    assert tags[259][0] == 8 and tags[258][0] == 16, "deflate/uint16 のみ対応"
    tw, th = tags[322][0], tags[323][0]
    ntx = (W + tw - 1) // tw
    img = [[0] * W for _ in range(H)]
    for k, (o, c) in enumerate(zip(tags[324], tags[325])):
        vals = struct.unpack(bo + "H" * (tw * th), zlib.decompress(d[o:o + c]))
        tx, ty = (k % ntx) * tw, (k // ntx) * th
        for r in range(th):
            gy = ty + r
            if gy >= H:
                break
            row, base = img[gy], r * tw
            for cc in range(min(tw, W - tx)):
                row[tx + cc] = vals[base + cc]
    tie = tags[33922]
    geo = dict(x0=tie[3], y0=tie[4], sx=tags[33550][0], sy=tags[33550][1], W=W, H=H)
    return img, geo


def wgs84_to_utm54n(lon, lat):
    """UTM zone 54N（中央子午線141°E）への順投影。pyproj が無いので実装した。"""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0, lon0 = 0.9996, math.radians(141.0)
    p, l = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    T = math.tan(p) ** 2
    C = ep2 * math.cos(p) ** 2
    A = (l - lon0) * math.cos(p)
    M = a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * p
             - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * p)
             + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * p)
             - (35 * e2**3 / 3072) * math.sin(6 * p))
    x = k0 * N * (A + (1 - T + C) * A**3 / 6
                  + (5 - 18 * T + T**2 + 72 * C - 58 * ep2) * A**5 / 120) + 500000.0
    y = k0 * (M + N * math.tan(p) * (A**2 / 2 + (5 - T + 9 * C + 4 * C**2) * A**4 / 24
              + (61 - 58 * T + T**2 + 600 * C - 330 * ep2) * A**6 / 720))
    return x, y


def doy_label(doy, year=2019):
    """通日 → 「5月2日」。年を渡すとその年の暦で換算する（閏年で1日ずれるため）。"""
    d = date.fromordinal(date(int(year), 1, 1).toordinal() + doy - 1)
    return f"{d.month}月{d.day}日"


def med_label(v, year):
    """画素中央値は .5 を取り得るので、挟む2日を「5月5〜6日」の形で出す（切り捨て・切り上げが
    2箇所で食い違わないように、ラベルの作り方をここ1箇所に閉じる）。"""
    lo, hi = int(v // 1), int(-(-v // 1))
    if lo == hi:
        return doy_label(lo, year)
    a, b = doy_label(lo, year), doy_label(hi, year)
    am, ad = a.split("月"); bm, bd = b.split("月")
    return f"{a[:-1]}〜{bd}" if am == bm else f"{a}〜{b}"


def snow_png_datauri(year):
    """.npy は火口±3kmの矩形なので、円の外は「範囲外」で塗って集計から外す。"""
    a, rows, cols = load_npy(os.path.join(
        ROOT, "30_theme2_ライフライン復旧/poc/data/snowmap", f"snow_doy_{year}.npy"))
    cy, cx, r = (rows - 1) / 2.0, (cols - 1) / 2.0, CIRCLE_R_M / PIXEL_M
    idx = bytearray(rows * cols)
    for i, v in enumerate(a):
        if ((i // cols) - cy) ** 2 + ((i % cols) - cx) ** 2 > r * r:
            idx[i] = 1                  # 火口から3kmの外
        elif v != v:                    # NaN = 欠測
            idx[i] = 0
        else:
            t = (v - DOY_MIN) / (DOY_MAX - DOY_MIN)
            idx[i] = 2 + min(max(int(round(t * (NCOL - 1))), 0), NCOL - 1)
    png = png_palette(idx, cols, rows, PALETTE)
    return "data:image/png;base64," + base64.b64encode(png).decode(), rows, cols, len(png)


# ---------------------------------------------------------------- 図①

def fig_t1():
    d = json.load(open(os.path.join(
        ROOT, "20_theme1_保温劣化監視/poc/out/poc4_results_real.json")))
    ref = d["ref_series_K"]
    series = d["series_vs_urban_ref_K"]
    epochs = [date(int(e[:4]), int(e[4:6]), int(e[6:])) for e in d["epochs"]]
    x0, x1 = epochs[0].toordinal(), epochs[-1].toordinal()

    # 左パネル: 絶対輝度温度（資産＝参照＋差。JSON の 42.97/44.05/12.53 を再現する）
    L = dict(x=58, y=30, w=318, h=196)
    R = dict(x=490, y=30, w=290, h=196)
    LKMIN, LKMAX = 272.0, 324.0
    RKMIN, RKMAX = -10.0, 3.0

    def px(t):  # 日付 → x 比
        return (t.toordinal() - x0) / (x1 - x0)

    def path(panel, vals, kmin, kmax):
        segs, cur = [], []
        for i, v in enumerate(vals):
            if v is None:
                if len(cur) > 1:
                    segs.append(cur)
                cur = []
                continue
            X = panel["x"] + px(epochs[i]) * panel["w"]
            Y = panel["y"] + panel["h"] * (1 - (v - kmin) / (kmax - kmin))
            cur.append((X, Y))
        if len(cur) > 1:
            segs.append(cur)
        return " ".join("M" + " L".join(f"{X:.1f} {Y:.1f}" for X, Y in s) for s in segs), \
               [(panel["x"] + px(epochs[i]) * panel["w"],
                 panel["y"] + panel["h"] * (1 - (v - kmin) / (kmax - kmin)))
                for i, v in enumerate(vals) if v is not None]

    o = []
    A = o.append
    A('<svg viewBox="0 0 860 288" role="img" aria-label="実Landsat 14シーンの資産地表温度。'
      'そのままでは42.97Kばらつくが、市街地参照との差にすると12.53Kに落ちる。">')

    for panel, kmin, kmax, ticks, unit in (
            (L, LKMIN, LKMAX, [280, 290, 300, 310, 320], "K"),
            (R, RKMIN, RKMAX, [-9, -6, -3, 0, 3], "K")):
        A(f'<rect x="{panel["x"]}" y="{panel["y"]}" width="{panel["w"]}" height="{panel["h"]}" '
          'fill="var(--surface-2)" opacity=".55"></rect>')
        for t in ticks:
            Y = panel["y"] + panel["h"] * (1 - (t - kmin) / (kmax - kmin))
            A(f'<line x1="{panel["x"]}" y1="{Y:.1f}" x2="{panel["x"]+panel["w"]}" y2="{Y:.1f}" '
              'stroke="currentColor" stroke-width="1" opacity=".13"></line>')
            A(f'<text class="s-xs s-num" x="{panel["x"]-6}" y="{Y+4:.1f}" text-anchor="end">{t}</text>')
        A(f'<text class="s-xs" x="{panel["x"]-6}" y="{panel["y"]-8}" text-anchor="end">{unit}</text>')
        for yr in (2023, 2024, 2025, 2026):
            X = panel["x"] + px(date(yr, 1, 1)) * panel["w"]
            if panel["x"] <= X <= panel["x"] + panel["w"]:
                A(f'<line x1="{X:.1f}" y1="{panel["y"]}" x2="{X:.1f}" y2="{panel["y"]+panel["h"]}" '
                  'stroke="currentColor" stroke-width="1" opacity=".10"></line>')
                A(f'<text class="s-xs s-num" x="{X:.1f}" y="{panel["y"]+panel["h"]+16}" '
                  f'text-anchor="middle">{yr}</text>')

    # 左: 参照面（市街地）
    dsh, pts = path(L, ref, LKMIN, LKMAX)
    A(f'<path d="{dsh}" fill="none" stroke="var(--unk)" stroke-width="1.8" '
      'stroke-dasharray="5 3"></path>')
    for X, Y in pts:
        A(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.2" fill="var(--unk)"></circle>')

    HL = "東扇島火力"
    for name, vals in series.items():
        abs_ = [None if v is None else ref[i] + v for i, v in enumerate(vals)]
        acc = name == HL
        col = "var(--accent)" if acc else "var(--ink-3)"
        wdt = 2.0 if acc else 1.3
        op = "1" if acc else ".45"
        for panel, vv, kmin, kmax in ((L, abs_, LKMIN, LKMAX), (R, vals, RKMIN, RKMAX)):
            dd, pts = path(panel, vv, kmin, kmax)
            A(f'<path d="{dd}" fill="none" stroke="{col}" stroke-width="{wdt}" '
              f'opacity="{op}" stroke-linejoin="round"><title>{name}</title></path>')
            for X, Y in pts:
                A(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{2.4 if acc else 1.8}" '
                  f'fill="{col}" opacity="{op}"></circle>')

    # 振れ幅のブラケット
    def bracket(panel, x, lo, hi, kmin, kmax, label):
        Y1 = panel["y"] + panel["h"] * (1 - (hi - kmin) / (kmax - kmin))
        Y2 = panel["y"] + panel["h"] * (1 - (lo - kmin) / (kmax - kmin))
        A(f'<path d="M{x-5} {Y1:.1f} L{x} {Y1:.1f} L{x} {Y2:.1f} L{x-5} {Y2:.1f}" '
          'fill="none" stroke="var(--accent)" stroke-width="1.4"></path>')
        A(f'<text class="s-sm s-num s-acc" x="{x+6}" y="{Y1+4:.1f}" '
          f'font-weight="600">{label}</text>')
        A(f'<text class="s-xs" x="{x+6}" y="{Y1+20:.1f}" fill="var(--ink-3)">振れ幅</text>')

    allabs = [ref[i] + v for vals in series.values() for i, v in enumerate(vals) if v is not None]
    alldif = [v for vals in series.values() for v in vals if v is not None]
    bracket(L, L["x"] + L["w"] + 8, min(allabs), max(allabs), LKMIN, LKMAX, "42.97 K")
    bracket(R, R["x"] + R["w"] + 8, min(alldif), max(alldif), RKMIN, RKMAX, "12.53 K")

    Y0 = R["y"] + R["h"] * (1 - (0 - RKMIN) / (RKMAX - RKMIN))
    A(f'<line x1="{R["x"]}" y1="{Y0:.1f}" x2="{R["x"]+R["w"]}" y2="{Y0:.1f}" '
      'stroke="currentColor" stroke-width="1" opacity=".45"></line>')
    A(f'<text class="s-hd" x="{L["x"]}" y="18">そのまま並べる（資産AOIの地表温度）</text>')
    A(f'<text class="s-hd" x="{R["x"]}" y="18">市街地参照との差にする</text>')
    mx = (L["x"] + L["w"] + R["x"]) / 2
    A(f'<text class="s-xs" x="{mx:.0f}" y="150" text-anchor="middle" fill="var(--ink-3)">同じ空の'
      f'<tspan x="{mx:.0f}" dy="15">下にある</tspan>'
      f'<tspan x="{mx:.0f}" dy="15">参照面を</tspan>'
      f'<tspan x="{mx:.0f}" dy="15">引き算</tspan></text>')
    A(f'<path d="M{mx-26:.0f} 214 L{mx+20:.0f} 214" stroke="var(--accent)" '
      'stroke-width="1.4" opacity=".7"></path>'
      f'<path d="M{mx+14:.0f} 209 L{mx+24:.0f} 214 L{mx+14:.0f} 219 Z" fill="var(--accent)" '
      'opacity=".7"></path>')
    A('<g transform="translate(58,258)">'
      '<line x1="0" y1="-4" x2="22" y2="-4" stroke="var(--accent)" stroke-width="2"></line>'
      '<text class="s-xs" x="28" y="0">東扇島火力</text>'
      '<line x1="120" y1="-4" x2="142" y2="-4" stroke="var(--ink-3)" stroke-width="1.3" opacity=".45"></line>'
      '<text class="s-xs" x="148" y="0">他5地区</text>'
      '<line x1="230" y1="-4" x2="252" y2="-4" stroke="var(--unk)" stroke-width="1.8" stroke-dasharray="5 3"></line>'
      '<text class="s-xs" x="258" y="0">市街地参照（鶴見区）</text>'
      '<text class="s-xs" x="410" y="0" fill="var(--ink-3)">線の切れ目は雲・スワス端による欠測</text>'
      '</g>')
    A("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- 図①b（実画像）

# 資料の gThermalScale と同じ配色（熱赤外の見た目を図2と揃える）
THERMAL = [(0.00, (11, 6, 22)), (0.22, (59, 16, 85)), (0.45, (140, 31, 92)),
           (0.66, (214, 75, 44)), (0.85, (245, 155, 42)), (1.00, (255, 233, 168))]
NODATA_RGB = (110, 114, 120)
# 物差しはシーンごとに取り直す。冬（282〜290K）と夏（300〜330K）を同じ固定幅に載せると
# 冬が真っ黒に潰れて何も読めなくなるため。**代わりに各パネルの下に実際の範囲を数字で出す。**

# poc4_pipeline.py の AOIS と同一（±数百mの概略AOI）
AOIS = {
    "川崎火力": (139.750, 35.512, 139.762, 35.522),
    "東扇島火力": (139.745, 35.495, 139.760, 35.505),
    "浮島製油所": (139.765, 35.520, 139.785, 35.535),
    "水江町製油所": (139.720, 35.515, 139.735, 35.525),
    "扇島製鉄所": (139.700, 35.470, 139.730, 35.490),
    "大黒町火力": (139.680, 35.462, 139.690, 35.472),
}
REF_AOI_V2 = (139.6615, 35.4952, 139.6815, 35.5098)
SCENES = [("20230108_landsat-9", "2023年1月8日（冬）"),
          ("20250902_landsat-8", "2025年9月2日（夏）")]
TIF = "20_theme1_保温劣化監視/poc/data/{}_ST_B10_keihin.tif"


def thermal_rgb(t):
    t = min(max(t, 0.0), 1.0)
    for i in range(len(THERMAL) - 1):
        a, ca = THERMAL[i]
        b, cb = THERMAL[i + 1]
        if a <= t <= b:
            u = 0.0 if b == a else (t - a) / (b - a)
            return tuple(round(ca[k] + (cb[k] - ca[k]) * u) for k in range(3))
    return THERMAL[-1][1]


TPAL = [NODATA_RGB] + [thermal_rgb(i / (NCOL - 1)) for i in range(NCOL)]


def tb_stretch(img):
    """有効画素の 2〜98 パーセンタイルを返す（表示の物差し）。"""
    vals = sorted(v * 0.00341802 + 149.0 for row in img for v in row if v)
    return vals[int(0.02 * len(vals))], vals[int(0.98 * len(vals))]


def tb_range(img):
    """有効画素の実際の最小・最大[K]。表示レンジ（2〜98%）と混同しないため別に出す。"""
    vals = [v * 0.00341802 + 149.0 for row in img for v in row if v]
    return min(vals), max(vals)


def tb_png(img, lo, hi, box=None, bin_=1):
    """DN → 輝度温度[K] → パレットPNG。box=(c0,r0,c1,r1) で切り出す。

    bin_=2 は 2×2 平均に間引く（全景パネルは 246 px 幅で表示するので 735 px は要らない。
    等倍が意味を持つ拡大パネルは bin_=1 のまま使うこと）。
    """
    r0, r1 = (0, len(img)) if box is None else (box[1], box[3])
    c0, c1 = (0, len(img[0])) if box is None else (box[0], box[2])
    w, h = (c1 - c0) // bin_, (r1 - r0) // bin_
    idx = bytearray(w * h)
    for r in range(h):
        base = r * w
        for c in range(w):
            s = n = 0
            for dr in range(bin_):
                row = img[r0 + r * bin_ + dr]
                for dc in range(bin_):
                    dn = row[c0 + c * bin_ + dc]
                    if dn:
                        s += dn
                        n += 1
            if not n:                       # nodata
                continue
            t = ((s / n * 0.00341802 + 149.0) - lo) / (hi - lo)
            idx[base + c] = 1 + min(max(int(round(t * (NCOL - 1))), 0), NCOL - 1)
    return ("data:image/png;base64,"
            + base64.b64encode(png_palette(idx, w, h, TPAL)).decode()), w, h


def fig_t1_image():
    o = []
    A = o.append
    A('<svg viewBox="0 0 860 410" role="img" aria-label="京浜臨海部の実Landsat熱赤外画像。'
      '冬と夏の同一地域と、東扇島火力の等倍拡大。">')

    W = 246
    scenes = []
    for key, _lab in SCENES:
        img, geo = read_geotiff(os.path.join(ROOT, TIF.format(key)))
        scenes.append((img, geo))

    def to_px(geo, lon, lat):
        x, y = wgs84_to_utm54n(lon, lat)
        return (x - geo["x0"]) / geo["sx"], (geo["y0"] - y) / geo["sy"]

    # 拡大窓（東扇島火力のAOIに余白を付けた 70×60 画素 ＝ 2.1×1.8 km）
    ZOOM = (430, 345, 500, 405)

    total = 0
    stretches = [tb_stretch(img) for img, _ in scenes]
    ranges = [tb_range(img) for img, _ in scenes]
    for k, ((img, geo), (key, lab)) in enumerate(zip(scenes, SCENES)):
        lo, hi = stretches[k]
        uri, w, h = tb_png(img, lo, hi, bin_=2)
        total += len(uri)
        x = 22 + k * (W + 24)
        hh = W * h / w
        sc = W / (w * 2)      # w は間引き後の画素数。枠は元画素の座標で描く
        A(f'<text class="s-hd s-num" x="{x}" y="16">{lab}</text>')
        A(f'<rect x="{x}" y="24" width="{W}" height="{hh:.1f}" fill="var(--surface-2)"></rect>')
        A(f'<image x="{x}" y="24" width="{W}" height="{hh:.1f}" href="{uri}"></image>')
        for nm, (a0, b0, a1, b1) in AOIS.items():
            px0, py0 = to_px(geo, a0, b1)
            px1, py1 = to_px(geo, a1, b0)
            for st, wd in (("#12161C", 2.6), ("#FFF", 1.0)):
                A(f'<rect x="{x+px0*sc:.1f}" y="{24+py0*sc:.1f}" width="{(px1-px0)*sc:.1f}" '
                  f'height="{(py1-py0)*sc:.1f}" fill="none" stroke="{st}" stroke-width="{wd}" '
                  'opacity=".85"></rect>')
        rx0, ry0 = to_px(geo, REF_AOI_V2[0], REF_AOI_V2[3])
        rx1, ry1 = to_px(geo, REF_AOI_V2[2], REF_AOI_V2[1])
        A(f'<rect x="{x+rx0*sc:.1f}" y="{24+ry0*sc:.1f}" width="{(rx1-rx0)*sc:.1f}" '
          f'height="{(ry1-ry0)*sc:.1f}" fill="none" stroke="#7FD1E8" stroke-width="1.2" '
          'stroke-dasharray="4 3"></rect>')
        if k == 0:
            A(f'<rect x="{x+ZOOM[0]*sc:.1f}" y="{24+ZOOM[1]*sc:.1f}" '
              f'width="{(ZOOM[2]-ZOOM[0])*sc:.1f}" height="{(ZOOM[3]-ZOOM[1])*sc:.1f}" '
              'fill="none" stroke="#FFE9A8" stroke-width="1.4"></rect>')
            sb = 5000 / 30 * sc      # 5 km
            A(f'<g transform="translate({x+10:.1f},{24+hh-12:.1f})">'
              f'<rect x="-6" y="-16" width="{sb+12:.1f}" height="24" fill="#000" opacity=".35" rx="2"></rect>'
              f'<line x1="0" y1="0" x2="{sb:.1f}" y2="0" stroke="#FFF" stroke-width="2"></line>'
              f'<text class="s-xs" x="{sb/2:.1f}" y="-4" text-anchor="middle" fill="#FFF">5 km</text></g>')
        A(f'<rect x="{x}" y="24" width="{W}" height="{hh:.1f}" fill="none" '
          'stroke="var(--rule)"></rect>')
        rng = ranges[k]
        A(f'<text class="s-xs s-num" x="{x}" y="{24+hh+16:.1f}" fill="var(--ink-2)">'
          f'表示レンジ(2–98%) <tspan font-weight="600" fill="var(--accent-ink)">'
          f'{lo:.1f} – {hi:.1f} K</tspan>'
          f'<tspan class="s-xs" x="{x}" dy="14" fill="var(--ink-3)">'
          f'実際は {rng[0]:.1f} – {rng[1]:.1f} K</tspan></text>')

    # 3枚目: 冬シーンの等倍拡大（物差しは冬パネルと同じ）
    img, geo = scenes[0]
    uri, zw, zh = tb_png(img, stretches[0][0], stretches[0][1], ZOOM)
    total += len(uri)
    x = 22 + 2 * (W + 24)
    hh = W * zh / zw
    scz = W / zw
    A(f'<text class="s-hd" x="{x}" y="16">東扇島火力の拡大（冬・間引きなし）</text>')
    A(f'<image x="{x}" y="24" width="{W}" height="{hh:.1f}" href="{uri}" '
      'style="image-rendering:pixelated"></image>')
    px0, py0 = to_px(geo, AOIS["東扇島火力"][0], AOIS["東扇島火力"][3])
    px1, py1 = to_px(geo, AOIS["東扇島火力"][2], AOIS["東扇島火力"][1])
    A(f'<rect x="{x+(px0-ZOOM[0])*scz:.1f}" y="{24+(py0-ZOOM[1])*scz:.1f}" '
      f'width="{(px1-px0)*scz:.1f}" height="{(py1-py0)*scz:.1f}" fill="none" '
      'stroke="#FFE9A8" stroke-width="1.6"></rect>')
    # 30m画素1つと、そこに入る設備の大きさ
    for st, wd in (("#12161C", 3.2), ("#FFF", 1.6)):
        A(f'<rect x="{x+34*scz:.1f}" y="{24+34*scz:.1f}" width="{scz:.1f}" height="{scz:.1f}" '
          f'fill="none" stroke="{st}" stroke-width="{wd}"></rect>')
    A(f'<rect x="{x+(34+5/30)*scz:.1f}" y="{24+(34+5/30)*scz:.1f}" '
      f'width="{scz*20/30:.1f}" height="{scz*20/30:.1f}" fill="none" stroke="#7FD1E8" '
      'stroke-width="1.4"></rect>')
    A(f'<rect x="{x}" y="24" width="{W}" height="{hh:.1f}" fill="none" stroke="var(--rule)"></rect>')
    A(f'<g transform="translate({x},{24+hh+8:.1f})">'
      '<rect x="0" y="2" width="11" height="11" fill="none" stroke="var(--ink-2)" stroke-width="1.4"></rect>'
      '<text class="s-xs" x="17" y="11">30 m画素1つ</text>'
      '<rect x="102" y="4" width="7.3" height="7.3" fill="none" stroke="#3E93AE" stroke-width="1.4"></rect>'
      '<text class="s-xs" x="115" y="11">20 m角の設備 ＝ 0.44画素</text></g>')

    # 凡例とカラーバー
    ytop = 24 + W * 749 / 735 + 66
    A('<defs><linearGradient id="gTb" x1="0" y1="0" x2="1" y2="0">')
    for i in range(0, 21):
        r, g, b = thermal_rgb(i / 20)
        A(f'<stop offset="{i*5}%" stop-color="rgb({r},{g},{b})"></stop>')
    A("</linearGradient></defs>")
    cbx, cbw = 22, 300
    A(f'<rect x="{cbx}" y="{ytop}" width="{cbw}" height="13" fill="url(#gTb)" '
      'stroke="var(--rule)"></rect>')
    A(f'<text class="s-xs" x="{cbx}" y="{ytop+28}">その日の下端</text>')
    A(f'<text class="s-xs" x="{cbx+cbw}" y="{ytop+28}" text-anchor="end">その日の上端</text>')
    A(f'<text class="s-xs" x="{cbx}" y="{ytop-6}">地表温度（<tspan font-weight="600">'
      '物差しはシーンごとに取り直し、上位2%は白飛びさせている</tspan>）</text>')
    A(f'<g transform="translate({cbx+cbw+40},{ytop})">'
      '<rect x="0" y="1" width="16" height="11" fill="none" stroke="#8A8F98" stroke-width="1.2"></rect>'
      '<text class="s-xs" x="22" y="11">白枠＝資産AOI 6地区</text>'
      '<g transform="translate(0,20)">'
      '<rect x="0" y="1" width="16" height="11" fill="none" stroke="#3E93AE" stroke-width="1.2" '
      'stroke-dasharray="4 3"></rect>'
      '<text class="s-xs" x="22" y="11">青破線＝市街地参照面（鶴見区）</text></g>'
      '<g transform="translate(0,40)">'
      '<rect x="0" y="1" width="16" height="11" fill="none" stroke="#C79A3A" stroke-width="1.4"></rect>'
      '<text class="s-xs" x="22" y="11">黄枠＝右の拡大範囲（2.1 × 1.8 km）</text></g></g>')
    A("</svg>")
    print(f"  実画像3枚の base64 合計: {total/1024:.0f} KB")
    return "\n".join(o)


# ---------------------------------------------------------------- 図②

def fig_t2():
    res = json.load(open(os.path.join(
        ROOT, "30_theme2_ライフライン復旧/poc/out/t2_snowmap_results.json")))
    # 中央値・決定率は「火口半径3kmの円」で取り直したものを使う（矩形は円の外接矩形で、
    # 四隅が火口から4.3km ある。2022年は 117.0 → 144.5 日目と入れ替わる）
    circ = json.load(open(os.path.join(
        ROOT, "30_theme2_ライフライン復旧/poc/out/t2_snowmap_circle_r3km.json")))["円_半径3km"]["年別"]
    years = res["years"]
    show = ["2023", "2019", "2025"]
    W = 246                       # 1枚の描画幅[px]
    o = []
    A = o.append
    A('<svg viewBox="0 0 860 512" role="img" aria-label="蔵王山 火口半径3kmの消雪日マップ3年分と、'
      '9年分の消雪日中央値。年によって中央値が102日から148日まで動く。'
      '年を選ぶと、その年1枚を拡大して観測日数・決定率・挟み込み間隔とともに表示する。">')
    A('<g id="snowRow3">')

    total = 0
    for k, y in enumerate(show):
        uri, rows, cols, nbytes = snow_png_datauri(y)
        total += nbytes
        x = 22 + k * (W + 24)
        h = W * rows / cols
        A(f'<text class="s-hd s-num" x="{x}" y="16">{y} 年</text>')
        # scenes は同一日の重複（Landsat のタイル分割等）を含むので、日付でユニーク化する。
        # t2_meltout_accuracy.py の year_dates() も set() で同じ処理をしている。
        ndays = len({s[:10] for s in years[y]["dates"]})
        A(f'<text class="s-xs s-num" x="{x+W}" y="16" text-anchor="end" fill="var(--ink-3)">'
          f'観測日 {ndays} 日・間隔 {years[y]["gap_median_days"]:.0f} 日</text>')
        A(f'<rect x="{x}" y="24" width="{W}" height="{h:.1f}" fill="var(--surface-2)"></rect>')
        A(f'<image x="{x}" y="24" width="{W}" height="{h:.1f}" href="{uri}" '
          'style="image-rendering:pixelated"></image>')
        # 火口の位置（AOI の中心＝140.44E, 38.14N）。AOI は中心±3km
        cx, cy = x + W / 2, 24 + h / 2
        A(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="none" stroke="#FFF" '
          'stroke-width="2.4" opacity=".85"></circle>')
        A(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="none" stroke="#1B2028" '
          'stroke-width="1.1"></circle>')
        # 円の境界は「範囲外」の白塗りが示すので、破線は描かない（描くと半径がずれて見える。
        # 白塗りの境界は 121.8 px、W/2 は 123.0 px）。
        if k == 0:
            A(f'<text class="s-xs" x="{cx+12:.1f}" y="{cy+4:.1f}" fill="#FFF" '
              'style="paint-order:stroke" stroke="#1B2028" stroke-width="2.5">火口</text>')
        A(f'<rect x="{x}" y="24" width="{W}" height="{h:.1f}" fill="none" '
          'stroke="var(--rule)"></rect>')
        A(f'<text class="s-sm s-num" x="{x}" y="{24+h+18:.1f}" fill="var(--ink-2)">'
          f'画素中央値 <tspan font-weight="600" fill="var(--accent-ink)">'
          f'{circ[y]["画素中央値"]:g} 日目</tspan>'
          f'（{med_label(circ[y]["画素中央値"], y)}ごろ）</text>')
        if k == 0:   # スケールバー 1km。AOI は 202画素 × 30m = 6.06km 幅
            sb = W / 6.06
            A(f'<g transform="translate({x+10:.1f},{24+h-12:.1f})">'
              f'<rect x="-6" y="-16" width="{sb+12:.1f}" height="24" fill="#000" opacity=".35" '
              'rx="2"></rect>'
              f'<line x1="0" y1="0" x2="{sb:.1f}" y2="0" stroke="#FFF" stroke-width="2"></line>'
              f'<text class="s-xs" x="{sb/2:.1f}" y="-4" text-anchor="middle" fill="#FFF">1 km</text></g>')

    A('</g>')

    # ---- 年を1つ選んだときの拡大表示（9年分すべてを焼き込み、表示だけ切り替える）----
    # 数値はここで実データから書き出しておき、JS では文字を組み立てない
    # （組み立てると、存在しない数字を作る余地ができる）。
    # 拡大時の描画幅。カラーバーのラベル（ytop は並置の W 基準で決まる）に
    # 重ならない上限で取る——BW を上げると地図の下端が下がり、ラベルに被る。
    BW = 272
    BH = BW * 203 / 202
    A('<g id="snowOne" style="display:none">')
    for y in sorted(years):
        uri, rows, cols, nbytes = snow_png_datauri(y)
        total += nbytes
        d, yy = circ[y], years[y]
        ndays = len({s[:10] for s in yy["dates"]})
        med = d["画素中央値"]
        A(f'<g id="snowY{y}" style="display:none">')
        A(f'<text class="s-hd s-num" x="22" y="16">{y} 年</text>')
        A(f'<rect x="22" y="24" width="{BW}" height="{BH:.1f}" fill="var(--surface-2)"></rect>')
        A(f'<image x="22" y="24" width="{BW}" height="{BH:.1f}" href="{uri}" '
          'style="image-rendering:pixelated"></image>')
        cx, cy = 22 + BW / 2, 24 + BH / 2
        A(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="none" stroke="#FFF" '
          'stroke-width="2.6" opacity=".85"></circle>')
        A(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="none" stroke="#1B2028" '
          'stroke-width="1.2"></circle>')
        A(f'<text class="s-xs" x="{cx+13:.1f}" y="{cy+4:.1f}" fill="#FFF" '
          'style="paint-order:stroke" stroke="#1B2028" stroke-width="2.5">火口</text>')
        sb = BW / 6.06
        A(f'<g transform="translate(32,{24+BH-12:.1f})">'
          f'<rect x="-6" y="-16" width="{sb+12:.1f}" height="24" fill="#000" opacity=".35" rx="2"></rect>'
          f'<line x1="0" y1="0" x2="{sb:.1f}" y2="0" stroke="#FFF" stroke-width="2"></line>'
          f'<text class="s-xs" x="{sb/2:.1f}" y="-4" text-anchor="middle" fill="#FFF">1 km</text></g>')
        A(f'<rect x="22" y="24" width="{BW}" height="{BH:.1f}" fill="none" stroke="var(--rule)"></rect>')
        # 右側の数値（すべて実測。単位と出所は figcaption 側に書いてある）
        tx = 356
        A(f'<text class="s-sm" x="{tx}" y="44" fill="var(--ink-2)">画素中央値</text>')
        A(f'<text class="s-hd s-num s-acc" x="{tx}" y="72" font-size="24">{med:g} 日目'
          f'<tspan class="s-sm" fill="var(--ink-2)" font-size="13.5">'
          f'（{med_label(med, y)}ごろ）</tspan></text>')
        A(f'<text class="s-sm" x="{tx}" y="112" fill="var(--ink-2)">'
          f'決められた画素 <tspan class="s-num" font-weight="600" fill="currentColor">'
          f'{d["決定率"]*100:.0f}%</tspan></text>')
        # 右の列は x=356 から幅504px しかないので、1行あたり全角43字を超えないこと
        # （超えると viewBox の外に出る。40_scripts の文字幅検査で落ちる）
        A(f'<text class="s-sm" x="{tx}" y="140" fill="var(--ink-2)">'
          f'観測日 <tspan class="s-num" font-weight="600" fill="currentColor">{ndays} 日</tspan>'
          f'　／　挟み込み間隔の中央値 <tspan class="s-num" font-weight="600" fill="currentColor">'
          f'{yy["gap_median_days"]:.0f} 日</tspan></text>')
        A(f'<text class="s-xs" x="{tx}" y="158">（間隔は矩形全体の値。円では取り直せていません）</text>')
        A(f'<text class="s-xs" x="{tx}" y="184">灰色は、その年は雲などで決められなかった画素です。</text>')
        A(f'<text class="s-xs" x="{tx}" y="202">灰色が減るかは枚数では決まりません（効くのは「いつ晴れたか」）。</text>')
        A(f'<text class="s-xs" x="{tx}" y="220">ただし<tspan font-weight="600" fill="currentColor">'
          '精度は挟み込み間隔が決めます</tspan>——間隔が広い年は、</text>')
        A(f'<text class="s-xs" x="{tx}" y="238">決まっていても幅が広いです（V-4）。</text>')
        if y == "2017":
            # 決定率は9年で3位なのに、実は最悪年である。ここを書かないと最良年に見える。
            A(f'<text class="s-xs s-acc" x="{tx}" y="264" font-weight="600">'
              'この年は決まった画素の98.5%が同じ1つの間隔に入っています（9年で最悪）。</text>')
        A('</g>')
    A('</g>')

    # カラーバー
    ytop = 24 + W * 203 / 202 + 52
    A(f'<defs><linearGradient id="gDoy" x1="0" y1="0" x2="1" y2="0">')
    for i in range(0, 21):
        r, g, b = ramp_rgb(i / 20)
        A(f'<stop offset="{i*5}%" stop-color="rgb({r},{g},{b})"></stop>')
    A("</linearGradient></defs>")
    cbx, cbw = 22, 480
    A(f'<rect x="{cbx}" y="{ytop}" width="{cbw}" height="13" fill="url(#gDoy)" '
      'stroke="var(--rule)"></rect>')
    for doy, lab in ((91, "4/1"), (121, "5/1"), (152, "6/1"), (182, "7/1")):
        X = cbx + cbw * (doy - DOY_MIN) / (DOY_MAX - DOY_MIN)
        A(f'<line x1="{X:.1f}" y1="{ytop+13}" x2="{X:.1f}" y2="{ytop+18}" stroke="currentColor" '
          'opacity=".5"></line>')
        A(f'<text class="s-xs s-num" x="{X:.1f}" y="{ytop+30}" text-anchor="middle">{lab}</text>')
    A(f'<text class="s-xs" x="{cbx}" y="{ytop-6}">雪が消えた日（早い ← → 遅い）</text>')
    A(f'<rect x="{cbx+cbw+26}" y="{ytop}" width="16" height="13" '
      f'fill="rgb({MISSING[0]},{MISSING[1]},{MISSING[2]})" stroke="var(--rule)"></rect>')
    A(f'<text class="s-xs" x="{cbx+cbw+48}" y="{ytop+11}">灰＝その年は雲などで決められなかった画素</text>')
    A(f'<rect x="{cbx+cbw+26}" y="{ytop+26}" width="16" height="13" '
      f'fill="rgb({OUTSIDE[0]},{OUTSIDE[1]},{OUTSIDE[2]})" stroke="var(--rule)"></rect>')
    A(f'<text class="s-xs" x="{cbx+cbw+48}" y="{ytop+37}">'
      '白＝火口から3 kmの外（集計に入れていない）</text>')

    # 9年分の中央値
    sy = ytop + 78
    A(f'<text class="s-hd" x="22" y="{sy-14}">9年分の画素中央値（同じ場所・同じ計算）</text>')
    gx0, gx1 = 100, 800
    dmin, dmax = 95, 155
    A(f'<line x1="{gx0}" y1="{sy+64}" x2="{gx1}" y2="{sy+64}" stroke="currentColor" '
      'opacity=".35"></line>')
    ks = sorted(years)
    for i, y in enumerate(ks):
        X = gx0 + (gx1 - gx0) * i / (len(ks) - 1)
        v = circ[y]["画素中央値"]
        Y = sy + 56 - 48 * (v - dmin) / (dmax - dmin)
        acc = y in show
        # 年を選んだときに、その年の点だけを囲む輪（JSが display を切り替える）
        A(f'<g id="snowRing{y}" style="display:none">'
          f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="10" fill="none" stroke="var(--accent)" '
          'stroke-width="2.5"></circle>'
          f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="5" fill="var(--accent)"></circle></g>')
        A(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="{4.5 if acc else 3.2}" '
          f'fill="{"var(--accent)" if acc else "var(--rock)"}" '
          f'opacity="{1 if acc else .75}"></circle>')
        A(f'<text class="s-xs s-num" x="{X:.1f}" y="{Y-9:.1f}" text-anchor="middle" '
          f'fill="{"var(--accent-ink)" if acc else "var(--ink-3)"}">{v:g}</text>')
        A(f'<text class="s-xs s-num" x="{X:.1f}" y="{sy+80}" text-anchor="middle">{y}</text>')
    vals = [circ[y]["画素中央値"] for y in ks]
    A(f'<text class="s-sm s-acc s-num" x="{gx1}" y="{sy-14}" text-anchor="end" font-weight="600">'
      f'最も早い年と遅い年で {max(vals)-min(vals):g} 日ちがう'
      '<tspan class="s-xs" fill="var(--ink-3)" font-weight="400">（画素中央値）</tspan></text>')
    A("</svg>")
    print(f"  PNG 3枚（並置）＋9枚（拡大）の合計: {total/1024:.0f} KB（base64 で約 {total*4/3/1024:.0f} KB）")
    return "\n".join(o)


if __name__ == "__main__":
    for name, fn in (("fig_t1_landsat.svg", fig_t1), ("fig_t1_image.svg", fig_t1_image),
                     ("fig_t2_snowmap.svg", fig_t2)):
        s = fn()
        p = os.path.join(OUT, name)
        open(p, "w").write(s)
        print(f"{p}  {len(s)/1024:.0f} KB")
