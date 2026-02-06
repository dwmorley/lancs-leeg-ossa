from typing import Tuple
from typing import Union

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import stackstac
import xarray

from src.covariates.bounding_box import BoundingBox


def get_lulc(
    aoi: Union[Tuple[float, float, float, float], list, np.ndarray, pd.DataFrame],
    year: int = 2023,
) -> xarray.DataArray:
    """
    Impact Observatory, Microsoft, and Esri. (2023). Global Land Use Land Cover (LULC) Dataset, 10m Resolution (2017-2023).
    ESA Sentinel-2 Imagery. Available at: https://planetarycomputer.microsoft.com/

    https://planetarycomputer.microsoft.com/dataset/io-lulc-annual-v02

    :param aoi: The BoundingBox can be initialized with four bounds (xmin, ymin, xmax, ymax) or from coordinates (tuple/list of 4 bounds or numpy array/pandas DataFrame with coordinates).
    :param year: Has to be between 2017 and 2023.
    :return: a land use land cover (LULC) raster for the specified area of interest (AOI) and year.
    """

    if 2017 > year > 2023:
        raise ValueError("Year must be between 2017 and 2023.")

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

    # Set class names as attributes
    collection = catalog.get_collection("io-lulc-9-class")
    x = collection.item_assets["data"]
    class_names = {x["values"][0]: x["summary"] for x in x.properties["file:values"]}
    da_raster.attrs["class"] = class_names

    return da_raster


if __name__ == "__main__":
    get_lulc(
        aoi=[1.5, 6.0, 2.1, 7.0],
        year=2020,
    )
