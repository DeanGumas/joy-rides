"""Render web-mercator raster tiles: summer imagery, synthetic winter imagery,
and slope-angle shading.

    python -m pipeline.build_tiles                 # full area
    python -m pipeline.build_tiles --preview -119.027,37.651   # one block -> data/preview/
"""

import argparse
import json
import math
import shutil
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from . import config, render
from .tilemath import lonlat_to_tile, pixel_size, tile_bounds, tile_center_lat, tiles_in_bbox

PAD = 24  # extra pixels around each block so slopes/shading have neighbors
WEBP_QUALITY = {"summer": 82, "winter": 82, "slope": 90}


def read_block(bz, bx, by):
    res = pixel_size(config.MAX_ZOOM, config.TILE_SIZE)
    n = config.TILE_SIZE * 2 ** (config.MAX_ZOOM - bz)
    left, _, _, top = tile_bounds(bz, bx, by)
    transform = from_origin(left - PAD * res, top + PAD * res, res, res)
    shape = (n + 2 * PAD, n + 2 * PAD)

    dem = np.full(shape, np.nan, np.float32)
    naip = np.zeros((4,) + shape, np.uint8)
    with rasterio.open(config.DEM_PATH) as ds:
        reproject(rasterio.band(ds, 1), dem, dst_transform=transform, dst_crs="EPSG:3857",
                  src_nodata=ds.nodata, dst_nodata=np.nan, resampling=Resampling.bilinear)
    with rasterio.open(config.NAIP_PATH) as ds:
        reproject(rasterio.band(ds, [1, 2, 3, 4]), naip, dst_transform=transform, dst_crs="EPSG:3857",
                  src_nodata=0, dst_nodata=0, resampling=Resampling.bilinear)

    ground_res = res * math.cos(math.radians(tile_center_lat(bz, bx, by)))
    return dem, naip, ground_res


def render_block(bz, bx, by):
    dem, naip, res_m = read_block(bz, bx, by)
    valid_dem = ~np.isnan(dem)
    if not valid_dem.any():
        return {}
    dem = np.where(valid_dem, dem, np.nanmean(dem))
    valid_img = naip.any(0) & valid_dem

    summer = np.concatenate([naip[:3], np.where(valid_img, 255, 0).astype(np.uint8)[None]], 0)
    winter = render.winterize(naip, dem, res_m, valid_img)
    slope = render.slope_rgba(render.slope_deg(dem, res_m, 2.5), valid_dem).transpose(2, 0, 1)

    crop = (slice(None), slice(PAD, -PAD), slice(PAD, -PAD))
    return {"summer": summer[crop], "winter": winter[crop], "slope": slope[crop]}


def save_tile(product, z, x, y, img):
    path = config.TILES / product / str(z) / str(x) / f"{y}.webp"
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "WEBP", quality=WEBP_QUALITY[product], method=4)


def write_block(block):
    bz, bx, by = block
    products = render_block(bz, bx, by)
    k = 2 ** (config.MAX_ZOOM - bz)
    s = config.TILE_SIZE
    written = 0
    for product, arr in products.items():
        for i in range(k):
            for j in range(k):
                tile = arr[:, j * s:(j + 1) * s, i * s:(i + 1) * s]
                if not tile[3].any():
                    continue
                save_tile(product, config.MAX_ZOOM, bx * k + i, by * k + j,
                          Image.fromarray(np.ascontiguousarray(tile.transpose(1, 2, 0)), "RGBA"))
                written += 1
    print(f"  block {bz}/{bx}/{by}: {written} tiles", flush=True)
    return written


def build_overviews(product):
    root = config.TILES / product
    for z in range(config.MAX_ZOOM - 1, config.MIN_ZOOM - 1, -1):
        children = {(int(p.parent.name), int(p.stem)) for p in (root / str(z + 1)).glob("*/*.webp")}
        parents = {(x // 2, y // 2) for x, y in children}
        s = config.TILE_SIZE
        for px, py in parents:
            canvas = Image.new("RGBA", (2 * s, 2 * s), (0, 0, 0, 0))
            for dx in (0, 1):
                for dy in (0, 1):
                    c = (2 * px + dx, 2 * py + dy)
                    if c in children:
                        canvas.paste(Image.open(root / str(z + 1) / str(c[0]) / f"{c[1]}.webp").convert("RGBA"), (dx * s, dy * s))
            small = canvas.convert("RGBa").resize((s, s), Image.Resampling.BOX).convert("RGBA")
            save_tile(product, z, px, py, small)
        print(f"  {product} z{z}: {len(parents)} tiles", flush=True)


def write_meta():
    with rasterio.open(config.NAIP_PATH) as ds:
        tags = ds.tags()
    meta = {
        "name": config.AREA["name"],
        "bounds": list(config.bbox()),
        "minzoom": config.MIN_ZOOM,
        "maxzoom": config.MAX_ZOOM,
        "tileSize": config.TILE_SIZE,
        "products": list(config.PRODUCTS),
        "slopeClasses": [{"min": lo, "max": hi, "color": "#%02x%02x%02x" % rgb} for lo, hi, rgb in render.SLOPE_CLASSES],
        "naip": tags.get("NAIP_YEAR"),
    }
    (config.TILES / "meta.json").write_text(json.dumps(meta, indent=2))


def preview(lon, lat):
    bx, by = lonlat_to_tile(lon, lat, config.BLOCK_ZOOM)
    products = render_block(config.BLOCK_ZOOM, bx, by)
    out = config.DATA / "preview"
    out.mkdir(parents=True, exist_ok=True)
    for name, arr in products.items():
        img = Image.fromarray(np.ascontiguousarray(arr.transpose(1, 2, 0)), "RGBA")
        img.save(out / f"{name}_full.png")
        img.resize((1024, 1024), Image.Resampling.BOX).save(out / f"{name}.png")
    print(f"wrote previews for block {config.BLOCK_ZOOM}/{bx}/{by} to {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="lon,lat: render just the block containing this point")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    if args.preview:
        preview(*map(float, args.preview.split(",")))
        return

    for p in config.PRODUCTS:
        shutil.rmtree(config.TILES / p, ignore_errors=True)
    blocks = [(config.BLOCK_ZOOM, x, y) for x, y in tiles_in_bbox(*config.bbox(), config.BLOCK_ZOOM)]
    print(f"rendering {len(blocks)} blocks at z{config.MAX_ZOOM}")
    with ProcessPoolExecutor(args.workers) as pool:
        total = sum(pool.map(write_block, blocks))
    print(f"z{config.MAX_ZOOM}: {total} tiles")
    for p in config.PRODUCTS:
        build_overviews(p)
    write_meta()
    print("done")


if __name__ == "__main__":
    main()
