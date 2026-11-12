"""Build NOAA CPC El Nino files for the Liberia El Nino platform.
Usage: python3 -I build_noaa.py OUTDIR
Writes roni.json, nino_regions.json, nino_monthly.json, outlook.json, enso_status.json."""
import sys, re, html, json, datetime, urllib.request, hashlib
OUT = sys.argv[1]
B = "https://www.cpc.ncep.noaa.gov/"
def get(p):
    req = urllib.request.Request(B + p, headers={"User-Agent": "Mozilla/5.0 (Liberia EPA El Nino platform)"})
    with urllib.request.urlopen(req, timeout=120) as r: return r.read().decode("utf-8", "ignore")
SEAS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
# RONI table
roni_rows = []
cur_year = None
for line in get("data/indices/RONI.ascii.txt").splitlines():
    p = line.split()
    if len(p) == 3 and p[0] in SEAS:
        try: y, v = int(p[1]), float(p[2])
        except ValueError: continue
        roni_rows.append((p[0], y, v))
cur_year = max(y for _, y, _ in roni_rows)
roni = [{"year": str(y), "season": s, "order": SEAS.index(s) + 1, "roni_c": round(v, 2)} for s, y, v in roni_rows if y in (1997, 2015, 2023, cur_year)]
# weekly conventional Nino regions (1991-2020)
wk = [l for l in get("data/indices/wksst9120.for").splitlines() if re.match(r"^\s*\d{2}[A-Z]{3}\d{4}", l)]
last = wk[-1].split()
d = datetime.datetime.strptime(last[0], "%d%b%Y").date().isoformat()
an = [float(last[i]) for i in (2, 4, 6, 8)]
regions = [{"region": "Niño 1+2", "area": "Far eastern Pacific, off Peru", "anomaly_c": an[0], "week": d},
           {"region": "Niño 3", "area": "Eastern Pacific", "anomaly_c": an[1], "week": d},
           {"region": "Niño 3.4", "area": "Central-east Pacific (main index)", "anomaly_c": an[2], "week": d},
           {"region": "Niño 4", "area": "Central-west Pacific", "anomaly_c": an[3], "week": d}]
# monthly conventional anomalies (OISST, 1991-2020)
mon = []
for l in get("data/indices/sstoi.indices").splitlines()[1:]:
    p = l.split()
    if len(p) == 10 and int(p[0]) == cur_year:
        m = f"{p[0]}-{int(p[1]):02d}"
        mon += [{"month": m, "region": "Niño 1+2", "anomaly_c": float(p[3])}, {"month": m, "region": "Niño 3", "anomaly_c": float(p[5])},
                {"month": m, "region": "Niño 3.4", "anomaly_c": float(p[9])}, {"month": m, "region": "Niño 4", "anomaly_c": float(p[7])}]
# outlook tables
def table(p):
    t = get(p); rows = []
    issued = re.search(r"Issued\s+(?:<[^>]+>\s*)*([A-Z][a-z]+ \d{4})", re.sub(r"<!--.*?-->", "", t, flags=re.S))
    for tr in re.findall(r"<tr.*?</tr>", t, flags=re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S)]
        if cells and re.match(r"^[A-Z]{3} [A-Z][a-z]{2} [A-Z][a-z]{2} [A-Z][a-z]{2}$", cells[0]): rows.append(cells)
    return rows, issued.group(1) if issued else ""
probs, issued = table("products/analysis_monitoring/enso/roni/probabilities/")
strs, _ = table("products/analysis_monitoring/enso/roni/strengths/")
sd = {r[0][:3]: r for r in strs}
outlook = []
for i, r in enumerate(probs):
    code = r[0][:3]; m = r[0].split()[1:]
    s = sd.get(code)
    outlook.append({"season": code, "label": f"{m[0]}–{m[2]}", "order": i + 1, "issued": issued,
                    "lanina_pct": int(r[1]), "neutral_pct": int(r[2]), "elnino_pct": int(r[3]),
                    "strong_pct": int(s[8]) if s else None, "very_strong_pct": int(s[9]) if s else None})
# discussion status
t = get("products/analysis_monitoring/enso_advisory/ensodisc.shtml")
txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S))))
dd = re.search(r"CLIMATE PREDICTION CENTER/NCEP/NWS (?:and the IRI )?(\d{1,2} [A-Z][a-z]+ \d{4})", txt)
al = re.search(r"ENSO Alert System Status: (.*?) Synopsis:", txt)
sy = re.search(r"Synopsis: (.*?\.)\s", txt)
nx = re.search(r"next ENSO Diagnostics Discussion is scheduled for (\d{1,2} [A-Z][a-z]+(?: \d{4})?)", txt)
iso = lambda s: datetime.datetime.strptime(s, "%d %B %Y").date().isoformat() if s and re.search(r"\d{4}$", s) else None
status = [{"discussion_date": iso(dd.group(1)) if dd else None, "alert": al.group(1).strip() if al else None,
           "synopsis": sy.group(1).strip() if sy else None,
           "next_date": iso(nx.group(1) if re.search(r"\d{4}$", nx.group(1)) else nx.group(1) + " " + (dd.group(1)[-4:] if dd else "")) if nx else None,
           "outlook_issued": issued, "roni_latest_season": f"{roni_rows[-1][0]} {roni_rows[-1][1]}", "weekly_week": d}]
for name, obj in [("roni", roni), ("nino_regions", regions), ("nino_monthly", mon), ("outlook", outlook), ("enso_status", status)]:
    json.dump(obj, open(f"{OUT}/{name}.json", "w"), ensure_ascii=False)
fp = {n: hashlib.sha256(open(f"{OUT}/{n}.json", "rb").read()).hexdigest()[:12] for n in ["roni", "nino_regions", "nino_monthly", "outlook", "enso_status"]}
print("fingerprints", json.dumps(fp))
print("discussion", status[0]["discussion_date"], "outlook", issued, "roni", status[0]["roni_latest_season"], roni_rows[-1][2], "week", d, "months", len(mon) // 4)
