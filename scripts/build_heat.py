"""Heat index for every Liberian district and county: the past 7 days and the next 7 days.
Usage: python3 scripts/build_heat.py docs/data   (from the repository root; needs internet)

Data: Open-Meteo forecast API (no key; CC BY 4.0), hourly 2 m temperature and relative humidity from the best
available weather models (ECMWF, GFS and others, about 10 km), at one point inside each of the 160 districts (LISGIS 2022).
Heat index: NOAA formula (Rothfusz regression with NOAA's adjustments), from each hour's temperature and humidity;
the daily figure is the day's highest hour (UTC, which is Liberia's time).

Normal for each place: the 90th percentile of the daily maximum heat index in the same calendar month, 2011-2025,
from ERA5 reanalysis (Open-Meteo historical API), at the same district point. Worked out once per month and kept in
heat_baseline.json. The normal is then shifted by the average difference between the forecast models and ERA5 in the
same month of 2023-2025 (Open-Meteo historical forecast API), so a model that runs warmer than ERA5 does not show as
unusual heat. Liberia is humid, so a heat index of 38-40 °C is ordinary on the coast in the dry season: the
levels therefore ask for heat that is both unusual for the place and dangerous.

Levels (provisional, for agreement with LiMet and the Ministry of Health):
  district  Warning: on at least 2 of the next 7 days the heat index is above the place's 90th percentile AND at or
                     above 41 °C ("Danger" in NOAA's scale)
            Watch:   on at least 2 of the next 7 days it is above the place's 90th percentile, or on any day 41 °C or more
            Low:     otherwise
  county    Warning when at least 25% of its residents live in districts at Warning; Watch when at least 25% live in
            districts at Watch or Warning; otherwise Low. Residents: 2022 census (district_pop.json).
Writes heat_areas.json (one row per county and district) and heat_daily.json (each district's daily maximum, 14 days)."""
import sys, json, math, time, pathlib, datetime, urllib.request, urllib.parse
from shapely.geometry import shape
from shapely.ops import polylabel

OUT = pathlib.Path(sys.argv[1])
UA = {"User-Agent": "EPA Liberia El Nino Early Warning Platform (github.com/epa-liberia/liberia-climate-early-warning)"}
DANGER, DAYS, BASE_YEARS = 41.0, 2, range(2011, 2026)

def heat_index_c(t_c, rh):
    """NOAA heat index (°C) from air temperature (°C) and relative humidity (%)."""
    if t_c is None or rh is None: return None
    T = t_c * 9 / 5 + 32
    hi = 0.5 * (T + 61.0 + (T - 68.0) * 1.2 + rh * 0.094)
    if (hi + T) / 2 >= 80:
        hi = (-42.379 + 2.04901523 * T + 10.14333127 * rh - 0.22475541 * T * rh - 6.83783e-3 * T * T
              - 5.481717e-2 * rh * rh + 1.22874e-3 * T * T * rh + 8.5282e-4 * T * rh * rh - 1.99e-6 * T * T * rh * rh)
        if rh < 13 and 80 <= T <= 112: hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(T - 95)) / 17)
        elif rh > 85 and 80 <= T <= 87: hi += ((rh - 85) / 10) * ((87 - T) / 5)
    return (hi - 32) * 5 / 9

def category(hi):
    if hi is None: return None
    return "Extreme danger" if hi >= 54 else "Danger" if hi >= 41 else "Extreme caution" if hi >= 32 else "Caution" if hi >= 27 else "No heat stress"

def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r: return json.loads(r.read())
        except Exception:
            if k == 3: raise
            time.sleep(5 * (k + 1))

dist = json.load(open(OUT / "districts.json", encoding="utf-8"))["features"]
pop = {(r["county"], r["district"]): r["pop2022"] for r in json.load(open(OUT / "district_pop.json", encoding="utf-8"))}
pts = []
for f in dist:
    g = shape(f["geometry"]); g = max(g.geoms, key=lambda x: x.area) if g.geom_type == "MultiPolygon" else g
    p = polylabel(g, tolerance=0.001); pr = f["properties"]
    pts.append({"county": pr["county"], "district": pr["district"], "lat": round(p.y, 4), "lon": round(p.x, 4)})

today = datetime.datetime.now(datetime.timezone.utc).date()
B = 40

def daily_max(h):
    out = {}
    for t, tc, rh in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"]):
        hi = heat_index_c(tc, rh)
        if hi is None: continue
        d = t[:10]; cur = out.get(d)
        if cur is None or hi > cur[0]: out[d] = (hi, tc, rh)
    return out

