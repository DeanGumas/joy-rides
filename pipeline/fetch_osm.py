"""Download ski runs, lifts and stations from OpenStreetMap (ODbL).

    python -m pipeline.fetch_osm
"""

import json

import requests

from . import config

OVERPASS = "https://overpass-api.de/api/interpreter"


def main():
    w, s, e, n = config.bbox()
    bb = f"{s},{w},{n},{e}"
    query = f"""
    [out:json][timeout:120];
    (
      way["piste:type"]({bb});
      relation["piste:type"]({bb});
      way["aerialway"]({bb});
      node["aerialway"="station"]({bb});
      way["landuse"="winter_sports"]({bb});
      relation["landuse"="winter_sports"]({bb});
    );
    out geom;
    """
    r = requests.post(OVERPASS, data={"data": query}, headers={"User-Agent": "joy-rides-pipeline"}, timeout=180)
    r.raise_for_status()
    data = r.json()
    config.OSM_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.OSM_PATH.write_text(json.dumps(data))
    print(f"wrote {config.OSM_PATH} ({len(data['elements'])} elements)")


if __name__ == "__main__":
    main()
