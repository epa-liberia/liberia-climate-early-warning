"""County flood maps (1-in-100-year river flood zone) for Liberia's coastal counties.
Usage: python3 -I scripts/build_flood_atlas.py REPO SRC OUTDIR [County,County]
SRC holds lisgis2022/ (LISGIS 2022 geojson), flood/ (JRC RP100 and perm tiles) and ne/places.geojson (Natural Earth).
Labelling safeguard: a clan's name is printed only where it fits inside the clan and clashes with no other label;
otherwise the clan gets a number on the map and its name in the index."""
import sys, json, math, textwrap, numpy as np, rasterio, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle, Polygon as MPoly, FancyArrow
from matplotlib.colors import ListedColormap
from matplotlib.backends.backend_pdf import PdfPages
from rasterio.merge import merge
from rasterio import features
from shapely.geometry import shape, box, Point, MultiPolygon
from shapely.ops import polylabel, unary_union
from PIL import Image

REPO, SC, OUT = sys.argv[1:4]
COASTAL = ["Grand Cape Mount", "Bomi", "Montserrado", "Margibi", "Grand Bassa", "Rivercess", "Sinoe", "Grand Kru", "Maryland"]
NAVY, RED, INK, MUTED = "#0B1F44", "#BF0A30", "#1B2333", "#4A5568"
SEA, LAND, OTHER = "#E3EBF3", "#FBFBF8", "#ECEBE6"
DEPTH = ["#C6DBEF", "#6BAED6", "#2171B5", "#08306B"]
PERM = "#9DB2CF"

def jl(p): return json.load(open(p, encoding="utf-8"))
D = REPO + "/docs/data/"
simple_d = {f["properties"]["code"]: f["properties"] for f in jl(D + "districts.json")["features"]}
simple_k = {f["properties"]["clan_id"]: f["properties"] for f in jl(D + "clans.json")["features"]}
simple_c = {f["properties"]["code"]: f["properties"]["county"] for f in jl(D + "counties.json")["features"]}
L = SC + "/lisgis2022/"
def geo(name): return jl(L + name)["features"]
counties = {simple_c[f["properties"]["code"]]: shape(f["geometry"]).buffer(0) for f in geo("eee399ba-geo-counties-2022.geojson")}
districts = []
for f in geo("6e1bd1a3-geo-districts-2022.geojson"):
    p = simple_d[f["properties"]["code"]]; districts.append({"county": p["county"], "district": p["district"], "code": p["code"], "g": shape(f["geometry"]).buffer(0)})
clans = []
for f in geo("feae5eae-geo-clans-2022.geojson"):
    p = simple_k[f["properties"]["code"]]; clans.append({"county": p["county"], "district": p["district"], "clan": p["clan"], "id": p["clan_id"], "g": shape(f["geometry"]).buffer(0)})
fa = {r["key"]: r for r in jl(D + "flood_areas.json")}
places = {}
for f in jl(SC + "/ne/places.geojson")["features"]:
    p = f["properties"]
    if p.get("adm0name") == "Liberia": places[p["name"]] = tuple(f["geometry"]["coordinates"])
places["Tubmanburg"] = (-10.8172, 6.8708)
CAPITAL = {"Grand Cape Mount": "Robertsport", "Bomi": "Tubmanburg", "Montserrado": "Bensonville", "Margibi": "Kakata", "Grand Bassa": "Buchanan",
           "Rivercess": "Rivercess", "Sinoe": "Greenville", "Grand Kru": "Barclayville", "Maryland": "Harper"}
TOWNLABEL = {"Rivercess": "Cestos City"}
FL = SC + "/flood/"
logo = np.asarray(Image.open(REPO + "/docs/assets/epa-logo.png").convert("RGBA"))

def largest(g): return max(g.geoms, key=lambda x: x.area) if isinstance(g, MultiPolygon) else g
def draw_poly(ax, g, **kw):
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        ax.add_patch(MPoly(np.asarray(p.exterior.coords), closed=True, **kw))
def outline(ax, g, **kw):
    for p in (g.geoms if isinstance(g, MultiPolygon) else [g]):
        x, y = p.exterior.xy; ax.plot(x, y, **kw)

