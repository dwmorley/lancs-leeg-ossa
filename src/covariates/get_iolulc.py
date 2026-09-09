"""Fetch and prepare land use / land cover (LULC) covariates for an AOI."""

import gc
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer

from src.utils.bounding_box import BoundingBox

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent remote file operations (prevent file descriptor exhaustion)
_remote_file_semaphore = threading.Semaphore(3)

# Dedicated executor used purely to impose a wall-clock timeout on blocking
# network calls. `signal.alarm`-based timeouts only work on the main thread,
# and this function is routinely called from worker threads, so we use a
# helper thread + future.result(timeout=...) instead, which is thread-safe.
# Threads are left to finish/die on their own if they exceed the timeout
# (the underlying socket calls will eventually time out via GDAL/requests
# config below); we just stop waiting on them here.
_timeout_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="iolulc-timeout")

# Network timeouts applied to GDAL's HTTP-backed COG reads, so a stalled
# connection can't hang a worker thread forever.
_GDAL_HTTP_ENV = {
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "CPL_VSIL_CURL_USE_HEAD": "NO",
}


def _run_with_timeout(func, timeout_s: float):
    """Run a blocking callable with a wall-clock timeout, safe to call from any thread."""
    future = _timeout_executor.submit(func)
    try:
        return future.result(timeout=timeout_s)
    except FutureTimeoutError as exc:
        raise TimeoutError(f"Operation timed out after {timeout_s} seconds") from exc


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

    values = np.full(len(xs), np.nan)

    try:
        items = _search_items_with_retry(bbox, year)

        with rasterio.Env(**_GDAL_HTTP_ENV):
            for item in items:
                try:
                    _sample_item_into(item, xs, ys, values)
                except Exception as exc:  # noqa: BLE001 - never let one bad tile abort the rest
                    logger.warning(
                        "Skipping io-lulc tile %s after repeated failures: %s", item.id, exc
                    )
    except Exception as exc:  # noqa: BLE001 - this function must never crash the caller
        logger.warning("get_iolulc_points failed, returning NaNs: %s", exc)
        return np.full(len(xs), np.nan)
    finally:
        # Explicitly trigger garbage collection to free file descriptors
        gc.collect()

    return values


def _search_items_with_retry(bbox: BoundingBox, year: int, attempts: int = 2):
    """Search the STAC catalog for matching items, with a timeout and retries."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return _run_with_timeout(lambda: _search_items(bbox, year), timeout_s=45)
        except Exception as exc:  # noqa: BLE001 - retry on any transient failure
            last_exc = exc
            logger.warning("io-lulc STAC search attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(2**attempt)
    raise last_exc


def _search_items(bbox: BoundingBox, year: int):
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=["io-lulc-annual-v02"],
        bbox=bbox.to_list(),
        datetime=str(year),
    )
    return [item for item in search.items() if int(item.id.split("-")[1]) == year]


def _sample_item_into(item, xs: np.ndarray, ys: np.ndarray, values: np.ndarray, attempts: int = 2):
    """Sample a single STAC item's raster at xs/ys, writing results into `values` in place."""
    href = item.assets["data"].href

    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            # Use semaphore to limit concurrent remote file operations
            with _remote_file_semaphore:
                _run_with_timeout(
                    lambda: _sample_item(href, xs, ys, values),
                    timeout_s=30,
                )
            return
        except Exception as exc:  # noqa: BLE001 - retry on any transient failure
            last_exc = exc
            if attempt < attempts:
                time.sleep(1)
    raise last_exc


def _sample_item(href: str, xs: np.ndarray, ys: np.ndarray, values: np.ndarray) -> None:
    with rasterio.open(href) as src:
        tile_crs = src.crs

        transformer = Transformer.from_crs("EPSG:4326", tile_crs, always_xy=True)
        tile_xs, tile_ys = transformer.transform(xs, ys)

        # Mask to points within tile bounds
        left, bottom, right, top = src.bounds
        in_tile = (tile_xs >= left) & (tile_xs <= right) & (tile_ys >= bottom) & (tile_ys <= top)

        if not in_tile.any():
            return

        coords = list(zip(tile_xs[in_tile], tile_ys[in_tile]))
        # sample() does a single batched COG read — only touches
        # the blocks your points fall in
        sampled = np.array([v[0] for v in src.sample(coords)])

        raw = sampled.astype(float)
        raw[np.isin(raw, [0, 1])] = np.nan

        mask = in_tile.nonzero()[0]
        overwrite = np.isnan(values[mask])
        values[mask] = np.where(overwrite, raw, values[mask])


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
