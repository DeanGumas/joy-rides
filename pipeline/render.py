"""Per-pixel rendering: slope-angle shading and synthetic "winter" imagery."""

import numpy as np
from scipy import ndimage

# Avalanche slope-angle classes (degrees) -> RGB. Mirrored in web/app.js legend.
SLOPE_CLASSES = [
    (27, 30, (255, 225, 77)),
    (30, 35, (255, 154, 46)),
    (35, 40, (242, 74, 43)),
    (40, 45, (196, 22, 107)),
    (45, 50, (123, 31, 162)),
    (50, 90, (45, 42, 140)),
]


def gradients(dem, res_m, sigma_px):
    z = ndimage.gaussian_filter(dem, sigma_px) if sigma_px else dem
    dzdy, dzdx = np.gradient(z, res_m)
    return dzdx, -dzdy  # +y is north (rows go south)


def slope_deg(dem, res_m, sigma_px):
    dx, dy = gradients(dem, res_m, sigma_px)
    return np.degrees(np.arctan(np.hypot(dx, dy)))


def hillshade(dem, res_m, sigma_px=1.0, azimuth=225.0, altitude=35.0):
    """Lambertian shading in [0, 1] for a sun at azimuth (deg from north) / altitude."""
    dx, dy = gradients(dem, res_m, sigma_px)
    az, alt = np.radians(azimuth), np.radians(altitude)
    sun = np.array([np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)])
    norm = np.sqrt(dx * dx + dy * dy + 1)
    shade = (-dx * sun[0] - dy * sun[1] + sun[2]) / norm
    return np.clip(shade, 0, 1)


def slope_rgba(slope, valid):
    out = np.zeros(slope.shape + (4,), np.uint8)
    for lo, hi, rgb in SLOPE_CLASSES:
        m = (slope >= lo) & (slope < hi) & valid
        out[m, :3] = rgb
        out[m, 3] = 255
    return out


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def winterize(naip, dem, res_m, valid):
    """Fake mid-winter snow cover from summer NAIP (RGB+NIR) and the 1m DEM.

    Open ground becomes snow shaded by the terrain; conifers (high NDVI, dark)
    stay as dark trees; cliffs too steep to hold snow show rock; frozen lakes
    become flat snow.
    """
    rgb = naip[:3].astype(np.float32) / 255.0
    nir = naip[3].astype(np.float32) / 255.0
    r, g, b = rgb
    lum = 0.30 * r + 0.59 * g + 0.11 * b
    ndvi = (nir - r) / (nir + r + 1e-4)

    # Conifer canopy: green-ish in NIR and dark in visible light.
    tree = smoothstep(ndvi, 0.10, 0.28) * (1 - smoothstep(lum, 0.22, 0.40))
    tree = ndimage.gaussian_filter(tree, 0.7)
    # Water / lake ice: negative NDVI and fairly flat.
    slope = slope_deg(dem, res_m, 2.0)
    water = smoothstep(-ndvi, 0.02, 0.12) * (1 - smoothstep(slope, 4, 10))
    # Terrain too steep to hold much snow.
    rock = smoothstep(slope, 48, 62)

    # Snow color: blue-grey in shadow, near-white in sun.
    shade = hillshade(dem, res_m, 1.5)
    sun_c = np.array([0.97, 0.98, 1.00], np.float32)[:, None, None]
    shadow_c = np.array([0.52, 0.60, 0.74], np.float32)[:, None, None]
    snow = shadow_c + (sun_c - shadow_c) * shade[None] ** 0.8
    # Keep a little of the photo's fine texture (rocks, stumps, tracks).
    detail = lum - ndimage.gaussian_filter(lum, 3.0)
    detail = np.where(water > 0.5, 0, detail)
    snow = snow * (1 + 0.9 * detail)[None]

    # Trees: darkened summer color with a light dusting of snow.
    trees = rgb * 0.70 + 0.10 * snow
    # Exposed rock: darkened photo, partly snow-plastered.
    rocks = rgb * 0.75 * (0.6 + 0.4 * shade[None]) * 0.65 + snow * 0.35

    out = snow * (1 - tree)[None] * (1 - rock)[None] + rocks * (1 - tree)[None] * rock[None] + trees * tree[None]
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    return np.concatenate([out, alpha[None]], 0)