def depth_grid(bounds):
    out = {}
    for name in ("RP100", "perm"):
        arr, tr = merge([rasterio.open(FL + f"ID105_N10_W20_{name}.tif"), rasterio.open(FL + f"ID111_N10_W10_{name}.tif")], bounds=bounds)
        out[name] = (arr[0], tr)
    return out

def nice_km(span_km):
    for v in (100, 50, 25, 20, 10, 5, 2, 1):
        if v <= span_km / 4: return v
    return 1

HALO = [pe.withStroke(linewidth=2.6, foreground="#FBFBF8")]
FW, FH = 16.54, 11.69

def fit(bounds, frac_w, frac_h, kx, pad=0.05):
    x0, y0, x1, y1 = bounds; w, h = (x1 - x0) * kx, (y1 - y0)
    fw, fh = frac_w * FW, frac_h * FH
    w2, h2 = w * (1 + 2 * pad), h * (1 + 2 * pad)
    if w2 / h2 < fw / fh: w2 = h2 * fw / fh
    else: h2 = w2 * fh / fw
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return cx - w2 / kx / 2, cx + w2 / kx / 2, cy - h2 / 2, cy + h2 / 2

class Labeller:
    def __init__(self, fig, ax):
        self.fig, self.ax = fig, ax; fig.canvas.draw(); self.R = fig.canvas.get_renderer(); self.placed = []
        self.frame = self.data_box((ax.bbox.x0 + 6, ax.bbox.y0 + 6, ax.bbox.x1 - 6, ax.bbox.y1 - 6))
    def bbox(self, t, padpx=2):
        b = t.get_window_extent(self.R); return (b.x0 - padpx, b.y0 - padpx, b.x1 + padpx, b.y1 + padpx)
    def clash(self, b): return any(not (b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3]) for o in self.placed)
    def data_box(self, b):
        inv = self.ax.transData.inverted(); (a, c), (e, f) = inv.transform((b[0], b[1])), inv.transform((b[2], b[3]))
        return box(min(a, e), min(c, f), max(a, e), max(c, f))
    def visible(self, g): return g.intersects(self.frame)
    @staticmethod
    def candidates(g, n=40):
        g = largest(g); best = polylabel(g, tolerance=1e-5)
        xs0, ys0, xs1, ys1 = g.bounds; pts = [best]; rng = np.random.default_rng(7)
        for _ in range(n * 6):
            p = Point(rng.uniform(xs0, xs1), rng.uniform(ys0, ys1))
            if g.contains(p): pts.append(p)
            if len(pts) > n: break
        return sorted(pts, key=lambda p: p.distance(best))
    def try_text(self, x, y, s, must_fit=None, pad=2, **kw):
        t = self.ax.text(x, y, s, **kw); b = self.bbox(t, pad); db = self.data_box(b)
        if not self.clash(b) and self.frame.contains(db) and (must_fit is None or must_fit.contains(db)):
            self.placed.append(b); return t
        t.remove(); return None
    def number(self, g, num, allow_leader):
        kw = dict(ha="center", va="center", fontsize=6.8, fontweight="bold", color=NAVY, zorder=8,
                  bbox=dict(boxstyle="circle,pad=0.18", facecolor="#FBFBF8", edgecolor=NAVY, linewidth=0.6))
        for p in self.candidates(g, 25):
            if self.try_text(p.x, p.y, str(num), pad=0, **kw): return "ok"
        if not allow_leader: return "fail"
        # Leader line: nearest free spot within a few label widths, joined to the clan by a thin line.
        p0 = polylabel(largest(g), 1e-5); P = self.ax.transData.transform((p0.x, p0.y)); inv = self.ax.transData.inverted()
        for r in range(18, 160, 9):
            for a in np.linspace(0, 2 * np.pi, 24, endpoint=False):
                q = inv.transform((P[0] + r * np.cos(a), P[1] + r * np.sin(a)))
                t = self.try_text(q[0], q[1], str(num), pad=0, **kw)
                if t:
                    self.ax.plot([p0.x, q[0]], [p0.y, q[1]], color=NAVY, linewidth=0.5, zorder=7)
                    self.ax.plot([p0.x], [p0.y], marker="o", markersize=1.8, color=NAVY, zorder=7); return "leader"
        t = self.ax.text(p0.x, p0.y, str(num), **kw); self.placed.append(self.bbox(t, 0)); return "forced"

