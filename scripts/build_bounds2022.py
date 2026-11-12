"""Build the platform's boundary and population files from LISGIS 2022 boundaries and the 2022 census.

Usage: python3 scripts/build_bounds2022.py SRC_DIR   (from the repository root)
SRC_DIR holds LISGIS geo-counties-2022.geojson, geo-districts-2022.geojson and geo-clans-2022.geojson.
Writes docs/data/counties.json, districts.json, clans.json (simplified for the web, lon/lat, wound for d3)
and docs/data/district_pop.json (2022 census by district, from scripts/data/census2022_districts.csv).
Clan population is placed later by build_flood.py / build_pop2022.py from WorldPop, scaled to district totals."""
import csv, json, pathlib, re, sys, glob
from shapely.geometry import shape, mapping
from shapely.geometry.polygon import orient
from shapely.ops import transform
import warnings; warnings.filterwarnings('ignore', category=DeprecationWarning)
import pyproj

root = pathlib.Path(__file__).resolve().parent.parent
src = pathlib.Path(sys.argv[1])
def find(pat):
    m = sorted(glob.glob(str(src / f"*{pat}*.geojson")))
    m = [x for x in m if "simplified" not in x] or m
    return json.load(open(m[0], encoding="utf-8"))["features"]
C, D, K = find("counties-2022"), find("districts-2022"), find("clans-2022")

to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32629", always_xy=True).transform
def km2(g): return round(transform(to_m, g).area / 1e6, 1)
def web(g, tol):
    g = g.buffer(0).simplify(tol, preserve_topology=True)
    if g.geom_type == "Polygon": g = orient(g, sign=-1.0)
    else:
        from shapely.geometry import MultiPolygon
        g = MultiPolygon([orient(p, sign=-1.0) for p in g.geoms])
    m = mapping(g)
    def rnd(c): return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 4), round(c[1], 4)]
    return {"type": m["type"], "coordinates": rnd(m["coordinates"])}

def title(s):
    s = re.sub(r"\s+", " ", s.strip())
    return re.sub(r"(^|[\s\-/(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)

cname = {f["properties"]["code"]: f["properties"]["name"] for f in C}

# 2022 census district figures, matched to boundary names.
census, totals = {}, {}
for r in csv.DictReader(open(root / "scripts" / "data" / "census2022_districts.csv", encoding="utf-8")):
    if r["district_2022"] == "COUNTY TOTAL": totals[r["county"]] = int(r["pop2022"])
    else: census.setdefault(r["county"], {})[r["district_2022"]] = int(r["pop2022"])
def norm(s):
    s = s.lower().replace("number", "no").replace("township", "").replace("tship", "").replace(" city", "").replace(" rs", "")
    s = s.replace("boundi", "gboni")
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", s))

dfeat, dpop, report = [], [], []
dname = {}
used = set()
for f in D:
    p = f["properties"]; cty = cname[p["parent_code"]]
    table = census.get(cty, {}); byn = {norm(k): k for k in table}
    k = byn.get(norm(p["name"]))
    if k: used.add((cty, k))
    name = k if k else title(p["name"])
    name = name.replace("Pleebo/ Sodoken", "Pleebo/Sodoken").replace("New georgia", "New Georgia")
    dname[p["code"]] = (cty, name)
    g = shape(f["geometry"])
    dpop.append({"code": p["code"], "county": cty, "district": name, "area_km2": km2(g),
                 "pop2022": table.get(k) if k else None, "pop2022_method": "2022 census" if k else None})
    dfeat.append({"type": "Feature", "properties": {"code": p["code"], "county": cty, "district": name, "area_km2": km2(g)}, "geometry": web(g, 0.0012)})
# Districts the census table does not list share the county's unlisted people (Sinoe: 17,478).
for cty in sorted(totals):
    rows = [r for r in dpop if r["county"] == cty]
    miss = [r for r in rows if r["pop2022"] is None]
    listed = sum(r["pop2022"] for r in rows if r["pop2022"] is not None)
    rest = totals[cty] - listed
    if miss:
        a = sum(r["area_km2"] for r in miss)
        for r in miss: r["pop2022"] = rest * r["area_km2"] / a; r["pop2022_method"] = "2022 census, estimated (district not listed in the census table)"
        report.append(f"{cty}: {len(miss)} districts not in the census table share {rest:,}: {', '.join(r['district'] for r in miss)}")
    elif rest: report.append(f"{cty}: table differs from county total by {rest:,}")
    unused = {k for k in census.get(cty, {}) if (cty, k) not in used} - {"(not listed)"}
    if unused: report.append(f"{cty}: census entries with no boundary: {sorted(unused)}")

cfeat = [{"type": "Feature", "properties": {"county": f["properties"]["name"], "code": f["properties"]["code"]}, "geometry": web(shape(f["geometry"]), 0.002)} for f in C]
kfeat = []
for f in K:
    p = f["properties"]; cty, dist = dname[p["parent_code"]]
    g = shape(f["geometry"])
    kfeat.append({"type": "Feature", "properties": {"clan_id": p["code"], "clan": title(p["name"]), "district": dist, "county": cty, "area_km2": km2(g)}, "geometry": web(g, 0.0008)})

out = root / "docs" / "data"
for n, fs in [("counties", cfeat), ("districts", dfeat), ("clans", kfeat)]:
    (out / f"{n}.json").write_text(json.dumps({"type": "FeatureCollection", "features": fs}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(out / "district_pop.json").write_text(json.dumps(dpop, ensure_ascii=False, indent=0), encoding="utf-8")
print("\n".join(report)); print(len(cfeat), "counties,", len(dfeat), "districts,", len(kfeat), "clans; population", round(sum(r["pop2022"] for r in dpop)))
