"""Joy Rides web server.

    .venv/bin/uvicorn server.app:app --reload --port 8000

Serves the static frontend (web/), the pre-rendered raster tiles and the
GeoJSON produced by the pipeline. Terrain comes straight from Mapterhorn in
the browser, so it isn't proxied here.
"""

import math
import threading
from pathlib import Path

import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window
from starlette.types import Scope

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class CachedStatic(StaticFiles):
    """StaticFiles with a Cache-Control header (tiles never change in place)."""

    def __init__(self, *args, max_age: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_age = max_age

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = f"public, max-age={self.max_age}"
        return response


app = FastAPI(title="Joy Rides")


@app.get("/api/health")
def health():
    return {"ok": True, "tiles": (DATA / "tiles" / "meta.json").exists(), "geo": (DATA / "geo" / "runs.geojson").exists()}


class DemReader:
    """Point queries against the 1m DEM: elevation, slope and aspect."""

    ASPECTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    def __init__(self, path: Path):
        self.path = path
        self.ds = None
        self.lock = threading.Lock()

    def query(self, lon: float, lat: float, radius: int = 3):
        with self.lock:
            if self.ds is None:
                if not self.path.exists():
                    return None
                self.ds = rasterio.open(self.path)
            ds = self.ds
            (x,), (y,) = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
            row, col = ds.index(x, y)
            win = Window(col - radius, row - radius, 2 * radius + 1, 2 * radius + 1)
            a = ds.read(1, window=win, boundless=True, fill_value=ds.nodata).astype(np.float64)
        if (a == ds.nodata).any():
            return None
        # Plane fit over the (2r+1)^2 window ~ slope over a ~7 m footprint.
        res = ds.res[0]
        dzdy, dzdx = np.gradient(a, res)
        gx, gy = dzdx.mean(), -dzdy.mean()  # +y north
        slope = math.degrees(math.atan(math.hypot(gx, gy)))
        aspect_deg = (math.degrees(math.atan2(-gx, -gy)) + 360) % 360  # direction the slope faces
        return {
            "elevation_m": round(float(a[radius, radius]), 1),
            "slope_deg": round(slope),
            "aspect_deg": round(aspect_deg),
            "aspect": self.ASPECTS[int((aspect_deg + 22.5) // 45) % 8],
        }


dem = DemReader(DATA / "raw" / "dem_1m.tif")


@app.get("/api/point")
def point(lon: float, lat: float):
    result = dem.query(lon, lat)
    if result is None:
        raise HTTPException(404, "outside DEM coverage")
    return result


(DATA / "tiles").mkdir(parents=True, exist_ok=True)
(DATA / "geo").mkdir(parents=True, exist_ok=True)
app.mount("/tiles", CachedStatic(directory=DATA / "tiles", max_age=3600), name="tiles")
app.mount("/geo", CachedStatic(directory=DATA / "geo", max_age=60), name="geo")
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
