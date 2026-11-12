"""Put 2022 census population (LISGIS 2022 Liberia Population and Housing Census, final results, Appendix B)
onto the 2007 LISGIS district and clan boundaries the maps use, and rescale the flood-zone counts to it.

Inputs:  scripts/data/census2022_districts.csv   (district totals as printed, with the corrections noted in it)
         docs/data/district_pop.json              (2007 districts with 2008 census and 2014 projection)
         scripts/data/flood_areas_worldpop2025.json (output of build_flood.py: WorldPop 2025 people per area)
Outputs: docs/data/district_pop.json  (adds pop2022 and pop2022_method)
         docs/data/flood_areas.json   (population and flood-zone people on a 2022-census basis)

Method. County totals are the census figures exactly. The 2022 census lists 172 districts against 136 on the
2007 map: many new districts were carved out of old ones, and the report does not say which. So, within each
county: a 2007 district whose name appears in the 2022 tables gets that 2022 figure; the people in 2022
districts with no 2007 match (new districts, plus any shortfall in a table) are shared out among the county's
2007 districts in proportion to the people WorldPop places there beyond their matched figure. Counties whose
districts did not change get the census figures exactly. Clans and flood-zone counts follow their district's
2022 total, keeping WorldPop's pattern within the district.
Usage: python3 scripts/build_pop2022.py   (from the repository root)"""
import csv, json, pathlib, re
root = pathlib.Path(__file__).resolve().parent.parent
D = root / "docs" / "data"

def norm(s):
    s = s.lower().replace("number", "#").replace("dist#", "#").replace("dist #", "#")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z0-9#]", "", s)
    return s
ALIAS = {  # 2007 map name -> 2022 table name, where only the spelling differs
    ("Grand Bassa", "Commonwealth2"): "Commonwealth",
    ("Montserrado", "Commonwealth1"): None,
    ("Margibi", "Mambah Kaba"): "Mambahn Kabah",
    ("Sinoe", "Kulu Shaw Boe"): "Kulu",
    ("Sinoe", "Plahn Nyarn"): "Plahn",
}

census, totals, notes = {}, {}, {}
for r in csv.DictReader(open(root / "scripts" / "data" / "census2022_districts.csv", encoding="utf-8")):
    if r["district_2022"] == "COUNTY TOTAL": totals[r["county"]] = int(r["pop2022"])
    else: census.setdefault(r["county"], {})[r["district_2022"]] = int(r["pop2022"])
for c, ds in census.items():
    assert sum(ds.values()) == totals[c], (c, sum(ds.values()), totals[c])

dp = json.loads((D / "district_pop.json").read_text(encoding="utf-8"))
wp = json.loads((root / "scripts" / "data" / "flood_areas_worldpop2025.json").read_text(encoding="utf-8"))
wpd = {(r["county"], r["district"]): r["pop2025"] for r in wp if r["level"] == "district"}

report = []
for c in sorted(totals):
    olds = [r for r in dp if r["county"] == c]
    table = dict(census[c])
    byn = {norm(k): k for k in table}
    matched = {}
    for r in olds:
        key = (c, r["district"])
        name = ALIAS.get(key, r["district"]) if key in ALIAS else r["district"]
        if name is None: continue
        k = byn.get(norm(name))
        if k is not None and k in table: matched[r["district"]] = table.pop(k)
    pool = sum(table.values())
    wtot = sum(wpd[(c, r["district"])] for r in olds)
    resid = {r["district"]: max(0.0, wpd[(c, r["district"])] / wtot * totals[c] - matched.get(r["district"], 0)) for r in olds}
    rs = sum(resid.values()) or 1.0
    for r in olds:
        m = matched.get(r["district"])
        add = pool * resid[r["district"]] / rs if pool else 0
        r["pop2022"] = int(round((m or 0) + add))
        r["pop2022_method"] = ("2022 census" if m is not None and add < 0.5 else
                               "2022 census, plus a share of new districts" if m is not None else
                               "2022 census, estimated (district renamed or split)")
    diff = totals[c] - sum(r["pop2022"] for r in olds)
    if diff:  # rounding: put it on the largest district that received a share, else the largest
        cand = [r for r in olds if r["pop2022_method"] != "2022 census"] or olds
        max(cand, key=lambda r: r["pop2022"])["pop2022"] += diff
    report.append(f"{c}: {len(matched)}/{len(olds)} matched, {len(table)} unmatched 2022 entries ({pool:,} people) shared out: {', '.join(table) or '-'}")
(D / "district_pop.json").write_text(json.dumps(dp, ensure_ascii=False, indent=0), encoding="utf-8")

# Flood-zone counts on the 2022 basis.
f22 = {(r["county"], r["district"]): r["pop2022"] / wpd[(r["county"], r["district"])] for r in dp}
out, cty = [], {}
POPF = ["pop2025"] + [f"rp{rp}_{k}" for rp in (10, 100, 500) for k in ("pop", "pop_1m")]
for r in wp:
    r = dict(r)
    if r["level"] == "county": continue
    k = f22[(r["county"], r["district"])]
    for f in POPF: r[f] = int(round(r[f] * k))
    out.append(r)
    if r["level"] == "district":
        a = cty.setdefault(r["county"], {f: 0 for f in POPF})
        for f in POPF: a[f] += r[f]
for r in wp:
    if r["level"] != "county": continue
    r = dict(r); r.update(cty[r["county"]]); out.append(r)
for r in out:
    r["pop2022"] = r.pop("pop2025")
    for rp in (10, 100, 500): r[f"rp{rp}_pop_pct"] = round(r[f"rp{rp}_pop"] / r["pop2022"] * 100, 1) if r["pop2022"] else 0.0
    r["flood_level"] = "Warning" if r["rp100_pop_pct"] >= 10 else "Watch" if r["rp100_pop_pct"] >= 3 else "Low"
out.sort(key=lambda r: ({"county": 0, "district": 1, "clan": 2}[r["level"]], r["key"]))
(D / "flood_areas.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("\n".join(report))
print("Liberia 2022:", sum(totals.values()), "· in 1-in-100-year zone:", sum(r["rp100_pop"] for r in out if r["level"] == "county"))
