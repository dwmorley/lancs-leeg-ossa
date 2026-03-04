"""Helpers to fetch and process WorldPop population rasters for AOIs."""

import numpy as np
import requests
import rioxarray as rxr
import xarray as xr
from rasterio.io import MemoryFile

from src.utils.bounding_box import BoundingBox
from src.utils.iso3 import get_iso3_codes


def get_worldpop(
    bbox: BoundingBox,
    year: int,
) -> xr.DataArray:
    """Download and combine WorldPop rasters for the given AOI and year.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip WorldPop rasters to.
    year : int
        Year between 2000 and 2020.

    Returns
    -------
    xarray.DataArray
        Clipped WorldPop raster for the AOI.
    """
    if year < 2000 or year > 2020:
        raise ValueError("Year must be between 2000 and 2020")

    iso3_codes = get_iso3_codes(bbox)

    if not iso3_codes:
        raise ValueError("No ISO3 codes found for the given bounding box")

    rasters = []
    for iso3 in iso3_codes:
        url = f"https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/{iso3}/{iso3.lower()}_ppp_{year}_1km_Aggregated_UNadj.tif"

        response = requests.get(url, timeout=30)

        with MemoryFile(response.content) as memfile:
            da = rxr.open_rasterio(memfile)
            da = da.where(da != -99999, np.nan)
            rasters.append(da)

    merged = xr.combine_by_coords(rasters)
    merged.rio.write_crs("EPSG:4326", inplace=True)
    merged_clipped = merged.rio.clip_box(
        bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
    )

    return merged_clipped


if __name__ == "__main__":

    year = 2020
    bbox = BoundingBox([2.5, 39.5, 3, 40])

    merged = get_worldpop(bbox, year)

    # merged.rio.write_crs("EPSG:4326", inplace=True)
    # merged.rio.to_raster("worldpop.tif", compress="deflate", COMPRESS_LEVEL=9)
