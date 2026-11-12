"""Build flood exposure files for Liberia from JRC Copernicus global river flood hazard maps (v2.1) and WorldPop 2025.
Usage: python3 -I build_flood.py INDIR BOUNDARY_DIR OUTDIR
INDIR holds ID105_N10_W20_RP{10,100,500}.tif, ID111_N10_W10_RP{...}.tif, *_perm.tif and lbr_pop_2025.tif.
Writes flood_map.json (display images) and flood_areas.json (per county, district, clan)."""
import sys, io, json, base64, numpy as np, rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling
from rasterio import features
from PIL import Image
IN, BD, OUT = sys.argv[1:4]
RPS = [10, 100, 500]
pop_src = rasterio.open(f"{IN}/lbr_pop_2025.tif")
pop = pop_src.read(1).astype("float64"); pop[pop < 0] = 0
H, W, T = pop_src.height, pop_src.width, pop_src.transform
def onto_grid(paths, resampling=Resampling.nearest, dtype="float32", nodata=-9999):
    arr, tr = merge([rasterio.open(p) for p in paths], nodata=nodata)
    out = np.full((H, W), nodata, dtype=dtype)
    reproject(arr[0], out, src_transform=tr, src_crs="EPSG:4326", dst_transform=T, dst_crs="EPSG:4326", resampling=resampling, src_nodata=nodata, dst_nodata=nodata)
    return out
perm = onto_grid([f"{IN}/ID105_N10_W20_perm.tif", f"{IN}/ID111_N10_W10_perm.tif"], dtype="uint8", nodata=255) == 1
counties = json.load(open(f"{BD}/counties.json"))["features"]
inside = features.rasterize([(f["geometry"], 1) for f in counties], out_shape=(H, W), transform=T, fill=0).astype(bool)
lat = T.f + (np.arange(H) + 0.5) * T.e
cell_km2 = (abs(T.e) * 111.32) * (abs(T.a) * 111.32 * np.cos(np.radians(lat)))
AREA = np.repeat(cell_km2[:, None], W, axis=1)
depth = {}
for rp in RPS:
    d = onto_grid([f"{IN}/ID105_N10_W20_RP{rp}.tif", f"{IN}/ID111_N10_W10_RP{rp}.tif"])
    d[(d <= 0) | perm | ~inside] = 0
    depth[rp] = d
# display images: 3x3 block max depth class, palette PNG
PAL = {0: (0, 0, 0, 0), 1: (158, 202, 225, 255), 2: (66, 146, 198, 255), 3: (8, 81, 156, 255), 4: (8, 48, 107, 255), 5: (120, 120, 120, 150)}
def cls(d): return np.where(d <= 0, 0, np.where(d < 1, 1, np.where(d < 3, 2, np.where(d < 10, 3, 4)))).astype(np.uint8)
def png(g):
    p = Image.new("P", (g.shape[1], g.shape[0])); flat = []
    for i in range(256): flat += list(PAL.get(i, (0, 0, 0, 0))[:3])
    p.putpalette(flat); p.putdata(g.ravel().tolist())
    tr = bytes([PAL.get(i, (0, 0, 0, 0))[3] for i in range(256)])
    b = io.BytesIO(); p.save(b, "PNG", optimize=True, transparency=tr)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
K = 3
h2, w2 = H // K, W // K
def block_max(a): return a[:h2 * K, :w2 * K].reshape(h2, K, w2, K).max(axis=(1, 3))
permb = block_max(perm.astype(np.uint8) * inside.astype(np.uint8))
imgs = {}
for rp in RPS:
    g = block_max(cls(depth[rp])); g = np.where((g == 0) & (permb == 1), 5, g); imgs[str(rp)] = png(g)
bbox = [T.c, T.f + h2 * K * T.e, T.c + w2 * K * T.a, T.f]
json.dump({"bbox": bbox, "width": w2, "height": h2, "return_periods": RPS, "images": imgs,
           "classes": {"1": "Under 1 m", "2": "1–3 m", "3": "3–10 m", "4": "Over 10 m", "5": "Permanent water"}}, open(f"{OUT}/flood_map.json", "w"), separators=(",", ":"))
# per-area statistics
def stats(geom):
    m = features.rasterize([(geom, 1)], out_shape=(H, W), transform=T, fill=0, all_touched=True).astype(bool) & inside
    land = m & ~perm; a_land = float(AREA[land].sum()); p_tot = float(pop[m].sum())
    r = {"area_km2": round(a_land, 1), "pop2025": int(round(p_tot))}
    for rp in RPS:
        f = land & (depth[rp] > 0); deep = land & (depth[rp] >= 1)
        r[f"rp{rp}_km2"] = round(float(AREA[f].sum()), 1)
        r[f"rp{rp}_area_pct"] = round(100 * float(AREA[f].sum()) / a_land, 1) if a_land else 0
        r[f"rp{rp}_pop"] = int(round(float(pop[f].sum())))
        r[f"rp{rp}_pop_pct"] = round(100 * float(pop[f].sum()) / p_tot, 1) if p_tot else 0
        r[f"rp{rp}_pop_1m"] = int(round(float(pop[deep].sum())))
    return r
def level(r):
    p = r["rp100_pop_pct"]
    return "Warning" if p >= 10 else "Watch" if p >= 3 else "Low"
areas = []
for lvl, fn in [("county", "counties.json"), ("district", "districts.json"), ("clan", "clans.json")]:
    for f in json.load(open(f"{BD}/{fn}"))["features"]:
        p = f["properties"]
        row = {"level": lvl, "county": p["county"], "district": p.get("district", ""), "clan_id": p.get("clan_id", "")}
        if lvl == "clan": row["clan"] = p.get("clan", "")
        row["key"] = lvl + ":" + row["county"] + (":" + row["district"] if row["district"] else "") + (":" + str(row["clan_id"]) if row["clan_id"] != "" else "")
        row.update(stats(f["geometry"])); row["flood_level"] = level(row); areas.append(row)
json.dump(areas, open(f"{OUT}/flood_areas.json", "w"), ensure_ascii=False)
tot = {rp: int(pop[inside & ~perm & (depth[rp] > 0)].sum()) for rp in RPS}
print("people in flood zones", tot, "of", int(pop[inside].sum()), "areas", len(areas), "image", w2, "x", h2)
