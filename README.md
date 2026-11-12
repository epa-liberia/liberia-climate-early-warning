# Liberia El Niño Early Warning Platform

Public website of the Environmental Protection Agency of Liberia for monitoring the 2026–27 El Niño and preparing for its hazards. It runs in any web browser, needs no login, and updates itself from NOAA, NASA and FAO.

The same page also runs as a Claude dashboard for partner agencies. Both versions use the same page file (`page/index.html`) and the same data scripts, so a change to one is a change to both.

## What is in this folder

| Path | What it is |
| --- | --- |
| `page/index.html` | The page itself: tabs, maps, charts, text. Shared with the Claude version. Edit this, not `docs/index.html`. |
| `docs/` | The website as served. `docs/index.html` is generated from `page/index.html`. |
| `docs/data/` | All data files, plus `manifest.json` listing each source and when it last changed. |
| `docs/assets/` | Runtime, theme and the charting library (d3), all bundled so the site loads nothing from other servers except web fonts. |
| `scripts/` | Python scripts that rebuild the data from NOAA, NASA and FAO, check it, and rebuild the page. |
| `.github/workflows/refresh.yml` | The schedule that runs those scripts automatically. |

## Publish it on GitHub Pages (free), step by step

1. **Create a GitHub account** for EPA if there isn't one (an organisation account is best, for example `epa-liberia`), at https://github.com.
2. **Create a new repository**, for example `elnino-platform`, set to **Public** (GitHub Pages is free for public repositories).
3. **Upload the contents of this folder** to the repository: on the repository page choose *Add file → Upload files*, drag in everything (including the hidden `.github` folder), and commit. Uploading through the website can skip hidden folders; if `.github/workflows/refresh.yml` is missing afterwards, create it with *Add file → Create new file* and paste its contents.
4. **Turn on the website:** *Settings → Pages*, Source: *Deploy from a branch*, Branch: `main`, Folder: `/docs`, Save. After a minute the site is live at `https://<account>.github.io/elnino-platform/`.
5. **Turn on automatic updates:** *Settings → Actions → General*, allow actions, and under *Workflow permissions* choose **Read and write permissions**. Then open the *Actions* tab, choose *Refresh data*, and press *Run workflow* once with `all` to check it works (it takes about 5 minutes).

After that, the schedule runs by itself:

| What | When (Monrovia time) | Source |
| --- | --- | --- |
| Ocean temperature and rainfall maps | Daily 05:35 | NASA GIBS (GHRSST MUR, GPM IMERG) |
| El Niño indices, outlook and status | Daily 17:55 | NOAA Climate Prediction Center |
| County drought data and 1 km crop stress map | Mondays 07:23 | FAO GIEWS ASIS |

Each run checks the data before saving it. If a source changes its format, the run stops without overwriting anything, and GitHub emails the repository owner.

## Use an EPA web address (optional)

To serve the site at, for example, `elnino.epa.gov.lr`: in *Settings → Pages → Custom domain* enter the address, and ask whoever manages EPA's domain to add a `CNAME` record pointing `elnino` to `<account>.github.io`. Tick *Enforce HTTPS* once it is offered.

## Hosting somewhere else

The `docs` folder is a plain static website: copy it to any web server (for example EPA's own) and it works. To keep the data updating there, run the same commands on a schedule (for example with cron) on a machine with Python 3 and `pip install pillow numpy rasterio affine`:

```
python3 scripts/build_ocean.py docs/data 30          # daily
python3 scripts/build_noaa.py docs/data              # daily
python3 scripts/build_fao.py docs/data               # weekly
python3 scripts/build_fao_map.py docs/data docs/data 12
python3 scripts/update_manifest.py
python3 scripts/build_site.py
```

## Changing the page

Edit `page/index.html`, then run `python3 scripts/build_site.py` to regenerate `docs/index.html`. When Claude makes a change, it updates both this file and the Claude dashboard, so the two stay identical.

## Sources and licences

NOAA and NASA data are US Government works and free to reuse. FAO ASIS data are published by FAO GIEWS. County, district and clan boundaries are LISGIS 2022 (15 counties, 160 districts, 902 named clans), built by `scripts/build_bounds2022.py`, which also writes the 2022 census population by district (see `scripts/data/census2022_districts.csv`). Flood figures: `scripts/build_flood.py` then `scripts/build_pop2022.py`. Average wind: `scripts/build_wind.py`.py`. Wind data: Global Wind Atlas 3 (DTU, World Bank/ESMAP), CC BY 4.0. Windstorm events: NDMA (via allAfrica), IFRC DREF MDRLR010, allAfrica. Flood exposure: JRC Copernicus Global River Flood Hazard Maps v2.1 (free to reuse) with WorldPop 2025 constrained population (CC BY 4.0), built once by `scripts/build_flood.py`. Heat levels are EPA's reading of NOAA/FEWS NET and AGRHYMET bulletins. None of the levels is an official LiMet or NDMA warning.
