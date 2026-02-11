from typing import Union

import numpy as np
import planetary_computer
import pystac_client
import stackstac
import xarray as xr
import rioxarray  # noqa: F401

from src.gis.bounding_box import BoundingBox


MODIS_CONFIGS = {
    "ET_500m": {"aggregation": ["mean"], "date_range": "{year}", "nodata": 6553},
    "LST_Day_1KM": {
        "aggregation": ["mean", "min", "max"],
        "date_range": "{year}",
        "nodata": None,
    },
}


def get_modis(
    bbox: BoundingBox,
    variable: str,
    year: int,
) -> dict[str, xr.DataArray]:

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    collection = get_collection(variable)

    date_range = MODIS_CONFIGS[variable]["date_range"].format(year=year)

    search = catalog.search(
        collections=[collection],
        bbox=bbox.to_list(),
        datetime=date_range,
    )
    items = search.item_collection()

    if len(items) == 0:
        raise Exception(
            f"No MODIS tiles found for variable {variable} in the specified AOI and date range."
        )

    stack = stackstac.stack(
        items,
        dtype=np.float64,
        fill_value=np.nan,
        assets=[variable],
        epsg=4326,
        bounds=bbox.to_tuple(),
        rescale=True,
        chunksize="auto",
    )

    # Mask nodata values
    nodata_value = MODIS_CONFIGS[variable]["nodata"]
    if nodata_value is not None:
        stack = stack.where(stack < nodata_value, np.nan)

    # Mosaic the stack into a single raster on spatial dimensions.
    da_raster = stackstac.mosaic(stack, dim="band", nodata=np.nan)

    # Perform temporal aggregation if needed
    rasters = {}
    aggregation_methods = MODIS_CONFIGS[variable]["aggregation"]
    if aggregation_methods:
        for method in aggregation_methods:
            rasters[f"{variable}_{method}"] = aggregate_ts(da_raster, method=method)
    else:
        rasters[f"{variable}"] = da_raster

    return rasters


def aggregate_ts(
    da_raster: xr.DataArray, method: str = "mean"
) -> Union[xr.DataArray, None]:

    if "time" not in da_raster.coords or len(da_raster.time) <= 1:
        return None

    methods = {
        "mean": lambda da: da.mean(dim="time", skipna=True),
        "min": lambda da: da.min(dim="time", skipna=True),
        "max": lambda da: da.max(dim="time", skipna=True),
    }

    if method not in methods:
        raise ValueError(
            f"Unsupported aggregation method: {method}. "
            f"Choose from {list(methods.keys())}"
        )

    return methods[method](da_raster)


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
    pass
