"""Get and transform MODIS rasters."""

from datetime import datetime
from typing import Dict, Union

import numpy as np
import planetary_computer
import pystac_client
import rioxarray  # noqa: F401
import stackstac
import xarray as xr

from src.utils.bounding_box import BoundingBox

MODIS_CONFIGS = {
    "ET_500m": {"aggregation": ["mean"], "nodata": 6553},
    "LST_Day_1KM": {
        "aggregation": ["mean", "min", "max"],
        "nodata": None,
    },
    "Gpp_500m": {"aggregation": ["mean", "min", "max"], "nodata": 3.2762},
}


def get_modis(
    bbox: BoundingBox,
    variable: str,
    date_range: tuple[datetime, datetime],
) -> Dict[str, xr.DataArray]:
    """Fetch and prepare MODIS rasters for the AOI, variable, and year.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to fetch the MODIS rasters for.
    variable : str
        MODIS variable to fetch (e.g. 'ET_500m')
    date_range : tuple[datetime, datetime]
        Date range

    Returns
    -------
    dict[str, xarray.DataArray] or None
        Dictionary of rasters, where keys are variable name with aggregation method,
        or None if no MODIS tiles were found for the requested AOI/date range.
    """
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    variable = variable.strip("modis_")
    collection = get_collection(variable)

    search = catalog.search(collections=[collection], bbox=bbox.to_list(), datetime=date_range)
    items = search.item_collection()

    stack = stackstac.stack(
        items,
        dtype=np.dtype("float64"),
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


def aggregate_ts(da_raster: xr.DataArray, method: str = "mean") -> Union[xr.DataArray, None]:
    """Aggregate a time series of rasters using the specified method.

    Parameters
    ----------
    da_raster : xarray.DataArray
        Input raster with a time dimension.
    method : str, optional
        Aggregation method to apply across the time dimension.
        Supported methods: 'mean', 'min', 'max' (default: 'mean')

    Returns
    -------
    xarray.DataArray or None
        Aggregated raster if time dimension exists, otherwise None.
    """
    if "time" not in da_raster.coords or len(da_raster.time) <= 1:
        return None

    methods = {
        "mean": lambda da: da.mean(dim="time", skipna=True),
        "min": lambda da: da.min(dim="time", skipna=True),
        "max": lambda da: da.max(dim="time", skipna=True),
    }

    if method not in methods:
        raise ValueError(
            f"Unsupported aggregation method: {method}. " f"Choose from {list(methods.keys())}"
        )

    return methods[method](da_raster)


def get_collection(var: str) -> str:
    """Connect to Microsoft Planetary Computer STAC API and find the MODIS collection.

    Parameters
    ----------
    var : str
        Variable name to search for in the collection assets (e.g. 'ET_500m').

    Returns
    -------
        The MODIS collection ID.
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

    start = datetime.strptime("2019-01-01", "%Y-%m-%d")
    end = datetime.strptime("2019-03-17", "%Y-%m-%d")

    r = get_modis(
        bbox=BoundingBox([-2.502, 42.698, -2.2, 43.0850]),
        variable="modis_LST_Day_1KM",
        date_range=(start, end),
    )

    if r is not None:
        r["LST_Day_1KM_mean"].rio.write_crs("epsg:4326")
        r["LST_Day_1KM_mean"].rio.to_raster("modis.tif", compress="deflate", COMPRESS_LEVEL=9)
