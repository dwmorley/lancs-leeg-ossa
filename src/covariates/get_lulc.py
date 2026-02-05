import pystac_client
from typing import Union, Tuple
import numpy as np
import pandas as pd
import planetary_computer
import stackstac
import matplotlib
import xarray

from src.covariates.spatial_aoi import BoundingBox

matplotlib.use("TkAgg")  # or 'Qt5Agg' or 'MacOSX'


def get_lulc(
    aoi: Union[Tuple[float, float, float, float], list, np.ndarray, pd.DataFrame],
    year: int = 2023,
) -> xarray.DataArray:

    bbox = BoundingBox(*aoi)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=["io-lulc-annual-v02"],
        bbox=[bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax],
        datetime=f"{year}",
    )
    items = [item for item in search.items() if int(item.id.split("-")[1]) == year]

    stack = stackstac.stack(
        items,
        dtype=np.ubyte,
        fill_value=np.uint8(0),
        bounds_latlon=(bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax),
        sortby_date=False,
        rescale=False,
        epsg=4326,
    ).assign_coords(
        time=pd.to_datetime(
            [item.properties["start_datetime"] for item in items]
        ).tz_convert(None)
    )

    da_raster = stack.squeeze().compute()
    return da_raster


if __name__ == "__main__":
    get_lulc(
        aoi=[1.5, 6.0, 2.1, 7.0],
        year=2020,
    )
