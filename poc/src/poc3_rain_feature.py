"""PoC-3: 「降雨後温度回復」特徴量の成立確率計算（京浜地区）
モードA(実データ): Open-Meteo時別CSV（ユーザーアップロード）があれば実気象で計算
モードB(気候値パラメトリック): 横浜の月別気候値レンジ+感度分析によるモンテカルロ

成立条件の定義:
  ベースライン: 降雨イベント前7日以内に晴天夜間撮像>=1
  単点特徴量:   降雨終了後96h以内に晴天夜間撮像>=1
  回復速度(傾き): 同96h以内に晴天夜間撮像>=2（12h以上間隔）
衛星: 太陽同期軌道の夜側パスが interval 日おき（タスキング成功率も考慮）
"""
import numpy as np, json, os, glob, csv

rng = np.random.default_rng(7)
_POC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_POC, "out")

# ---------- モード判定 ----------
cand = (glob.glob(os.path.join(_POC, "data", "*.csv")) +
        glob.glob("/root/.claude/uploads/**/*.csv", recursive=True) +
        glob.glob("/home/claude/poc/data/*.csv"))
REAL = None
for p in cand:
    try:
        head = open(p, encoding="utf-8", errors="ignore").read(400)
        if "precipitation" in head and ("cloud" in head or "cloudcover" in head):
            REAL = p; break
    except Exception:
        pass

# ---------- 気候値（モードB用）: 横浜の月別 近似値レンジ ----------
# 降水日数(>=1mm)/月 と 月平均雲量(0-10)。気候値の近似であり、実データ到着後に置換する。
RAIN_DAYS = {1: 5.5, 2: 6.5, 3: 10, 4: 10.5, 5: 11, 6: 13, 7: 11, 8: 8.5, 9: 11.5, 10: 11, 11: 8, 12: 5.5}
CLOUD_10 = {1: 4.5, 2: 5.5, 3: 6.5, 4: 7.0, 5: 7.5, 6: 8.5, 7: 8.0, 8: 7.0, 9: 8.0, 10: 7.0, 11: 6.0, 12: 4.5}
EVENT_MEAN_DUR = 1.4     # 降雨イベント平均継続日数
POST_RAIN_CLEAR_FACTOR = [0.6, 0.9, 1.1, 1.1]  # 降雨後0-24/24-48/48-72/72-96hの晴天率補正(前線通過後の晴れ上がり)

def p_clear_night(month, factor=1.0):
    """雲量から夜間晴天(雲量<3割)確率への粗い写像 + 補正"""
    c = CLOUD_10[month]/10
    base = max(0.03, (1-c)**1.5)   # 雲量7→0.16, 雲量4.5→0.41
    return min(0.95, base*factor)

def simulate_year(interval_days, tasking_p=0.85, mode_params=None):
    """1年分を日単位でシミュレート。返り値: (単点成立数, 傾き成立数, ベースライン欠落数, イベント総数)"""
    # 降雨イベント系列の生成
    events = []
    for m in range(1, 13):
        n_ev = rng.poisson(RAIN_DAYS[m]/EVENT_MEAN_DUR)
        days_in_m = 30
        for _ in range(n_ev):
            d0 = (m-1)*30 + rng.integers(0, days_in_m)
            events.append((d0, d0 + max(0, rng.poisson(EVENT_MEAN_DUR-1))))  # (開始日, 終了日)
    events.sort()
    # 夜側パス日: interval日おき + タスキング成功
    phase = rng.uniform(0, interval_days)
    pass_days = set()
    d = phase
    while d < 365:
        if rng.random() < tasking_p: pass_days.add(int(d))
        d += interval_days
    single, slope, no_base = 0, 0, 0
    for (s, e) in events:
        m = min(12, max(1, int(s/30)+1))
        # ベースライン: 前7日
        base_ok = any((s-7 <= pd < s) and (rng.random() < p_clear_night(m)) for pd in pass_days)
        # 降雨後96h(4日)
        post = []
        for pd in pass_days:
            if e < pd <= e+4:
                slot = min(3, int(pd-e-0.001))
                if rng.random() < p_clear_night(m, POST_RAIN_CLEAR_FACTOR[slot]):
                    post.append(pd)
        if not base_ok:
            no_base += 1; continue
        if len(post) >= 1: single += 1
        if len(post) >= 2: slope += 1
    return single, slope, no_base, len(events)

def run_mc(n_years=300):
    scen = {}
    for label, interval in [("現行1機(2日おき夜側パス)", 2.0), ("現行1機(3日おき・競合考慮)", 3.0),
                            ("3機化(0.67日)", 0.67), ("9機化(0.22日)", 0.22)]:
        res = np.array([simulate_year(interval) for _ in range(n_years)], float)
        scen[label] = dict(
            single_per_year=dict(median=float(np.median(res[:, 0])), p25=float(np.percentile(res[:, 0], 25)), p75=float(np.percentile(res[:, 0], 75))),
            slope_per_year=dict(median=float(np.median(res[:, 1])), p25=float(np.percentile(res[:, 1], 25)), p75=float(np.percentile(res[:, 1], 75))),
            events_per_year=float(np.median(res[:, 3])))
    return scen