def base_map(fig, rect, cty, X0, X1, Y0, Y1, kx, clan_lw=0.45):
    ax = fig.add_axes(rect); cg = counties[cty]
    ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect(1 / kx); ax.set_facecolor(SEA); ax.set_xticks([]); ax.set_yticks([])
    for s_ in ax.spines.values(): s_.set_color("#8A97AB"); s_.set_linewidth(1)
    for n, g in counties.items():
        if n != cty: draw_poly(ax, g, facecolor=OTHER, edgecolor="#B9B6AC", linewidth=0.8, zorder=1)
    draw_poly(ax, cg, facecolor=LAND, edgecolor="none", zorder=1)
    gr = depth_grid((X0, Y0, X1, Y1)); dep, tr = gr["RP100"]; perm, _ = gr["perm"]
    inside = features.rasterize([(cg, 1)], out_shape=dep.shape, transform=tr, fill=0).astype(bool)
    cls = np.zeros(dep.shape, np.uint8); d = np.where(np.isfinite(dep), dep, 0)
    cls[(d > 0) & (d < 1)] = 1; cls[(d >= 1) & (d < 3)] = 2; cls[(d >= 3) & (d < 10)] = 3; cls[d >= 10] = 4; cls[perm == 1] = 5; cls[~inside] = 0
    ext = (tr.c, tr.c + tr.a * dep.shape[1], tr.f + tr.e * dep.shape[0], tr.f)
    ax.imshow(np.ma.masked_equal(cls, 0), cmap=ListedColormap(["#00000000"] + DEPTH + [PERM]), vmin=0, vmax=5, extent=ext, interpolation="nearest", zorder=2)
    for c in clans:
        if c["county"] == cty:
            for p_ in (c["g"].geoms if isinstance(c["g"], MultiPolygon) else [c["g"]]):
                x_, y_ = p_.exterior.xy
                ax.plot(x_, y_, color="#6B778A", linewidth=clan_lw, zorder=3, path_effects=[pe.withStroke(linewidth=clan_lw + 1.4, foreground="#FBFBF8")])
    for x in districts:
        if x["county"] == cty: outline(ax, x["g"], color="#3C4A63", linewidth=1.3, zorder=4)
    outline(ax, cg, color=NAVY, linewidth=2.6, zorder=5)
    ax.set_rasterization_zorder(5.5)  # map body as one image in the PDF; labels stay sharp text
    return ax

def scale_north(ax, X0, X1, Y0, Y1, kx):
    km_deg = 111.32 * kx; kmv = nice_km((X1 - X0) * km_deg)
    sx0, sy0 = X0 + (X1 - X0) * 0.04, Y0 + (Y1 - Y0) * 0.04; seg = kmv / km_deg
    for i in range(2):
        ax.add_patch(Rectangle((sx0 + i * seg / 2, sy0), seg / 2, (Y1 - Y0) * 0.008, facecolor=NAVY if i == 0 else "#FBFBF8", edgecolor=NAVY, linewidth=1, zorder=10))
    for v, xx in ((0, sx0), (kmv / 2, sx0 + seg / 2), (kmv, sx0 + seg)):
        ax.text(xx, sy0 + (Y1 - Y0) * 0.016, f"{v:g}", ha="center", va="bottom", fontsize=9, color=INK, path_effects=HALO, zorder=10)
    ax.text(sx0 + seg + (X1 - X0) * 0.008, sy0 + (Y1 - Y0) * 0.004, "km", ha="left", va="center", fontsize=9, color=INK, path_effects=HALO, zorder=10)
    nx, ny = X1 - (X1 - X0) * 0.04, Y1 - (Y1 - Y0) * 0.10
    ax.annotate("", xy=(nx, ny + (Y1 - Y0) * 0.055), xytext=(nx, ny), arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=2, mutation_scale=22), zorder=10)
    ax.text(nx, ny - (Y1 - Y0) * 0.012, "N", ha="center", va="top", fontsize=14, fontweight="bold", color=NAVY, zorder=10)