# Normal for each district and month (ERA5, 2011-2025), kept between runs.
bp = OUT / "heat_baseline.json"
base = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else {}
need = sorted({(today + datetime.timedelta(days=k)).month for k in range(8)})
for m in need:
    key_m = f"{m:02d}"
    if key_m in base and len(base[key_m]) >= 150: continue
    vals = {f"{p['county']}:{p['district']}": [] for p in pts}
    for y in BASE_YEARS:
        start = datetime.date(y, m, 1); end = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
        for i in range(0, len(pts), B):
            chunk = pts[i:i + B]
            q = urllib.parse.urlencode({"latitude": ",".join(str(p["lat"]) for p in chunk), "longitude": ",".join(str(p["lon"]) for p in chunk),
                                        "hourly": "temperature_2m,relative_humidity_2m", "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "GMT"})
            res = get("https://archive-api.open-meteo.com/v1/archive?" + q)
            if isinstance(res, dict): res = [res]
            for p, r in zip(chunk, res):
                vals[f"{p['county']}:{p['district']}"] += [v[0] for v in daily_max(r["hourly"]).values()]
            time.sleep(1)
    def pct(a, q):
        a = sorted(a); return round(a[min(len(a) - 1, int(q * (len(a) - 1) + 0.5))], 1) if a else None
    base[key_m] = {k: {"p50": pct(v, 0.5), "p90": pct(v, 0.9), "n": len(v)} for k, v in vals.items()}
    print("baseline month", key_m, "built from", len(BASE_YEARS), "years")
bp.write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# Model bias: today's forecast models and ERA5 differ (resolution, humidity). Open-Meteo keeps past forecasts
# (historical forecast API, from 2022), so for the same month of 2023-2025 we compare the forecast models with ERA5
# day by day at each district point, and shift each district's normal by the average difference. Kept per month.
for m in need:
    key_b = f"bias_{m:02d}"
    if key_b in base and len(base[key_b]) >= 150: continue
    diffs = {f"{p['county']}:{p['district']}": [] for p in pts}
    for y in (2023, 2024, 2025):
        start = datetime.date(y, m, 1); end = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
        for i in range(0, len(pts), B):
            chunk = pts[i:i + B]
            q = urllib.parse.urlencode({"latitude": ",".join(str(p["lat"]) for p in chunk), "longitude": ",".join(str(p["lon"]) for p in chunk),
                                        "hourly": "temperature_2m,relative_humidity_2m", "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "GMT"})
            fc = get("https://historical-forecast-api.open-meteo.com/v1/forecast?" + q); time.sleep(1)
            er = get("https://archive-api.open-meteo.com/v1/archive?" + q); time.sleep(1)
            if isinstance(fc, dict): fc = [fc]
            if isinstance(er, dict): er = [er]
            for p, f1, e1 in zip(chunk, fc, er):
                a1, b1 = daily_max(f1["hourly"]), daily_max(e1["hourly"])
                diffs[f"{p['county']}:{p['district']}"] += [a1[d][0] - b1[d][0] for d in a1 if d in b1]
    base[key_b] = {k: {"bias": round(sum(v) / len(v), 2) if v else 0.0, "n": len(v)} for k, v in diffs.items()}
    print("bias month", f"{m:02d}", "from 2023-2025")
bp.write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

daily, rows = [], []
for i in range(0, len(pts), B):
    chunk = pts[i:i + B]
    q = urllib.parse.urlencode({"latitude": ",".join(str(p["lat"]) for p in chunk), "longitude": ",".join(str(p["lon"]) for p in chunk),
                                "hourly": "temperature_2m,relative_humidity_2m", "past_days": 7, "forecast_days": 8, "timezone": "GMT"})
    res = get("https://api.open-meteo.com/v1/forecast?" + q)
    if isinstance(res, dict): res = [res]
    for p, r in zip(chunk, res):
        byday = daily_max(r["hourly"]); kd = f"{p['county']}:{p['district']}"
        def bias_for(d): return base.get("bias_" + d[5:7], {}).get(kd, {}).get("bias", 0.0)
        def p90(d): b = base.get(d[5:7], {}).get(kd); return round(b["p90"] + bias_for(d), 1) if b else None
        bias = round(bias_for(today.isoformat()), 1); nb = base.get("bias_" + today.strftime("%m"), {}).get(kd, {}).get("n", 0)
        past = [(d, v) for d, v in sorted(byday.items()) if d < today.isoformat()][-7:]
        fut = [(d, v) for d, v in sorted(byday.items()) if d >= today.isoformat()][:7]
        for d, (hi, tc, rh) in past + fut:
            daily.append({"county": p["county"], "district": p["district"], "date": d, "kind": "forecast" if d >= today.isoformat() else "past",
                          "hi_max": round(hi, 1), "temp_at_max": round(tc, 1), "rh_at_max": int(round(rh)), "normal_p90": p90(d)})
        fmax = max((v[0] for _, v in fut), default=None); pmax = max((v[0] for _, v in past), default=None)
        unusual = [d for d, v in fut if p90(d) is not None and v[0] > p90(d)]
        both = [d for d, v in fut if p90(d) is not None and v[0] > p90(d) and v[0] >= DANGER]
        n41 = sum(1 for _, v in fut if v[0] >= DANGER)
        level = "Warning" if len(both) >= DAYS else "Watch" if (len(unusual) >= DAYS or n41 >= 1) else "Low"
        b0 = base.get(today.strftime("%m"), {}).get(kd, {})
        peak = max(fut, key=lambda x: x[1][0]) if fut else None
        rows.append({"key": f"district:{p['county']}:{p['district']}", "level": "district", "county": p["county"], "district": p["district"],
                     "lat": p["lat"], "lon": p["lon"], "pop2022": pop.get((p["county"], p["district"])),
                     "hi_max_past7": round(pmax, 1) if pmax is not None else None, "hi_max_next7": round(fmax, 1) if fmax is not None else None,
                     "peak_date": peak[0] if peak else None, "normal_p90_month": round(b0["p90"] + bias, 1) if b0.get("p90") is not None else None,
                     "normal_p50_month": round(b0["p50"] + bias, 1) if b0.get("p50") is not None else None, "model_bias_c": bias, "bias_days": nb,
                     "days_unusual_next7": len(unusual), "days_ge41_next7": n41, "days_unusual_and_ge41_next7": len(both),
                     "category_next7": category(fmax), "heat_level": level})
    time.sleep(1)

for cty in sorted({r["county"] for r in rows}):
    ds = [r for r in rows if r["county"] == cty]; P = sum(r["pop2022"] or 0 for r in ds) or 1
    sh_w = sum(r["pop2022"] or 0 for r in ds if r["heat_level"] == "Warning") / P * 100
    sh_ww = sum(r["pop2022"] or 0 for r in ds if r["heat_level"] in ("Warning", "Watch")) / P * 100
    level = "Warning" if sh_w >= 25 else "Watch" if sh_ww >= 25 else "Low"
    fx = [r["hi_max_next7"] for r in ds if r["hi_max_next7"] is not None]; px = [r["hi_max_past7"] for r in ds if r["hi_max_past7"] is not None]
    top = max(ds, key=lambda r: r["hi_max_next7"] or -99)
    rows.append({"key": f"county:{cty}", "level": "county", "county": cty, "district": "", "pop2022": P,
                 "hi_max_past7": max(px) if px else None, "hi_max_next7": max(fx) if fx else None, "hottest_district": top["district"],
                 "peak_date": top["peak_date"], "pop_pct_warning": round(sh_w, 1), "pop_pct_watch_or_warning": round(sh_ww, 1),
                 "districts_warning": ", ".join(r["district"] for r in ds if r["heat_level"] == "Warning"),
                 "category_next7": category(max(fx) if fx else None), "heat_level": level})
issued = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
for r in rows: r["issued"] = issued
rows.sort(key=lambda r: (r["level"] != "county", r["key"]))
if len([r for r in rows if r["level"] == "district"]) < 150: sys.exit("too few districts returned; not saving")
(OUT / "heat_areas.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(OUT / "heat_daily.json").write_text(json.dumps(daily, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
mp = OUT / "manifest.json"; man = json.loads(mp.read_text(encoding="utf-8"))
for k, t, d in (("heat_baseline", "Normal heat index by district and month", "90th and 50th percentile of each district's daily maximum heat index in each calendar month, 2011-2025 (ERA5 reanalysis via Open-Meteo)."),
                ("heat_areas", "Heat index by county and district", "Highest heat index (temperature and humidity together) in the past 7 and next 7 days for every district, with provisional heat levels; counties by the share of residents in districts at each level. Open-Meteo weather models, NOAA heat index."),
                ("heat_daily", "Daily heat index by district", "Each district's highest hourly heat index for each of the past 7 and next 7 days (Open-Meteo weather models, NOAA heat index).")):
    man.setdefault(k, {"file": f"data/{k}.json", "title": t, "description": d, "updated": issued, "sha": ""})
mp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
cs = [r for r in rows if r["level"] == "county"]
print("heat", issued, "districts", len(rows) - len(cs), "| counties:", ", ".join(f"{r['county']} {r['heat_level']} {r['hi_max_next7']}" for r in cs))