def sensitivity(n_years=200):
    """主要パラメータを振って傾き成立数/年の変動幅を見る"""
    global EVENT_MEAN_DUR, POST_RAIN_CLEAR_FACTOR
    out = {}
    base = np.median([simulate_year(2.0)[1] for _ in range(n_years)])
    out["基準(1機,2日)"] = float(base)
    keep = POST_RAIN_CLEAR_FACTOR[:]
    POST_RAIN_CLEAR_FACTOR = [f*0.7 for f in keep]   # 降雨後も曇りがち(悲観)
    out["降雨後晴天率-30%"] = float(np.median([simulate_year(2.0)[1] for _ in range(n_years)]))
    POST_RAIN_CLEAR_FACTOR = [min(1.3, f*1.3) for f in keep]  # 晴れ上がり強め(楽観)
    out["降雨後晴天率+30%"] = float(np.median([simulate_year(2.0)[1] for _ in range(n_years)]))
    POST_RAIN_CLEAR_FACTOR = keep
    out["タスキング成功率0.6"] = float(np.median([simulate_year(2.0, tasking_p=0.6)[1] for _ in range(n_years)]))
    return out

results = {"mode": "B: 気候値パラメトリック（実データ到着後に置換可能）" if not REAL else f"A: 実データ {REAL}"}

if REAL:
    # ---- モードA: Open-Meteo時別CSV ----
    import datetime as dt
    rows = []
    with open(REAL, encoding="utf-8", errors="ignore") as f:
        txt = f.read().splitlines()
    hdr_i = next(i for i, l in enumerate(txt) if l.startswith("time"))
    cols = txt[hdr_i].split(",")
    ip = next(i for i, c in enumerate(cols) if "precipitation" in c)
    ic = next(i for i, c in enumerate(cols) if "cloud" in c)
    data = []
    for l in txt[hdr_i+1:]:
        p = l.split(",")
        if len(p) < max(ip, ic)+1 or not p[0]: continue
        try:
            data.append((dt.datetime.fromisoformat(p[0]), float(p[ip] or 0), float(p[ic] or 100)))
        except ValueError: continue
    # 降雨イベント抽出（日単位: 日降水>=1mm の連続区間）
    # 晴天夜判定: 衛星パスは一晩1回・固定時刻なので「パス時刻の雲量<30%」で判定する
    # （夜間ウィンドウ内の最小雲量を使うと成立回数を過大評価する）
    PASS_HOUR = 22  # SSO夜側パス想定時刻（HotSat級のLTAN 22時台を仮定）
    import collections
    daily_p = collections.defaultdict(float); night_clear = {}; night_clear_minwin = {}
    for t, pr, cl in data:
        daily_p[t.date()] += pr
        if t.hour == PASS_HOUR:
            night_clear[t.date()] = cl
        if t.hour in (22, 23, 0, 1, 2):   # 参考: ウィンドウ最小雲量（楽観上限）
            d = t.date() if t.hour >= 22 else (t - dt.timedelta(days=1)).date()
            night_clear_minwin[d] = min(night_clear_minwin.get(d, 100), cl)
    days = sorted(daily_p)
    rain = [d for d in days if daily_p[d] >= 1.0]
    events, cur = [], []
    for d in rain:
        if cur and (d - cur[-1]).days == 1: cur.append(d)
        else:
            if cur: events.append((cur[0], cur[-1]))
            cur = [d]
    if cur: events.append((cur[0], cur[-1]))
    def mc_real(interval, n_iter=200, tasking_p=0.85, clear_map=None):
        clear_map = night_clear if clear_map is None else clear_map
        singles, slopes = [], []
        day_index = {d: i for i, d in enumerate(days)}
        for it in range(n_iter):
            phase = rng.uniform(0, interval)
            pass_set = set()
            x = phase
            while x < len(days):
                if rng.random() < tasking_p: pass_set.add(int(x))
                x += interval
            s1 = s2 = 0
            for (a, b) in events:
                ia, ib = day_index[a], day_index[b]
                base = any((ia-7 <= i < ia) and i in pass_set and clear_map.get(days[i], 100) < 30 for i in range(max(0, ia-7), ia))
                post = [i for i in range(ib+1, min(len(days), ib+5)) if i in pass_set and clear_map.get(days[i], 100) < 30]
                if base and len(post) >= 1: s1 += 1
                if base and len(post) >= 2: s2 += 1
            n_years_data = len(days)/365.25
            singles.append(s1/n_years_data); slopes.append(s2/n_years_data)
        def q(a):
            return dict(median=float(np.median(a)), p25=float(np.percentile(a, 25)),
                        p75=float(np.percentile(a, 75)))
        return dict(single_per_year=q(singles), slope_per_year=q(slopes))
    results["events_per_year"] = len(events)/(len(days)/365.25)
    results["pass_hour_jst"] = PASS_HOUR
    results["scenarios"] = {lab: mc_real(iv) for lab, iv in
                            [("現行1機(2日)", 2.0), ("現行1機(3日)", 3.0), ("3機化", 0.67), ("9機化", 0.22)]}
    # 感度: パス時刻を深夜1時に / タスキング成功率0.6 / 楽観上限(夜間ウィンドウ最小雲量)
    nc_h1 = {}
    for t, pr, cl in data:
        if t.hour == 1:
            nc_h1[(t - dt.timedelta(days=1)).date()] = cl
    results["sensitivity_1sat_2day"] = {
        "パス時刻22時(基準)": results["scenarios"]["現行1機(2日)"],
        "パス時刻1時": mc_real(2.0, clear_map=nc_h1),
        "タスキング成功率0.6": mc_real(2.0, tasking_p=0.6),
        "楽観上限(夜間5hのどこかで晴れ)": mc_real(2.0, clear_map=night_clear_minwin),
    }
else:
    results["scenarios"] = run_mc()
    results["sensitivity_slope_per_year"] = sensitivity()

os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/poc3_results.json", "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print(json.dumps(results, ensure_ascii=False, indent=1))
