"""Turn the raw OSM download into GeoJSON for the web app, adding run/lift
stats (length, vertical, slope) sampled from the 1m DEM.

    python -m pipeline.build_geo
"""

import json
import math

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform

from . import config

DIFFICULTY = {
    "novice": "green", "easy": "green",
    "intermediate": "blue",
    "advanced": "black",
    "expert": "double-black", "extreme": "double-black",
    "freeride": "freeride",
}
SAMPLE_STEP_M = 5.0
MAX_SLOPE_WINDOW_M = 30.0


def to_coords(geom):
    return [[round(p["lon"], 7), round(p["lat"], 7)] for p in geom]


def profile(dem, coords):
    """Densified (distance, elevation) profile along a lon/lat polyline."""
    xs, ys = warp_transform("EPSG:4326", config.UTM_CRS, [c[0] for c in coords], [c[1] for c in coords])
    pts = []
    for i in range(len(xs) - 1):
        seg = math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i])
        n = max(1, int(seg // SAMPLE_STEP_M))
        for k in range(n):
            t = k / n
            pts.append((xs[i] + t * (xs[i + 1] - xs[i]), ys[i] + t * (ys[i + 1] - ys[i])))
    pts.append((xs[-1], ys[-1]))
    elev = np.array([v[0] for v in dem.sample(pts)], np.float64)
    elev[elev == dem.nodata] = np.nan
    p = np.array(pts)
    dist = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    return dist, elev


def line_stats(dem, coords):
    dist, elev = profile(dem, coords)
    if np.isnan(elev).all() or dist[-1] < 1:
        return {}
    top, bottom = np.nanmax(elev), np.nanmin(elev)
    # Steepest pitch: rise over run across any ~30 m stretch of the line.
    k = max(1, int(MAX_SLOPE_WINDOW_M / SAMPLE_STEP_M))
    max_pitch = 0.0
    if len(dist) > k:
        dz = np.abs(elev[k:] - elev[:-k])
        dd = dist[k:] - dist[:-k]
        ok = (dd > 0) & ~np.isnan(dz)
        if ok.any():
            max_pitch = float(np.degrees(np.arctan(np.max(dz[ok] / dd[ok]))))
    horiz = dist[-1]
    return {
        "length_m": round(float(horiz)),
        "top_m": round(float(top)),
        "bottom_m": round(float(bottom)),
        "vertical_m": round(float(top - bottom)),
        "avg_pitch_deg": round(float(np.degrees(np.arctan((top - bottom) / horiz))), 1),
        "max_pitch_deg": round(max_pitch, 1),
    }


def feature(geom_type, coords, props):
    return {"type": "Feature", "geometry": {"type": geom_type, "coordinates": coords}, "properties": props}


def main():
    elements = json.loads(config.OSM_PATH.read_text())["elements"]
    runs, lifts, areas, stations = [], [], [], []

    with rasterio.open(config.DEM_PATH) as dem:
        for e in elements:
            t = e.get("tags", {})
            base = {"id": f"{e['type']}/{e['id']}", "name": t.get("name") or t.get("piste:name")}

            if e["type"] == "node" and t.get("aerialway") == "station":
                stations.append(feature("Point", [e["lon"], e["lat"]], base))
                continue
            if e["type"] != "way":
                continue
            coords = to_coords(e["geometry"])
            closed = len(coords) > 3 and coords[0] == coords[-1]

            if "piste:type" in t:
                props = base | {
                    "piste_type": t["piste:type"],
                    "difficulty": DIFFICULTY.get(t.get("piste:difficulty"), "unknown"),
                    "osm_difficulty": t.get("piste:difficulty"),
                    "grooming": t.get("piste:grooming"),
                    "gladed": t.get("gladed") == "yes",
                }
                if closed and t.get("area") == "yes":
                    areas.append(feature("Polygon", [coords], props))
                else:
                    runs.append(feature("LineString", coords, props | line_stats(dem, coords)))
            elif "aerialway" in t and not closed and t["aerialway"] != "station":
                stats = line_stats(dem, coords)
                lifts.append(feature("LineString", coords, base | {
                    "lift_type": t["aerialway"],
                    "occupancy": t.get("aerialway:occupancy"),
                    "duration_min": t.get("aerialway:duration"),
                    "bubble": t.get("aerialway:bubble") == "yes",
                    "ref": t.get("ref"),
                    "length_m": stats.get("length_m"),
                    "vertical_m": stats.get("vertical_m"),
                    "top_m": stats.get("top_m"),
                    "bottom_m": stats.get("bottom_m"),
                }))

    config.GEO.mkdir(parents=True, exist_ok=True)
    for name, feats in [("runs", runs), ("lifts", lifts), ("areas", areas), ("stations", stations)]:
        (config.GEO / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        print(f"wrote {name}.geojson ({len(feats)} features)")


if __name__ == "__main__":
    main()
