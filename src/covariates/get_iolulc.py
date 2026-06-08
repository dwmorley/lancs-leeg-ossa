"""Fetch and prepare land use / land cover (LULC) covariates for an AOI."""

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


def get_iolulc_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    year: int = 2023,
) -> np.ndarray:
    """Return land use/land cover values for points in the AOI and year.

    Impact Observatory, Microsoft, and Esri. (2023). Global Land Use Land Cover (LULC) Dataset, 10m Resolution (2017-2023).

    Parameters
    ----------
    bbox : BoundingBox
        Bounding box to fetch the raster for.
    xs : np.ndarray
        Array of x coordinates (longitude) of the points.
    ys : np.ndarray
        Array of y coordinates (latitude) of the points.
    year : int, optional
        Year between 2017 and 2023 inclusive.

    Returns
    -------
    np.ndarray
        LULC values at the specified points, NaN where data is not available.
    """
    if not (2017 <= year <= 2023):
        raise ValueError("Year must be between 2017 and 2023.")

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=["io-lulc-annual-v02"],
        bbox=bbox.to_list(),
        datetime=str(year),
    )
    items = [item for item in search.items() if int(item.id.split("-")[1]) == year]

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

                    # Mask to points within tile bounds
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
                    # sample() does a single batched COG read — only touches
                    # the blocks your points fall in
                    sampled = np.array([v[0] for v in src.sample(coords)])

                    raw = sampled.astype(float)
                    raw[np.isin(raw, [0, 1])] = np.nan

                    mask = in_tile.nonzero()[0]
                    overwrite = np.isnan(values[mask])
                    values[mask] = np.where(overwrite, raw, values[mask])
    finally:
        # Explicitly trigger garbage collection to free file descriptors
        gc.collect()

    return values


if __name__ == "__main__":
    # a = get_iolulc(
    #     # bbox=BoundingBox([-5, 31.0, 8.2968, 32.0]),
    #     bbox=BoundingBox([1.5, 6.0, 2.1, 7.0]),
    #     year=2020,
    # )
    #
    # import pandas as pd

    bbox = BoundingBox([1.5, 6.0, 2.1, 7.0])

    xy = bbox.sampling_grid(500)

    x = xy[:, 0]
    y = xy[:, 1]

    res = get_iolulc_points(bbox, x, y)
