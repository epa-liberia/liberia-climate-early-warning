"""Build 30-day NASA GIBS ocean-temperature and rainfall map files for the Liberia El Nino platform.
Usage: python3 -I build_ocean.py OUTDIR [DAYS]
Writes ocean_pacific.json, ocean_wafrica.json, rain_wafrica.json."""
import sys, io, json, base64, re, urllib.request, datetime, concurrent.futures as cf
from PIL import Image
OUT = sys.argv[1]; NDAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r: return r.read()
        except Exception as e:
            if k == tries - 1: raise
def b64(data, mime): return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())
caps = get(WMS + "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0").decode("utf-8", "ignore")
def dates(layer, n):
    i = caps.index("<Name>%s</Name>" % layer)
    dim = re.search(r"<Dimension[^>]*>([^<]*)</Dimension>", caps[i:i + 6000]).group(1)
    out = []
    for part in reversed(dim.split(",")):
        a, b = part.split("/")[:2]
        d0 = datetime.date.fromisoformat(a[:10]); d = datetime.date.fromisoformat(b[:10])
        while d >= d0 and len(out) < n:
            out.append(d.isoformat()); d -= datetime.timedelta(days=1)
        if len(out) >= n: break
    return sorted(out)
def colormap(name, unit_title):
    x = get("https://gibs.earthdata.nasa.gov/colormaps/v1.3/%s.xml" % name).decode()
    lut = {}; bins = {}
    for m in re.finditer(r"<ColorMapEntry ([^>]*)/>", x):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        ref = int(a["ref"]); rgb = tuple(int(v) for v in a["rgb"].split(","))
        if a.get("nodata") == "true": continue
        lut.setdefault(rgb, ref); bins[ref] = a.get("value", "")
    return lut, bins
def wms(layer, lon0, lon1, lat0, lat1, w, h, date=None, fmt="image/png"):
    q = (f"?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES=&CRS=EPSG:4326&BBOX={lat0},{lon0},{lat1},{lon1}"
         f"&WIDTH={w}&HEIGHT={h}&FORMAT={fmt}&TRANSPARENT=TRUE" + (f"&TIME={date}" if date else ""))
    return Image.open(io.BytesIO(get(WMS + q))).convert("RGBA")
def strip(layer, parts, lat0, lat1, ppd, date=None):
    ims = [wms(layer, a, b, lat0, lat1, round((b - a) * ppd), round((lat1 - lat0) * ppd), date) for a, b in parts]
    W = sum(i.width for i in ims); out = Image.new("RGBA", (W, ims[0].height)); x = 0
    for i in ims: out.paste(i, (x, 0)); x += i.width
    return out
def decode(img, lut):
    px = img.load(); w, h = img.size; buf = bytearray(w * h); cache = {}
    keys = list(lut.keys())
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128: buf[y * w + x] = 0; continue
            c = (r, g, b)
            if c in lut: v = lut[c]
            elif c in cache: v = cache[c]
            else:
                k = min(keys, key=lambda q: (q[0]-r)**2 + (q[1]-g)**2 + (q[2]-b)**2)
                v = lut[k] if (k[0]-r)**2 + (k[1]-g)**2 + (k[2]-b)**2 < 300 else 0
                cache[c] = v
            buf[y * w + x] = min(v, 254) + 1 if v else 0
    return base64.b64encode(bytes(buf)).decode()
SST = ("GHRSST_L4_MUR_Sea_Surface_Temperature_Anomalies", "GHRSST_Sea_Surface_Temperature_Anomalies")
RAIN = ("IMERG_Precipitation_Rate", "GPM_Precipitation_Rate")
VIEWS = [
  dict(id="ocean_pacific", layer=SST, parts=[(120, 180), (-180, 20)], lon0=120, span=260, lat0=-25, lat1=25, ppd=4, gppd=1, bg=(205, 205, 205), q=72),
  dict(id="ocean_wafrica", layer=SST, parts=[(-25, 15)], lon0=-25, span=40, lat0=-5, lat1=20, ppd=16, gppd=4, bg=(205, 205, 205), q=74),
  dict(id="rain_wafrica", layer=RAIN, parts=[(-25, 15)], lon0=-25, span=40, lat0=-5, lat1=20, ppd=16, gppd=4, bg=(232, 232, 228), q=74),
]
legend = {SST[0]: b64(get("https://gibs.earthdata.nasa.gov/legends/GHRSST_Sea_Surface_Temperature_Anomalies_H.png"), "image/png"),
          RAIN[0]: b64(get("https://gibs.earthdata.nasa.gov/legends/GPM_Precipitation_Rate_H.png"), "image/png")}
cmaps = {SST[0]: colormap(SST[1], "°C"), RAIN[0]: colormap(RAIN[1], "mm/hr")}
coast = {}
for v in VIEWS:
    key = v["id"].split("_")[1]
    if key not in coast: coast[key] = strip("Coastlines_15m", v["parts"], v["lat0"], v["lat1"], v["ppd"])
def build_day(v, date):
    layer = v["layer"][0]; lut, _ = cmaps[layer]
    img = strip(layer, v["parts"], v["lat0"], v["lat1"], v["ppd"], date)
    base = Image.new("RGBA", img.size, v["bg"] + (255,)); base.alpha_composite(img); base.alpha_composite(coast[v["id"].split("_")[1]])
    jb = io.BytesIO(); base.convert("RGB").save(jb, "JPEG", quality=v["q"], optimize=True)
    g = strip(layer, v["parts"], v["lat0"], v["lat1"], v["gppd"], date)
    return {"date": date, "image": b64(jb.getvalue(), "image/jpeg"), "grid": decode(g, lut)}
for v in VIEWS:
    layer = v["layer"][0]; ds = dates(layer, NDAYS)
    with cf.ThreadPoolExecutor(6) as ex: days = list(ex.map(lambda d: build_day(v, d), ds))
    _, bins = cmaps[layer]
    gw = round(v["span"] * v["gppd"]); gh = round((v["lat1"] - v["lat0"]) * v["gppd"])
    out = {"view": v["id"], "layer": "sst" if layer == SST[0] else "rain", "source": layer,
           "unit": "°C" if layer == SST[0] else "mm/hr", "lon0": v["lon0"], "lon_span": v["span"], "lat_min": v["lat0"], "lat_max": v["lat1"],
           "grid_w": gw, "grid_h": gh, "bins": {str(k + 1 if k < 255 else 255): val for k, val in bins.items()},
           "legend": legend[layer], "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "days": days}
    json.dump(out, open(f"{OUT}/{v['id']}.json", "w"), separators=(",", ":"))
    print(v["id"], ds[0], ds[-1], len(days), round(len(json.dumps(out)) / 1e6, 2), "MB")
