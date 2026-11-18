"""GIS package of Liberia's river flood layer (JRC Copernicus global river flood hazard maps v2.1) with exposure by area.
Usage: python3 -I scripts/build_flood_gis.py REPO SRC OUTDIR
SRC holds flood/ (JRC RP10, RP100, RP500 and perm tiles ID105_N10_W20_*, ID111_N10_W10_*) and lisgis2022/ (LISGIS 2022 geojson).
Writes, in OUTDIR:
  liberia_flood_depth_rp10.tif, _rp100.tif, _rp500.tif   flood depth in metres, clipped to Liberia, permanent water removed
  liberia_permanent_water.tif                            1 = permanent river or lake
  liberia_flood_extent.gpkg      layers flood_rp10 / flood_rp100 / flood_rp500 (polygons by depth class), permanent_water
  liberia_flood_exposure.gpkg    layers counties / districts / clans: LISGIS 2022 boundaries with residents in each flood zone
  (and the same layers as shapefiles in shapefiles/)"""
import sys, json, pathlib, numpy as np, rasterio, geopandas as gpd, pandas as pd
from rasterio.merge import merge
from rasterio.mask import mask
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

REPO, SRC, OUT = (pathlib.Path(a) for a in sys.argv[1:4]); OUT.mkdir(parents=True, exist_ok=True)
FL = SRC / "flood"; L = SRC / "lisgis2022"
def jl(p): return json.load(open(p, encoding="utf-8"))
D = REPO / "docs" / "data"
simple_c = {f["properties"]["code"]: f["properties"]["county"] for f in jl(D / "counties.json")["features"]}
simple_d = {f["properties"]["code"]: f["properties"] for f in jl(D / "districts.json")["features"]}
simple_k = {f["properties"]["clan_id"]: f["properties"] for f in jl(D / "clans.json")["features"]}
def gfile(pat): return next(p for p in sorted(L.glob(f"*{pat}*.geojson")) if "simplified" not in p.name)
C = gpd.read_file(gfile("counties-2022")); Dd = gpd.read_file(gfile("districts-2022")); K = gpd.read_file(gfile("clans-2022"))
for g in (C, Dd, K): g.set_crs(4326, inplace=True, allow_override=True); g["geometry"] = g.geometry.buffer(0)
liberia = unary_union(C.geometry)

# Rasters: mosaic the two JRC tiles, clip to Liberia, drop permanent water from the flood depth.
def mosaic(name, nodata):
    srcs = [rasterio.open(FL / f"ID105_N10_W20_{name}.tif"), rasterio.open(FL / f"ID111_N10_W10_{name}.tif")]
    arr, tr = merge(srcs, bounds=liberia.bounds, nodata=nodata)
    prof = srcs[0].profile.copy(); prof.update(height=arr.shape[1], width=arr.shape[2], transform=tr, count=1, nodata=nodata, compress="deflate", predictor=2 if arr.dtype.kind == "f" else 1, tiled=True, blockxsize=256, blockysize=256, crs="EPSG:4326")
    return arr[0], tr, prof
perm, tr, pprof = mosaic("perm", 255)
inside = features.rasterize([(liberia, 1)], out_shape=perm.shape, transform=tr, fill=0).astype(bool)
permw = (perm == 1) & inside
pprof.update(dtype="uint8", nodata=0)
with rasterio.open(OUT / "liberia_permanent_water.tif", "w", **pprof) as d: d.write(permw.astype("uint8"), 1)
CLS = [(0, 1, 1, "under 1 m"), (1, 3, 2, "1-3 m"), (3, 10, 3, "3-10 m"), (10, 1e9, 4, "over 10 m")]
layers = {}
for rp in (10, 100, 500):
    dep, tr2, prof = mosaic(f"RP{rp}", -9999.0)
    dep = dep.astype("float32"); valid = np.isfinite(dep) & (dep > 0) & inside & ~permw
    out = np.where(valid, dep, -9999.0).astype("float32")
    prof.update(dtype="float32", nodata=-9999.0)
    with rasterio.open(OUT / f"liberia_flood_depth_rp{rp}.tif", "w", **prof) as d:
        d.write(out, 1); d.update_tags(units="metres", source="JRC Copernicus global river flood hazard map v2.1", return_period=f"1-in-{rp}-year")
    cls = np.zeros(dep.shape, np.uint8)
    for lo, hi, k, _ in CLS: cls[valid & (dep > lo if lo == 0 else dep >= lo) & (dep < hi)] = k
    recs = [{"depth_cls": int(v), "geometry": shape(g)} for g, v in features.shapes(cls, mask=cls > 0, transform=tr2, connectivity=8)]
    gdf = gpd.GeoDataFrame(recs, crs=4326).dissolve(by="depth_cls", as_index=False)
    gdf["depth"] = gdf["depth_cls"].map({k: lab for _, _, k, lab in CLS}); gdf["ret_period"] = f"1-in-{rp}-year"
    area = gdf.to_crs(32629).area / 1e6; gdf["area_km2"] = area.round(2)
    layers[f"flood_rp{rp}"] = gdf[["depth_cls", "depth", "ret_period", "area_km2", "geometry"]]
    print(f"RP{rp}:", round(float(gdf['area_km2'].sum()), 1), "km2")
