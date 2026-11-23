"""Web-mercator (EPSG:3857) XYZ tile helpers."""

import math

R = 6378137.0
ORIGIN = math.pi * R  # half the world width in mercator meters
WORLD = 2 * ORIGIN


def lonlat_to_tile(lon, lat, z):
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(math.floor(x)), int(math.floor(y))


def tile_bounds(z, x, y):
    """(left, bottom, right, top) in mercator meters."""
    size = WORLD / 2**z
    left = -ORIGIN + x * size
    top = ORIGIN - y * size
    return left, top - size, left + size, top


def tile_center_lat(z, x, y):
    n = 2**z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))


def tiles_in_bbox(west, south, east, north, z):
    x0, y0 = lonlat_to_tile(west, north, z)
    x1, y1 = lonlat_to_tile(east, south, z)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def pixel_size(z, tile_size):
    """Mercator meters per pixel at zoom z."""
    return WORLD / 2**z / tile_size
