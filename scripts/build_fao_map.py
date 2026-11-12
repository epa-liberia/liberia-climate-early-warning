"""Build FAO ASIS 1 km drought map files for Liberia (Agricultural Stress Index, last N dekads; Historic Drought Frequency).
Usage: python3 -I build_fao_map.py OUTDIR BOUNDARY_DIR [N]
BOUNDARY_DIR holds counties.json, districts.json, clans.json (GeoJSON, lon/lat).
Writes fao_map.json and fao_map_areas.json."""
import sys, io, re, json, base64, datetime, urllib.request, numpy as np
from PIL import Image
from rasterio import features
from affine import Affine
OUT, BD = sys.argv[1], sys.argv[2]; N = int(sys.argv[3]) if len(sys.argv) > 3 else 12
WMTS = "https://data.apps.fao.org/map/wmts/wmts"
UA = {"User-Agent": "Mozilla/5.0 (Liberia EPA El Nino platform)"}
LON0, LON1, LAT0, LAT1 = -11.7, -7.2, 4.1, 8.7
Z = 7; TD = 180 / 2 ** Z; PX = TD / 256
COLORS = {(47, 205, 0): 1, (154, 231, 19): 2, (255, 255, 48): 3, (255, 186, 32): 4, (255, 117, 16): 5, (255, 42, 2): 6, (196, 0, 0): 7,
          (102, 102, 255): 8, (0, 0, 0): 9, (102, 102, 102): 10, (204, 204, 204): 11}
PAL = {0: (0, 0, 0, 0), 1: (47, 205, 0, 255), 2: (154, 231, 19, 255), 3: (255, 255, 48, 255), 4: (255, 186, 32, 255), 5: (255, 117, 16, 255),
       6: (255, 42, 2, 255), 7: (196, 0, 0, 255), 8: (102, 102, 255, 255), 9: (40, 40, 40, 255), 10: (120, 120, 120, 255), 11: (226, 226, 222, 255)}
ASI_MID = {1: 5, 2: 17.5, 3: 32.5, 4: 47.5, 5: 62.5, 6: 77.5, 7: 92.5}
HDF_MID = {1: 2.5, 2: 7.5, 3: 12.5, 4: 17.5, 5: 22.5, 6: 27.5, 7: 35}
def get(url):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r: return r.read()
        except Exception:
            if k == 2: raise
def mosaic(layer, date, extra):
    c0, c1 = int((LON0 + 180) // TD), int((LON1 + 180) // TD); r0, r1 = int((90 - LAT1) // TD), int((90 - LAT0) // TD)
    big = Image.new("RGBA", ((c1 - c0 + 1) * 256, (r1 - r0 + 1) * 256))
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            u = (f"{WMTS}?layer=fao-gismgr/ASIS/mapsets/{layer}&style=&tilematrixset=EPSG:4326&tilematrix={Z}&tilerow={r}&tilecol={c}"
                 f"&format=image/png&service=WMTS&version=1.0.0&request=GetTile" + (f"&Time={date}" if date else "") + extra)
            big.paste(Image.open(io.BytesIO(get(u))).convert("RGBA"), ((c - c0) * 256, (r - r0) * 256))
    ox = round((LON0 - (c0 * TD - 180)) / PX); oy = round(((90 - r0 * TD) - LAT1) / PX)
    w = round((LON1 - LON0) / PX); h = round((LAT1 - LAT0) / PX)
    return big.crop((ox, oy, ox + w, oy + h))
def classes(img):
    a = np.asarray(img); out = np.zeros(a.shape[:2], np.uint8)
    rgb = a[..., :3].astype(int); alpha = a[..., 3]
    keys = np.array(list(COLORS.keys())); vals = np.array(list(COLORS.values()))
    d = ((rgb[..., None, :] - keys[None, None, :, :]) ** 2).sum(-1)
    k = d.argmin(-1); ok = (d.min(-1) < 200) & (alpha > 128)
    out[ok] = vals[k[ok]]
    return out
def png(g):
    p = Image.new("P", (g.shape[1], g.shape[0])); flat = []
    for i in range(256): flat += list(PAL.get(i, (0, 0, 0, 0))[:3])
    p.putpalette(flat); p.putdata(g.ravel().tolist())
    p.info["transparency"] = bytes([PAL.get(i, (0, 0, 0, 0))[3] for i in range(256)])
    b = io.BytesIO(); p.save(b, "PNG", optimize=True, transparency=p.info["transparency"])
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
caps = get(f"{WMTS}?service=WMTS&request=GetCapabilities&version=1.0.0&layer=fao-gismgr/ASIS/mapsets/ASI-D").decode("utf-8", "ignore")
vals = re.search(r"<ows:Identifier>time</ows:Identifier>\s*<Value>([^<]*)</Value>", caps).group(1).split(",")
dates = vals[-N:]
EX = "&dim_season=GS1&dim_lct=LC-C"
days = []; last_grid = None
for d in dates:
    g = classes(mosaic("ASI-D", d, EX)); days.append({"date": d, "image": png(g)}); last_grid = g
hdf = classes(mosaic("HDF", None, EX + "&dim_pal=AL30"))
H, W = last_grid.shape
tr = Affine(PX, 0, LON0, 0, -PX, LAT1)
def stats(geom):
    m = features.rasterize([(geom, 1)], out_shape=(H, W), transform=tr, fill=0, all_touched=True).astype(bool)
    v = last_grid[m]; crop = v[(v >= 1) & (v <= 7)]; hv = hdf[m]; hc = hv[(hv >= 1) & (hv <= 7)]
    n = int(len(crop))
    return {"crop_px": n, "offseason_px": int((v == 8).sum()),
            "stressed_pct": round(float((crop >= 3).mean() * 100), 1) if n else None,
            "index_est": round(float(np.mean([ASI_MID[int(x)] for x in crop])), 1) if n else None,
            "hdf_pct": round(float(np.mean([HDF_MID[int(x)] for x in hc])), 1) if len(hc) else None}
areas = []
for lvl, fn in [("county", "counties.json"), ("district", "districts.json"), ("clan", "clans.json")]:
    for f in json.load(open(f"{BD}/{fn}", encoding="utf-8"))["features"]:
        p = f["properties"]
        row = {"level": lvl, "county": p["county"], "district": p.get("district", ""), "clan_id": p.get("clan_id", ""), "date": dates[-1]}
        if lvl == "clan": row["clan"] = p.get("clan", "")
        row["key"] = lvl + ":" + row["county"] + (":" + row["district"] if row["district"] else "") + (":" + str(row["clan_id"]) if row["clan_id"] != "" else "")
        row.update(stats(f["geometry"])); areas.append(row)
out = {"bbox": [LON0, LAT0, LON1, LAT1], "width": W, "height": H, "latest": dates[-1], "season": "Season 1", "landcover": "Cropland",
       "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "days": days, "hdf_image": png(hdf)}
json.dump(out, open(f"{OUT}/fao_map.json", "w"), separators=(",", ":"))
json.dump(areas, open(f"{OUT}/fao_map_areas.json", "w"), ensure_ascii=False)
print("dekads", dates[0], dates[-1], len(days), "size", round(len(json.dumps(out)) / 1e6, 2), "MB", "areas", len(areas))