pw = [{"water": 1, "geometry": shape(g)} for g, v in features.shapes(permw.astype("uint8"), mask=permw, transform=tr, connectivity=8)]
pwg = gpd.GeoDataFrame(pw, crs=4326).dissolve(by="water", as_index=False); pwg["area_km2"] = (pwg.to_crs(32629).area / 1e6).round(2)
layers["permanent_water"] = pwg
for i, (n, g) in enumerate(layers.items()):
    g.to_file(OUT / "liberia_flood_extent.gpkg", layer=n, driver="GPKG", mode="w" if i == 0 else "a")

# Exposure: residents (2022 census basis) inside each flood zone, joined to LISGIS 2022 boundaries.
fa = {r["key"]: r for r in jl(D / "flood_areas.json")}
F = ["pop2022", "rp10_pop", "rp10_pop_pct", "rp100_pop", "rp100_pop_pct", "rp500_pop", "rp500_pop_pct", "rp100_area_pct", "flood_level"]
def attach(g, keyf, extra):
    rows = []
    for _, r in g.iterrows():
        key, ex = keyf(r); a = fa.get(key, {})
        rows.append({**ex, **{k: a.get(k) for k in F}, "geometry": r.geometry})
    return gpd.GeoDataFrame(rows, crs=4326)
cty = attach(C, lambda r: (f"county:{simple_c[r['code']]}", {"cty_code": r["code"], "county": simple_c[r["code"]]}), None)
dis = attach(Dd, lambda r: (f"district:{simple_d[r['code']]['county']}:{simple_d[r['code']]['district']}",
                           {"dist_code": r["code"], "district": simple_d[r["code"]]["district"], "county": simple_d[r["code"]]["county"]}), None)
cl = attach(K, lambda r: (f"clan:{simple_k[r['code']]['county']}:{simple_k[r['code']]['district']}:{r['code']}",
                         {"clan_code": r["code"], "clan": simple_k[r["code"]]["clan"], "district": simple_k[r["code"]]["district"], "county": simple_k[r["code"]]["county"]}), None)
ren = {"rp10_pop": "rp10_pop", "rp10_pop_pct": "rp10_pct", "rp100_pop": "rp100_pop", "rp100_pop_pct": "rp100_pct", "rp500_pop": "rp500_pop", "rp500_pop_pct": "rp500_pct", "rp100_area_pct": "rp100_apct", "flood_level": "fl_level"}
(OUT / "shapefiles").mkdir(exist_ok=True)
for i, (n, g) in enumerate((("counties", cty), ("districts", dis), ("clans", cl))):
    g = g.rename(columns=ren)
    g.to_file(OUT / "liberia_flood_exposure.gpkg", layer=n, driver="GPKG", mode="w" if i == 0 else "a")
    g.to_file(OUT / "shapefiles" / f"liberia_flood_exposure_{n}.shp", encoding="utf-8")
    g.drop(columns="geometry").to_csv(OUT / f"liberia_flood_exposure_{n}.csv", index=False, encoding="utf-8")
    print(n, len(g), "missing exposure:", int(g["pop2022"].isna().sum()))
for n in ("flood_rp100", "permanent_water"):
    layers[n].to_file(OUT / "shapefiles" / f"liberia_{n}.shp", encoding="utf-8")
