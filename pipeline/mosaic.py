"""Crop remote cloud-optimized GeoTIFFs to the area and mosaic them locally.

Both USGS 1m DEMs and NAIP quads are COGs, so GDAL only fetches the byte
ranges inside the area instead of the whole files.
"""

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from . import config

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
}


def area_bounds_utm(margin_m=100.0, res=1.0):
    left, bottom, right, top = transform_bounds("EPSG:4326", config.UTM_CRS, *config.bbox(), densify_pts=50)
    snap = lambda v, f: f(v / res) * res
    return (
        snap(left - margin_m, math.floor),
        snap(bottom - margin_m, math.floor),
        snap(right + margin_m, math.ceil),
        snap(top + margin_m, math.ceil),
    )


def build_mosaic(sources, out_path, *, res, count, dtype, nodata, resampling, chunk=4096, workers=6, predictor=2, tags=None):
    """Resample `sources` (URLs/paths, later ones win on overlap) onto one UTM grid."""
    left, bottom, right, top = area_bounds_utm(res=res)
    width = int(round((right - left) / res))
    height = int(round((top - bottom) / res))
    transform = from_origin(left, top, res, res)
    profile = dict(
        driver="GTiff", width=width, height=height, count=count, dtype=dtype, nodata=nodata,
        crs=config.UTM_CRS, transform=transform, tiled=True, blockxsize=512, blockysize=512,
        compress="deflate", predictor=predictor, BIGTIFF="IF_SAFER",
    )
    print(f"mosaic {out_path.name}: {width}x{height} px @ {res} m from {len(sources)} sources")

    with rasterio.Env(**GDAL_ENV):
        src_bounds = []
        for s in sources:
            with rasterio.open(s) as ds:
                src_bounds.append(ds.bounds)

    windows = [
        Window(c, r, min(chunk, width - c), min(chunk, height - r))
        for r in range(0, height, chunk)
        for c in range(0, width, chunk)
    ]

    def render(win):
        wt = rasterio.windows.transform(win, transform)
        wl, wb, wr, wtop = rasterio.windows.bounds(win, transform)
        dst = np.full((count, int(win.height), int(win.width)), nodata, dtype=dtype)
        with rasterio.Env(**GDAL_ENV):
            for s, b in zip(sources, src_bounds):
                if b.left >= wr or b.right <= wl or b.bottom >= wtop or b.top <= wb:
                    continue
                with rasterio.open(s) as ds:
                    m = 4 * ds.res[0]
                    sw = from_bounds(wl - m, wb - m, wr + m, wtop + m, ds.transform)
                    sw = sw.intersection(Window(0, 0, ds.width, ds.height)).round_offsets().round_lengths()
                    data = ds.read(window=sw)
                    reproject(
                        data, dst,
                        src_transform=ds.window_transform(sw), src_crs=ds.crs, src_nodata=ds.nodata if ds.nodata is not None else nodata,
                        dst_transform=wt, dst_crs=config.UTM_CRS, dst_nodata=nodata,
                        init_dest_nodata=False, resampling=resampling,
                    )
        return win, dst

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".partial.tif")
    with rasterio.open(tmp, "w", **profile) as out, ThreadPoolExecutor(workers) as pool:
        if tags:
            out.update_tags(**tags)
        futures = [pool.submit(render, w) for w in windows]
        for i, f in enumerate(as_completed(futures), 1):
            win, dst = f.result()
            out.write(dst, window=win)
            print(f"  chunk {i}/{len(windows)}", flush=True)
    os.replace(tmp, out_path)
    print(f"wrote {out_path}")


__all__ = ["build_mosaic", "Resampling", "area_bounds_utm"]
