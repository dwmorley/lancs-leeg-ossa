"""Helpers to fetch and process digital elevation model (DEM) rasters for AOIs."""

import gc
import threading

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer

from src.utils.bounding_box import BoundingBox

# Semaphore to limit concurrent remote file operations (prevent file descriptor exhaustion)
_remote_file_semaphore = threading.Semaphore(3)


def get_dem_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    res: int = 30,
) -> np.ndarray:
    """Sample Copernicus DEM at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Bounding box used to search for tiles.
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    res : int, optional
        DEM resolution in metres (30 or 90).

    Returns
    -------
    np.ndarray
        Elevation values at each point (NaN where no data).
    """
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=[f"cop-dem-glo-{res}"],
        bbox=bbox.to_list(),
    )
    items = list(search.items())

    values = np.full(len(xs), np.nan)

    try:
        for item in items:
            href = item.assets["data"].href
            # Use semaphore to limit concurrent remote file operations
            with _remote_file_semaphore:
                with rasterio.open(href) as src:
                    tile_crs = src.crs
                    transformer = Transformer.from_crs("EPSG:4326", tile_crs, always_xy=True)
                    tile_xs, tile_ys = transformer.transform(xs, ys)

                    left, bottom, right, top = src.bounds
                    in_tile = (
                        (tile_xs >= left)
                        & (tile_xs <= right)
                        & (tile_ys >= bottom)
                        & (tile_ys <= top)
                    )
                    if not in_tile.any():
                        continue

                    coords = list(zip(tile_xs[in_tile], tile_ys[in_tile]))
                    sampled = np.array([v[0] for v in src.sample(coords)], dtype=float)
                    # nodata is typically -32767 or large negative
                    sampled[sampled <= -9999] = np.nan

                    mask = in_tile.nonzero()[0]
                    overwrite = np.isnan(values[mask])
                    values[mask] = np.where(overwrite, sampled, values[mask])
    finally:
        # Explicitly trigger garbage collection to free file descriptors
        gc.collect()

    return values
