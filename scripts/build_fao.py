"""Build FAO ASIS drought files for the Liberia El Nino platform.
Usage: python3 -I build_fao.py OUTDIR
Writes fao_county.json, fao_rain.json, fao_asi_annual.json, county_watch.json."""
import sys, io, csv, json, urllib.request, collections, datetime
OUT = sys.argv[1]
B = "https://www.fao.org/giews/earthobservation/asis/data/country/LBR/"
def rows(path):
    req = urllib.request.Request(B + path, headers={"User-Agent": "Mozilla/5.0 (Liberia EPA El Nino platform)"})
    with urllib.request.urlopen(req, timeout=180) as r: txt = r.read().decode("utf-8", "ignore")
    seen = set(); out = []
    for x in csv.DictReader(io.StringIO(txt)):
        x = {k.strip(): (v or "").strip() for k, v in x.items() if k}
        key = tuple(x.items())
        if key in seen: continue
        seen.add(key); out.append(x)
    return out
num = lambda v: None if v in ("", None) else float(v)
asi = rows("MAP_ASI/DATA/ASI_Dekad_Season1_data.csv")
vhi = rows("MAP_NDVI_ANOMALY/DATA/vhi_adm1_dekad_data.csv")
rain = rows("GRAPH_RAIN_AGRI/rain_adm1_data.csv")
ann = rows("MAP_ASI/DATA/ASI_AnnualSummary_Season1_data.csv")
def latest(rs, field="Data"):
    by = {}
    for r in rs:
        p = r["Province"]
        if p not in by or r["Date"] > by[p]["Date"]: by[p] = r
    return by
la, lv = latest(asi), latest(vhi)
year = max(r["Date"] for r in rain)[:4]
rain_y = [r for r in rain if r["Date"].startswith(year)]
last_date = max(r["Date"] for r in rain_y)
dates = sorted(set(r["Date"] for r in rain_y))
last3 = dates[-3:]
season_start = f"{year}-03-01"
def pct(a, b): return None if not b else round(100 * a / b)
county = []
for p in sorted(la):
    rr = [r for r in rain_y if r["Province"] == p]
    s = sum(num(r["Data"]) for r in rr if r["Date"] >= season_start); sl = sum(num(r["Data_long_term_Average"]) for r in rr if r["Date"] >= season_start)
    t = sum(num(r["Data"]) for r in rr if r["Date"] in last3); tl = sum(num(r["Data_long_term_Average"]) for r in rr if r["Date"] in last3)
    a = num(la[p]["Data"])
    level = "Warning" if a >= 25 else "Watch" if a >= 10 else "Low"
    county.append({"county": p, "asi_date": la[p]["Date"], "asi_pct": round(a, 1), "level": level,
                   "vhi": num(lv[p]["Data"]) if p in lv else None, "vhi_date": lv[p]["Date"] if p in lv else None,
                   "rain_season_mm": round(s), "rain_season_normal_mm": round(sl), "rain_season_pct": pct(s, sl),
                   "rain_30d_mm": round(t), "rain_30d_normal_mm": round(tl), "rain_30d_pct": pct(t, tl), "rain_to": last_date})
rain_rows = [{"county": r["Province"], "date": r["Date"], "rain_mm": round(num(r["Data"]), 1), "normal_mm": round(num(r["Data_long_term_Average"]), 1)}
             for r in sorted(rain_y, key=lambda r: (r["Province"], r["Date"]))]
ann_rows = [{"county": r["PROVINCE"], "year": int(r["YEAR"]), "asi_pct": round(num(r["DATA"]), 1)} for r in ann if r["PROVINCE"] and r["DATA"]]
ann_rows.sort(key=lambda r: (r["county"], r["year"]))
FLOOD_WATCH = {"Grand Cape Mount", "Bomi", "Montserrado", "Gbarpolu"}
watch = []
for c in county:
    p = c["county"]
    watch.append({"county": p, "dryness": c["level"],
      "dryness_basis": f"FAO Agricultural Stress Index: {c['asi_pct']:g}% of cropland under drought stress (10 days to {c['asi_date']}). Warning at 25% or more, Watch at 10–25%. Season rainfall since 1 Mar: {c['rain_season_pct']}% of normal.",
      "flood": "Watch" if p in FLOOD_WATCH else "Low",
      "flood_basis": ("Heavy rain forecast for parts of western Liberia (NOAA/FEWS NET, 29 Oct–4 Nov) and AGRHYMET's coastal excess-rain signal." if p in FLOOD_WATCH else "No heavy-rain signal in current bulletins."),
      "heat": "Watch", "heat_basis": "Warmer-than-normal temperatures forecast across West Africa (AGRHYMET Aug–Oct update).",
      "confidence": "Dryness high (FAO index); flood and heat low"})
json.dump(county, open(f"{OUT}/fao_county.json", "w"), ensure_ascii=False)
json.dump(rain_rows, open(f"{OUT}/fao_rain.json", "w"), ensure_ascii=False)
json.dump(ann_rows, open(f"{OUT}/fao_asi_annual.json", "w"), ensure_ascii=False)
json.dump(watch, open(f"{OUT}/county_watch.json", "w"), ensure_ascii=False)
print("asi", max(c["asi_date"] for c in county), "rain", last_date, "counties", len(county), "rain rows", len(rain_rows), "annual", len(ann_rows))
