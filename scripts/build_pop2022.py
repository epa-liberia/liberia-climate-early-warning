"""Put flood-zone people on a 2022-census basis.

Inputs:  docs/data/district_pop.json                (2022 census by district, from build_bounds2022.py)
         scripts/data/flood_areas_worldpop2025.json  (output of build_flood.py: WorldPop 2025 people per area)
Output:  docs/data/flood_areas.json

The 2022 census gives people per district and per clan (the LISGIS 2022 maps match the census tables by name
and code). WorldPop says where within each area people live, which places them inside or outside the flood zone.
Clans use their own census count. Each district's WorldPop counts, including its clans and the
people inside flood zones, are scaled so the district total equals the census; counties are the sum of their
districts. Shares within a district do not change.
Usage: python3 scripts/build_pop2022.py   (from the repository root)"""
import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
D = root / "docs" / "data"
dp = json.loads((D / "district_pop.json").read_text(encoding="utf-8"))
wp = json.loads((root / "scripts" / "data" / "flood_areas_worldpop2025.json").read_text(encoding="utf-8"))
wpd = {(r["county"], r["district"]): r["pop2025"] for r in wp if r["level"] == "district"}
f22 = {(r["county"], r["district"]): (r["pop2022"] / wpd[(r["county"], r["district"])] if wpd[(r["county"], r["district"])] else 0) for r in dp}
cp = {r["key"]: r["pop2022"] for r in json.loads((D / "clan_pop.json").read_text(encoding="utf-8"))}
POPF = ["pop2025"] + [f"rp{rp}_{k}" for rp in (10, 100, 500) for k in ("pop", "pop_1m")]
out, cty = [], {}
for r in wp:
    if r["level"] == "county": continue
    r = dict(r); k = f22[(r["county"], r["district"])]
    if r["level"] == "clan" and r["key"] in cp:
        # clan census count; WorldPop says which share of the clan's people live in the flood zone
        tot = cp[r["key"]]; wpc = r["pop2025"]
        if wpc > 0: k = tot / wpc
        else:  # WorldPop has no settlement here: assume people spread like the land
            for rp in (10, 100, 500): r[f"rp{rp}_pop"] = r[f"rp{rp}_pop_1m"] = int(round(tot * r[f"rp{rp}_area_pct"] / 100))
            r["pop2025"] = tot; out.append(r); continue
    for f in POPF: r[f] = int(round(r[f] * k))
    if r["level"] == "district":
        r["pop2025"] = int(round(next(x["pop2022"] for x in dp if x["county"] == r["county"] and x["district"] == r["district"])))
        a = cty.setdefault(r["county"], {f: 0 for f in POPF})
        for f in POPF: a[f] += r[f]
    out.append(r)
for r in wp:
    if r["level"] == "county": r = dict(r); r.update(cty[r["county"]]); out.append(r)
for r in out:
    r["pop2022"] = r.pop("pop2025")
    for rp in (10, 100, 500): r[f"rp{rp}_pop_pct"] = round(r[f"rp{rp}_pop"] / r["pop2022"] * 100, 1) if r["pop2022"] else 0.0
    r["flood_level"] = "Warning" if r["rp100_pop_pct"] >= 10 else "Watch" if r["rp100_pop_pct"] >= 3 else "Low"
out.sort(key=lambda r: ({"county": 0, "district": 1, "clan": 2}[r["level"]], r["key"]))
(D / "flood_areas.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
cs = [r for r in out if r["level"] == "county"]
print("Liberia 2022:", sum(r["pop2022"] for r in cs), "· in 1-in-100-year zone:", sum(r["rp100_pop"] for r in cs))
for r in cs: print(f"  {r['county']:17} {r['rp100_pop_pct']:5}% {r['flood_level']}")
