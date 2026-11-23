"""Download the USGS 3DEP 1m bare-earth DEM for the area (public domain).

    python -m pipeline.fetch_dem
"""

import requests

from . import config
from .mosaic import Resampling, build_mosaic

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"


def find_sources():
    w, s, e, n = config.bbox()
    r = requests.get(
        TNM_API,
        params={
            "datasets": "Digital Elevation Model (DEM) 1 meter",
            "bbox": f"{w},{s},{e},{n}",
            "prodFormats": "GeoTIFF",
            "max": 200,
            "outputFormat": "JSON",
        },
        timeout=60,
    )
    r.raise_for_status()
    items = [i for i in r.json()["items"] if i.get("downloadURL", "").endswith(".tif")]
    # Oldest first so the newest survey wins where projects overlap.
    items.sort(key=lambda i: i.get("publicationDate") or "")
    for i in items:
        print(f"  {i['title']}  ({i.get('publicationDate')})")
    return [i["downloadURL"] for i in items]


def main():
    sources = find_sources()
    if not sources:
        raise SystemExit("No 1m DEM tiles found for this area")
    build_mosaic(
        sources, config.DEM_PATH,
        res=1.0, count=1, dtype="float32", nodata=-9999.0,
        resampling=Resampling.bilinear, predictor=3,
    )


if __name__ == "__main__":
    main()