def label_towns(L, cty):
    ax = L.ax
    for tn in [CAPITAL[cty]] + (["Monrovia"] if cty == "Montserrado" else []):
        x, y = places[tn]
        if not L.frame.contains(Point(x, y)): continue
        ax.plot([x], [y], marker="*" if tn == "Monrovia" else "s", markersize=11 if tn == "Monrovia" else 7, color=RED, markeredgecolor="#FBFBF8", markeredgewidth=1, zorder=8)
        mb = ax.transData.transform((x, y)); L.placed.append((mb[0] - 7, mb[1] - 7, mb[0] + 7, mb[1] + 7))
        for dx, dy, ha, va in ((8, 0, "left", "center"), (-8, 0, "right", "center"), (0, 9, "center", "bottom"), (0, -9, "center", "top")):
            t = ax.annotate(TOWNLABEL.get(tn, tn), (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=11, fontweight="bold", color=RED, path_effects=HALO, zorder=9)
            b = L.bbox(t)
            if not L.clash(b): L.placed.append(b); break
            t.remove()

def label_districts(L, cty, fs=10.5):
    for x in sorted([d for d in districts if d["county"] == cty and L.visible(d["g"])], key=lambda r: -r["g"].area):
        lab = "\n".join(textwrap.wrap(x["district"].upper(), 18, break_long_words=False)); g = x["g"].intersection(L.frame)
        if g.is_empty: continue
        for p in L.candidates(g, 60):
            if L.try_text(p.x, p.y, lab, pad=3, ha="center", va="center", fontsize=fs, fontweight="bold", color="#3C4A63", linespacing=1.0, path_effects=HALO, zorder=7): break

def name_clan(L, c, sizes=(8, 7)):
    g = largest(c["g"]); fitg = g.buffer(0.0002)
    words = c["clan"]
    opts = [words] + (["\n".join(textwrap.wrap(words, max(6, len(words) // 2 + 1), break_long_words=False))] if " " in words else [])
    for fs in sizes:
        for lab in opts:
            for p in L.candidates(g, 25):
                if L.try_text(p.x, p.y, lab, must_fit=fitg, pad=1, ha="center", va="center", fontsize=fs, style="italic", color=INK, linespacing=0.95,
                              path_effects=[pe.withStroke(linewidth=2, foreground="#FBFBF8")], zorder=6): return True
    return False

def footer(fig, left_note):
    fig.text(0.025, 0.05, left_note, fontsize=9, color=MUTED)
    fig.text(0.975, 0.05, "EPA Liberia · Geospatial Information Services and Environmental Statistics Unit · 18 November 2026", fontsize=9, color=MUTED, ha="right")
    fig.text(0.025, 0.033, "River flooding only: coastal storm surge, swamps and wetlands, other low-lying ground and town drainage flooding are not yet included. Clan and district figures are residents whose homes lie inside the zone.", fontsize=8, color=MUTED)
    fig.text(0.025, 0.018, "Sources: EU Copernicus / JRC global river flood hazard map v2.1 (about 90 m); WorldPop 2025 scaled to the LISGIS 2022 census; LISGIS 2022 boundaries; Natural Earth (towns). Liberia El Niño Early Warning Platform.", fontsize=8, color=MUTED)

def header(fig, title, sub):
    fig.text(0.025, 0.955, title, fontsize=26, fontweight="bold", color=NAVY, va="top")
    fig.text(0.025, 0.912, sub, fontsize=12.5, color=MUTED, va="top")
    fig.add_artist(plt.Line2D([0.025, 0.975], [0.888, 0.888], color=RED, linewidth=3))
    lax = fig.add_axes([0.905, 0.905, 0.07, 0.07]); lax.imshow(logo); lax.axis("off")

def legend(fig, lx, ly, extra=()):
    fig.text(lx, ly, "Legend", fontsize=11.5, fontweight="bold", color=NAVY, va="top"); ly -= 0.03
    items = [("box", DEPTH[0], "Flood zone: under 1 m deep"), ("box", DEPTH[1], "1–3 m"), ("box", DEPTH[2], "3–10 m"), ("box", DEPTH[3], "Over 10 m"),
             ("box", PERM, "Rivers and lakes (permanent water)"), ("line", NAVY, "County boundary"), ("line", "#3C4A63", "District boundary"), ("line", "#8E99AB", "Clan boundary"),
             ("mark", RED, "County capital"), ("num", NAVY, "Clan too small to name (see index)")] + list(extra)
    for kind, col, lab in items:
        if kind == "box": fig.add_artist(Rectangle((lx, ly - 0.012), 0.016, 0.014, transform=fig.transFigure, facecolor=col, edgecolor="#8A97AB", linewidth=0.5))
        elif kind == "line": fig.add_artist(plt.Line2D([lx, lx + 0.016], [ly - 0.005, ly - 0.005], color=col, linewidth=2.6 if col == NAVY else (1.3 if col == "#3C4A63" else 0.8)))
        elif kind == "mark": fig.add_artist(plt.Line2D([lx + 0.008], [ly - 0.005], marker="s", color=col, markersize=7, markeredgecolor="#FBFBF8"))
        elif kind == "rect": fig.add_artist(Rectangle((lx, ly - 0.012), 0.016, 0.014, transform=fig.transFigure, facecolor="none", edgecolor=col, linewidth=1.6, linestyle="--"))
        else: fig.text(lx + 0.008, ly - 0.005, "7", ha="center", va="center", fontsize=7, fontweight="bold", color=col, bbox=dict(boxstyle="circle,pad=0.18", facecolor="#FBFBF8", edgecolor=col, linewidth=0.6))
        fig.text(lx + 0.022, ly - 0.005, lab, fontsize=9, color=INK, va="center"); ly -= 0.0215
    return ly

def enlarge(cty, numbered, zoom, kx, pdf, png_dir):
    """Safeguard 2 and 3. The enlargement places numbers only where they clash with nothing. Clans still left over are
    shown on detail pages, each a tile of the enlargement at a larger scale, where short leader lines are allowed."""
    where = "Greater Monrovia and surroundings" if cty == "Montserrado" else f"the {CAPITAL[cty]} area"
    def render(view, title, sub, only=None, skip=(), leaders=False, dry=False, tiles=(), lead_set=()):
        Z0, Z1, W0, W1 = view
        fig = plt.figure(figsize=(FW, FH), dpi=100)
        header(fig, title, sub)
        ax = base_map(fig, [0.025, 0.075, 0.95, 0.80], cty, Z0, Z1, W0, W1, kx, clan_lw=0.6)
        L2 = Labeller(fig, ax); label_towns(L2, cty); label_districts(L2, cty, fs=12)
        for k, t in tiles:
            ax.add_patch(Rectangle((t[0], t[2]), t[1] - t[0], t[3] - t[2], fill=False, edgecolor=RED, linewidth=1.8, linestyle="--", zorder=11))
            if not L2.try_text(max(t[0], Z0), min(t[3], W1), f"Detail {k}", pad=1, ha="left", va="top", fontsize=11, fontweight="bold", color=RED, path_effects=HALO, zorder=11):
                ax.text(max(t[0], Z0), min(t[3], W1), f" Detail {k}", ha="left", va="top", fontsize=11, fontweight="bold", color=RED, path_effects=HALO, zorder=11)
        todo = [c for c in numbered if L2.visible(c["g"]) and c["num"] not in skip and (only is None or c["num"] in only)]
        named = lead = forced = 0; left = []
        done = set()
        for c in todo:
            if name_clan(L2, c, sizes=(9, 8)): named += 1; done.add(c["num"])
        for c in todo:
            if c["num"] in done: continue
            r = L2.number(c["g"], c["num"], allow_leader=leaders or c["num"] in lead_set)
            if r == "fail": left.append(c)
            lead += r == "leader"; forced += r == "forced"
        if dry: plt.close(fig); return left
        scale_north(ax, Z0, Z1, W0, W1, kx)
        return fig, len(todo), named, lead, forced, left
    view = fit(zoom, 0.95, 0.80, kx, pad=0.03)
    left = render(view, "", "", dry=True)
    tiles = []
    if left:
        tw = (view[1] - view[0]) / 2.4; th = tw * kx * (0.80 * FH) / (0.95 * FW) / kx * kx
        th = (view[3] - view[2]) / 2.4
        pts = {c["num"]: polylabel(largest(c["g"]), 1e-5) for c in left}
        x0 = min(p.x for p in pts.values()); y1 = max(p.y for p in pts.values())
        cells = {}
        for n, p in pts.items(): cells.setdefault((int((p.x - x0) // tw), int((y1 - p.y) // th)), []).append(n)
        for i, ((cx, cy), ns) in enumerate(sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0]))):
            t = (x0 + cx * tw, x0 + (cx + 1) * tw, y1 - (cy + 1) * th, y1 - cy * th)
            tiles.append((chr(65 + i), t, set(ns)))
    few = set().union(*[t[2] for t in tiles if len(t[2]) < 3]) if tiles else set()
    tiles = [(chr(65 + i), t, ns) for i, (_, t, ns) in enumerate([x for x in tiles if len(x[2]) >= 3])]
    skip = set().union(*[t[2] for t in tiles]) if tiles else set()
    fig, n_, named, lead, forced, _ = render(view, f"{cty} County: {where} enlarged", "Same flood zone and boundaries as the county map, enlarged so that small clans can be read. Numbers match the clan index.",
                                            skip=skip, tiles=[(k, t) for k, t, _ in tiles], lead_set=few)
    note = f"{n_} numbered clans are placed in this view; {named} are named here" + (f", {lead} numbered with a short leader line" if lead else "")
    if tiles: note += f". {len(skip)} more, in the dashed boxes, are on the detail pages that follow"
    footer(fig, note + ".")
    pdf.savefig(fig, dpi=220); fig.savefig(f"{png_dir}/{cty.replace(' ', '_')}_flood_map_enlarged.png", dpi=150); plt.close(fig)
    out = [{"page": "enlarged", "clans": n_, "named": named}]
    for k, t, ns in tiles:
        tv = fit((t[0], t[2], t[1], t[3]), 0.95, 0.80, kx, pad=0.08)
        fig, n_, named, lead, forced, _ = render(tv, f"{cty} County: detail {k}", f"Part of {where}, shown at a larger scale. Numbers match the clan index.", only=ns, leaders=True)
        footer(fig, f"{n_} clans are placed on this detail page; {named} are named" + (f", {lead} numbered with a short leader line" if lead else "") + ".")
        pdf.savefig(fig, dpi=220); fig.savefig(f"{png_dir}/{cty.replace(' ', '_')}_flood_map_detail_{k}.png", dpi=150); plt.close(fig)
        out.append({"page": f"detail {k}", "clans": n_, "named": named, "leaders": lead, "forced": forced})
    return out

def page(cty, pdf, png_dir, zoom_in=None, dry=False):
    cg = counties[cty]; kx = math.cos(math.radians(cg.centroid.y)); crow = fa[f"county:{cty}"]
    myclans = sorted([c for c in clans if c["county"] == cty], key=lambda c: (c["district"], c["clan"]))
    mydist = [x for x in districts if x["county"] == cty]
    X0, X1, Y0, Y1 = fit(cg.bounds, 0.645, 0.80, kx)
    fig = plt.figure(figsize=(FW, FH), dpi=100)
    header(fig, f"{cty} County", f"River flood zone (1-in-100-year flood) and where people live  ·  {crow['rp100_pop']:,} of {crow['pop2022']:,} residents ({crow['rp100_pop_pct']:g}%) live inside the zone")
    ax = base_map(fig, [0.025, 0.075, 0.645, 0.80], cty, X0, X1, Y0, Y1, kx)
    L = Labeller(fig, ax); label_towns(L, cty); label_districts(L, cty)
    numbered, failed = [], []
    for c in myclans:
        if not name_clan(L, c): numbered.append(c)
    for i, c in enumerate(numbered, 1): c["num"] = i
    zb_ = box(*zoom_in) if zoom_in else None
    for c in numbered:
        if zb_ is not None and zb_.contains(polylabel(largest(c["g"]), 1e-5)): failed.append(c); continue
        if L.number(c["g"], c["num"], allow_leader=(zoom_in is None and not dry)) == "fail": failed.append(c)
    if dry:
        plt.close(fig)
        if len(failed) <= 3: return None  # a few stragglers get leader lines on the county map instead
        zb = unary_union([c["g"] for c in failed]).bounds
        return (zb[0] - 0.01, zb[1] - 0.01, zb[2] + 0.01, zb[3] + 0.01)
    # Safeguard 2: where even numbers cannot be placed cleanly, the area is shown enlarged on its own page.
    zoom = zoom_in
    if zoom:
        ax.add_patch(Rectangle((zoom[0], zoom[1]), zoom[2] - zoom[0], zoom[3] - zoom[1], fill=False, edgecolor=RED, linewidth=1.8, linestyle="--", zorder=11))
        for (xx, yy, ha, va) in ((zoom[0], zoom[1], "left", "top"), (zoom[0], zoom[3], "left", "bottom"), (zoom[2], zoom[1], "right", "top"), (zoom[2], zoom[3], "right", "bottom")):
            if L.try_text(xx, yy, "Enlarged on next page", pad=1, ha=ha, va=va, fontsize=9, fontweight="bold", color=RED, path_effects=HALO, zorder=11): break
        else: ax.text(zoom[0], zoom[1], "Enlarged on next page", ha="left", va="top", fontsize=9, fontweight="bold", color=RED, path_effects=HALO, zorder=11)
    scale_north(ax, X0, X1, Y0, Y1, kx)
    # Right panel: location, legend, tables.
    px = 0.69
    iax = fig.add_axes([px, 0.66, 0.13, 0.21])
    for n, g in counties.items(): draw_poly(iax, g, facecolor=RED if n == cty else "#D5DAE3", edgecolor="#FBFBF8", linewidth=0.5)
    allb = unary_union(list(counties.values())).bounds
    iax.set_xlim(allb[0], allb[2]); iax.set_ylim(allb[1], allb[3]); iax.set_aspect(1 / math.cos(math.radians(6.4))); iax.axis("off")
    iax.set_title("Location in Liberia", fontsize=9.5, color=MUTED, loc="left")
    legend(fig, 0.835, 0.865, [("rect", RED, "Area enlarged on next page")] if zoom else [])
    ty = 0.60 if not zoom else 0.585
    fig.text(px, ty, "People living inside the flood zone, by district", fontsize=11.5, fontweight="bold", color=NAVY, va="top"); ty -= 0.03
    cols = (px, px + 0.16, px + 0.222, px + 0.28)
    for xx, h, ha in zip(cols, ("District", "Residents", "In zone", "Share"), ("left", "right", "right", "right")):
        fig.text(xx, ty, h, fontsize=9, fontweight="bold", color=MUTED, va="top", ha=ha)
    ty -= 0.02
    drs = sorted([fa[f"district:{cty}:{x['district']}"] for x in mydist], key=lambda r: -r["rp100_pop"])
    if len(drs) > 11:
        rest = drs[10:]; drs = drs[:10] + [{"district": f"Other {len(rest)} districts", "pop2022": sum(r["pop2022"] for r in rest), "rp100_pop": sum(r["rp100_pop"] for r in rest)}]
        drs[-1]["rp100_pop_pct"] = round(drs[-1]["rp100_pop"] / drs[-1]["pop2022"] * 100, 1) if drs[-1]["pop2022"] else 0
    for r in drs:
        for xx, v, ha in zip(cols, (textwrap.shorten(r["district"], 34, placeholder="…"), f"{r['pop2022']:,}", f"{r['rp100_pop']:,}", f"{r['rp100_pop_pct']:g}%"), ("left", "right", "right", "right")):
            fig.text(xx, ty, v, fontsize=9, color=INK, va="top", ha=ha, style="italic" if r["district"].startswith("Other ") else "normal")
        ty -= 0.0185
    ty -= 0.012
    crows = sorted([fa[k] for k in (f"clan:{cty}:{c['district']}:{c['id']}" for c in myclans) if k in fa], key=lambda r: -r["rp100_pop"])[:5]
    fig.text(px, ty, "Most exposed clans (residents in the zone)", fontsize=11.5, fontweight="bold", color=NAVY, va="top"); ty -= 0.026
    for r in crows:
        fig.text(px, ty, textwrap.shorten(f"{r['clan']} ({r['district']})", 46, placeholder="…"), fontsize=9, color=INK, va="top")
        fig.text(cols[2], ty, f"{r['rp100_pop']:,}", fontsize=9, color=INK, va="top", ha="right")
        fig.text(cols[3], ty, f"{r['rp100_pop_pct']:g}%", fontsize=9, color=INK, va="top", ha="right"); ty -= 0.0185
    index_lines = [f"{c['num']:>3}  {c['clan']}  ({c['district']})" for c in numbered]
    rows_left = int((ty - 0.10) / 0.0165) - 2
    inline = numbered and len(index_lines) <= max(0, rows_left) * 2
    if inline:
        ty -= 0.014
        fig.text(px, ty, "Clan index (numbers on the map)", fontsize=11.5, fontweight="bold", color=NAVY, va="top"); ty -= 0.025
        half = math.ceil(len(index_lines) / 2)
        for j, s_ in enumerate(index_lines):
            fig.text(px + (0 if j < half else 0.145), ty - (j % half) * 0.0165, textwrap.shorten(s_, 33, placeholder="…"), fontsize=8, color=INK, va="top")
    elif numbered:
        ty -= 0.014
        fig.text(px, ty, f"Clan index: {len(numbered)} clans are numbered on the map;\ntheir names are listed on the index page.", fontsize=9.5, color=INK, va="top")
    footer(fig, f"{len(myclans) - len(numbered)} of {len(myclans)} clans are named on the map; {len(numbered)} are too small to name and carry a number instead."
                + (f" {len(failed)} are shown on the enlargement." if failed else ""))
    pdf.savefig(fig, dpi=220); fig.savefig(f"{png_dir}/{cty.replace(' ', '_')}_flood_map.png", dpi=150); plt.close(fig)
    stats = {"clans": len(myclans), "named": len(myclans) - len(numbered), "numbered": len(numbered), "to_zoom": len(failed)}
    if zoom:
        stats["enlargements"] = enlarge(cty, numbered, zoom, kx, pdf, png_dir)
    if numbered and not inline:
        fig = plt.figure(figsize=(FW, FH), dpi=100)
        header(fig, f"{cty} County: clan index", "Clans too small to name on the county map, by the number shown on the maps, with their district")
        ncol = 5; per = math.ceil(len(index_lines) / ncol); step = min(0.0175, 0.78 / per)
        for j, s_ in enumerate(index_lines):
            fig.text(0.025 + (j // per) * 0.193, 0.865 - (j % per) * step, textwrap.shorten(s_, 42, placeholder="…"), fontsize=8 if step >= 0.0165 else 7.4, color=INK, va="top")
        fig.text(0.975, 0.03, "EPA Liberia · Liberia El Niño Early Warning Platform · 18 November 2026", fontsize=8, color=MUTED, ha="right")
        pdf.savefig(fig, dpi=220); plt.close(fig)
    return stats

with PdfPages(f"{OUT}/EPA_Liberia_Coastal_County_Flood_Maps.pdf") as pdf:
    for cty in (sys.argv[4].split(",") if len(sys.argv) > 4 else COASTAL):
        z = page(cty, pdf, OUT, dry=True)
        print(cty, page(cty, pdf, OUT, zoom_in=z), flush=True)
