"""Helpers to fetch and process WorldPop population rasters for AOIs."""

import numpy as np
import requests
import rioxarray as rxr
import xarray as xr  # noqa: F401
from rasterio.io import MemoryFile
from rioxarray.merge import merge_arrays

from src.utils.bounding_box import BoundingBox
from src.utils.iso3 import get_iso3_codes


def get_worldpop(
    bbox: BoundingBox,
    year: int,
    adjusted: bool,
) -> xr.DataArray:
    """Download and combine WorldPop rasters for the given AOI and year.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip WorldPop rasters to.
    year : int
        Year between 2000 and 2020.
    adjusted : bool
        Whether to fetch adjusted (UNadj) or unadjusted (adj) population rasters

    Returns
    -------
    xarray.DataArray
        Clipped WorldPop raster for the AOI.
    """
    adjusted_urls = {
        True: lambda year, iso3: f"https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/{year}/{iso3}/{iso3.lower()}_ppp_{year}_1km_Aggregated_UNadj.tif",
        False: lambda year, iso3: f"https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/{year}/{iso3}/{iso3.lower()}_ppp_{year}_1km_Aggregated.tif",
    }

    if year < 2000 or year > 2020:
        raise ValueError("Year must be between 2000 and 2020")

    iso3_codes = get_iso3_codes(bbox)

    if not iso3_codes:
        raise ValueError("No ISO3 codes found for the given bounding box")

    rasters = []
    for iso3 in iso3_codes:
        url = adjusted_urls[adjusted](year, iso3)

        response = requests.get(url, timeout=30)
        if response.status_code == 404:
            print(f"DEBUG: Possibly malformed URL: {url}")

        with MemoryFile(response.content) as memfile:
            da = rxr.open_rasterio(memfile)
            da = da.where(da != -99999, np.nan)
            da.rio.write_crs("EPSG:4326", inplace=True)
            da = da.rio.clip_box(
                bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
            )
            da = da.rio.write_nodata(-9999, encoded=True)
            rasters.append(da.load())

    if len(rasters) == 1:
        merged = rasters[0]
    else:
        merged = merge_arrays(rasters, method="max", nodata=-9999)

    return merged.where(merged != -9999, np.nan)


if __name__ == "__main__":

    year = 2019
    bbox = BoundingBox([3.8644, 44.2689, 4.6865, 44.5155])

    merged = get_worldpop(bbox, year, adjusted=False)

    merged.rio.write_crs("EPSG:4326", inplace=True)
    merged.rio.to_raster("worldpop2.tif", compress="deflate", COMPRESS_LEVEL=9)
