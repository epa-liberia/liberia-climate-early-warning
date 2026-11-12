"""Average wind per county, district and clan from Global Wind Atlas 3 rasters (250 m, CC BY 4.0).
Usage: python3 -I scripts/build_wind.py GWA_DIR BOUNDARY_DIR OUT_JSON
GWA_DIR holds the LBR_wind-speed_{10,50,100}m.tif and LBR_power-density_{10,50,100}m.tif files from globalwindatlas.info."""
import sys, glob, json, numpy as np, rasterio
from rasterio import features
GWA, BD, OUT = sys.argv[1:4]
LAYERS = {}
for h in (10, 50, 100):
    LAYERS[f"ws{h}"] = sorted(glob.glob(f"{GWA}/*wind-speed_{h}m.tif"))[0]
    LAYERS[f"pd{h}"] = sorted(glob.glob(f"{GWA}/*power-density_{h}m.tif"))[0]
ref = rasterio.open(LAYERS["ws100"]); T, H, W = ref.transform, ref.height, ref.width
A = {k: rasterio.open(p).read(1).astype("float64") for k, p in LAYERS.items()}
ROUND = {"ws10": 2, "ws50": 2, "ws100": 2, "pd10": 1, "pd50": 0, "pd100": 0}
def rnd(k, v): return None if v is None or not np.isfinite(v) else (int(round(v)) if ROUND[k] == 0 else round(float(v), ROUND[k]))
rows = []
for lvl, fn in [("county", "counties.json"), ("district", "districts.json"), ("clan", "clans.json")]:
    for f in json.load(open(f"{BD}/{fn}", encoding="utf-8"))["features"]:
        p = f["properties"]
        m = features.rasterize([(f["geometry"], 1)], out_shape=(H, W), transform=T, fill=0, all_touched=True).astype(bool)
        r = {"level": lvl, "county": p["county"], "district": p.get("district", ""), "clan_id": p.get("clan_id", "")}
        if lvl == "clan": r["clan"] = p.get("clan", "")
        r["key"] = lvl + ":" + r["county"] + (":" + r["district"] if r["district"] else "") + (":" + str(r["clan_id"]) if r["clan_id"] != "" else "")
        for k, a in A.items():
            v = a[m]; v = v[np.isfinite(v)]
            r[k + "_mean"] = rnd(k, v.mean()) if v.size else None
            if k in ("ws10", "ws50", "ws100", "pd10", "pd50", "pd100"): r[k + "_max"] = rnd(k, v.max()) if v.size else None
        r["cells"] = int(m.sum())
        rows.append(r)
json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(rows), "areas")
