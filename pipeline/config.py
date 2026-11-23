"""Shared settings for the data pipeline.

The area of interest is a lon/lat box. Everything (downloads, tiles, run
stats) is clipped to it, so growing coverage later means editing AREA and
re-running the pipeline.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
TILES = DATA / "tiles"
GEO = DATA / "geo"

# Mammoth Mountain plus nearby sidecountry/backcountry: the Sherwins,
# Lakes Basin / Mammoth Crest, Punta Bardini, San Joaquin Ridge.
AREA = {
    "name": "Mammoth",
    "west": -119.10,
    "south": 37.56,
    "east": -118.94,
    "north": 37.70,
}

# Native CRS of both the USGS 1m DEM and NAIP here (NAD83 / UTM zone 11N).
UTM_CRS = "EPSG:26911"

DEM_PATH = RAW / "dem_1m.tif"
NAIP_PATH = RAW / "naip.tif"
OSM_PATH = RAW / "osm.json"

# Raster tile pyramid served to the browser (512px web-mercator tiles).
# z16 @ 512px is ~0.95 m/pixel on the ground at this latitude.
TILE_SIZE = 512
MAX_ZOOM = 16
MIN_ZOOM = 11
# Tiles are rendered in blocks of one z13 tile (8x8 z16 tiles) at a time.
BLOCK_ZOOM = 13

PRODUCTS = ("summer", "winter", "slope")


def bbox():
    return AREA["west"], AREA["south"], AREA["east"], AREA["north"]
