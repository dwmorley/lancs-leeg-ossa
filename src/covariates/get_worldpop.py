"""Helpers to fetch and process WorldPop population rasters for AOIs."""

import numpy as np
import requests
from rasterio.io import MemoryFile

from src.utils.bounding_box import BoundingBox
from src.utils.iso3 import get_iso3_codes


def get_worldpop_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    year: int,
    adjusted: bool,
) -> np.ndarray:
    """Sample WorldPop population density at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Bounding box used to determine which country tiles to fetch.
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    year : int
        Year between 2000 and 2020.
    adjusted : bool
        Whether to fetch UN-adjusted (True) or unadjusted (False) rasters.

    Returns
    -------
    np.ndarray
        Population values at each point (NaN where no data).
    """
    adjusted_urls = {
        True: lambda year, iso3: (
            f"https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/{year}/{iso3}/"
            f"{iso3.lower()}_ppp_{year}_1km_Aggregated_UNadj.tif"
        ),
        False: lambda year, iso3: (
            f"https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/{year}/{iso3}/"
            f"{iso3.lower()}_ppp_{year}_1km_Aggregated.tif"
        ),
    }

    # A compromise: Ensure year is within valid range
    if year < 2000:
        year = 2000
    elif year > 2020:
        year = 2020

    iso3_codes = get_iso3_codes(bbox)
    if not iso3_codes:
        raise ValueError("No ISO3 codes found for the given bounding box")

    values = np.full(len(xs), np.nan)

    for iso3 in iso3_codes:
        url = adjusted_urls[adjusted](year, iso3)
        response = requests.get(url, timeout=30)
        if response.status_code == 404:
            continue

        with MemoryFile(response.content) as memfile:
            with memfile.open() as src:
                left, bottom, right, top = src.bounds
                in_tile = (xs >= left) & (xs <= right) & (ys >= bottom) & (ys <= top)
                if not in_tile.any():
                    continue

                coords = list(zip(xs[in_tile], ys[in_tile]))
                sampled = np.array([v[0] for v in src.sample(coords)], dtype=float)
                sampled[sampled == -99999] = np.nan

                mask = in_tile.nonzero()[0]
                overwrite = np.isnan(values[mask])
                values[mask] = np.where(overwrite, sampled, values[mask])

    return values
