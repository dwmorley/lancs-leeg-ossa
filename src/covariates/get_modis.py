from typing import Tuple
from typing import Union

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import stackstac
import xarray as xr

from src.covariates.bounding_box import BoundingBox


def get_modis(
    aoi: Union[Tuple[float, float, float, float], list, np.ndarray, pd.DataFrame],
    variable: str,
    date_range: str,
) -> xr.DataArray:

    bbox = BoundingBox(*aoi)

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    collection = get_collection(variable)

    search = catalog.search(
        collections=[collection],
        bbox=[bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax],
        datetime=date_range,
    )
    items = search.item_collection()

    if len(items) == 0:
        raise Exception(
            f"No MODIS tiles found for variable {variable} in the specified AOI and date range."
        )

    stack = stackstac.stack(
        items,
        assets=[variable],
        epsg=4326,
        bounds=(bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax),
        chunksize="auto",
    )
    da_raster = stackstac.mosaic(stack, dim="time")
    return da_raster


def get_collection(var: str) -> Union[str, None]:
    """
    Connect to Microsoft Planetary Computer STAC API and find
    the MODIS collection containing the specified variable.

    Returns the collection ID.
    """
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    collections = list(catalog.get_collections())
    modis_collections = [c for c in collections if "modis" in c.id.lower()]

    for collection in modis_collections:
        search = catalog.search(collections=[collection.id], max_items=1)
        item = next(search.items(), None)
        if item and var in item.assets:
            return collection.id

    raise Exception(f"Variable {var} not found in MODIS collections.")


if __name__ == "__main__":
    get_modis(
        aoi=[1.5, 6.0, 2.1, 7.0],
        variable="ET_500m",
        date_range="2019-01-01/2019-01-31",
    )
