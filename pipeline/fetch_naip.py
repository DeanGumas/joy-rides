"""Download 4-band (RGB + near-infrared) NAIP aerial imagery for the area.

Uses Microsoft Planetary Computer's free NAIP mirror (no account needed; the
read token comes from their public token endpoint).

    python -m pipeline.fetch_naip
"""

import requests

from . import config
from .mosaic import Resampling, build_mosaic

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"


def find_sources():
    r = requests.post(
        STAC_SEARCH,
        json={"collections": ["naip"], "bbox": list(config.bbox()), "limit": 500},
        timeout=60,
    )
    r.raise_for_status()
    feats = r.json()["features"]
    latest = max(f["properties"]["naip:year"] for f in feats)
    feats = [f for f in feats if f["properties"]["naip:year"] == latest]
    feats.sort(key=lambda f: f["properties"]["datetime"])
    print(f"  NAIP {latest}: {len(feats)} quarter-quads")
    token = requests.get(TOKEN_URL, timeout=30).json()["token"]
    return latest, [f"{f['assets']['image']['href']}?{token}" for f in feats]


def main():
    year, sources = find_sources()
    build_mosaic(
        sources, config.NAIP_PATH, tags={"NAIP_YEAR": str(year)},
        res=0.6, count=4, dtype="uint8", nodata=0,
        resampling=Resampling.bilinear,
    )


if __name__ == "__main__":
    main()
