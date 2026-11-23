# Joy Rides

A free, FATMAP-style 3D map of ski terrain, starting with Mammoth Mountain and the
nearby sidecountry/backcountry. Real 1 m lidar terrain, aerial imagery (summer, or a
simulated winter version), runs and lifts from OpenStreetMap, and slope-angle shading.

## Quick start

```sh
uv venv --python 3.12
uv pip install -r requirements.txt

# 1. Download source data for the area in pipeline/config.py (~2 GB, ~10 min)
.venv/bin/python -m pipeline.fetch_dem     # USGS 3DEP 1 m DEM  -> data/raw/dem_1m.tif
.venv/bin/python -m pipeline.fetch_naip    # NAIP 2022 RGB+NIR  -> data/raw/naip.tif
.venv/bin/python -m pipeline.fetch_osm     # OSM runs/lifts     -> data/raw/osm.json

# 2. Build what the web app serves
.venv/bin/python -m pipeline.build_geo     # runs/lifts GeoJSON with vertical, pitch, etc.
.venv/bin/python -m pipeline.build_tiles   # summer / winter / slope tiles (~5 min)

# 3. Run it
.venv/bin/uvicorn server.app:app --reload --port 8000
open http://localhost:8000
```

Tweak the snow look on a single block without rebuilding everything:

```sh
.venv/bin/python -m pipeline.build_tiles --preview=-119.027,37.640   # -> data/preview/*.png
```

## How it fits together

| Layer | Source | Where it's processed |
|---|---|---|
| 3D terrain | [Mapterhorn](https://mapterhorn.com) tiles, which already include USGS 3DEP 1 m lidar here | Browser, direct from Mapterhorn |
| Summer imagery | USDA NAIP 2022, 60 cm, via Microsoft Planetary Computer | `pipeline/build_tiles.py` |
| Winter imagery | NAIP + 1 m DEM: conifers detected via NDVI stay dark, open ground becomes snow shaded by the terrain, cliffs stay rock | `pipeline/render.py:winterize` |
| Slope angle | USGS 3DEP 1 m DEM, lightly smoothed | `pipeline/render.py` |
| Runs and lifts | OpenStreetMap (ODbL) via Overpass | `pipeline/build_geo.py` |
| Outside the area | USGS National Map imagery basemap | Browser |
| Cursor readout | `/api/point`: elevation, slope and aspect from the 1 m DEM | `server/app.py` |

- `pipeline/`: Python data pipeline (rasterio/numpy). Area and zoom levels are set in `pipeline/config.py`.
- `server/`: FastAPI app that serves `web/`, `data/tiles`, `data/geo` and `/api/*`.
- `web/`: Preact + HTM + MapLibre GL, loaded as ES modules from a CDN. There's no build step.

## Attribution

Terrain: Mapterhorn / USGS 3DEP (public domain). Imagery: USDA NAIP (public domain), USGS
The National Map. Runs and lifts: © OpenStreetMap contributors, ODbL.

Slope shading and simulated snow are visual aids only. They are not avalanche information. Check the
[Eastern Sierra Avalanche Center](https://www.esavalanche.org) before heading out.
