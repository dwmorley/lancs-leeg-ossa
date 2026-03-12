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
    # modis-16A3GF-061 / modis-16A2-061 - Net Evapotranspiration
    "ET_500m": {"aggregation": ["avg"], "nodata": 6553},
    "LE_500m": {"aggregation": ["avg"], "nodata": 327630000},
    "PET_500m": {"aggregation": ["avg"], "nodata": 6553},
    "PLE_500m": {"aggregation": ["avg"], "nodata": 327630000},
    # modis-11A2-061 / modis-11A1-061 / modis-21A2-061 - Land Surface Temperature
    "LST_Day_1KM": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "LST_Night_1KM": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "LST_Day_1km": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "LST_Night_1km": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "Emis_31": {"aggregation": ["avg"], "nodata": None},
    "Emis_32": {"aggregation": ["avg"], "nodata": None},
    "Emis_29": {"aggregation": ["avg"], "nodata": None},
    # modis-17A2H-061 / modis-17A2HGF-061 / modis-17A3HGF-061 - Gross/Net Primary Productivity
    "Gpp_500m": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": 3.2762},
    "PsnNet_500m": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": 3.2762},
    "Npp_500m": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": 3.2762},
    # modis-09A1-061 - Surface Reflectance 8-Day (500m)
    "sur_refl_b01": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b02": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b03": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b04": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b05": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b06": {"aggregation": ["avg"], "nodata": None},
    "sur_refl_b07": {"aggregation": ["avg"], "nodata": None},
    # modis-09Q1-061 - Surface Reflectance 8-Day (250m)
    # sur_refl_b01 / sur_refl_b02 shared with above
    # modis-43A4-061 - Nadir BRDF-Adjusted Reflectance (NBAR) Daily
    "Nadir_Reflectance_Band1": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band2": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band3": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band4": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band5": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band6": {"aggregation": ["avg"], "nodata": None},
    "Nadir_Reflectance_Band7": {"aggregation": ["avg"], "nodata": None},
    # modis-13Q1-061 - Vegetation Indices 16-Day (250m)
    "250m_16_days_EVI": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "250m_16_days_NDVI": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "250m_16_days_NIR_reflectance": {"aggregation": ["avg"], "nodata": None},
    "250m_16_days_MIR_reflectance": {"aggregation": ["avg"], "nodata": None},
    "250m_16_days_red_reflectance": {"aggregation": ["avg"], "nodata": None},
    "250m_16_days_blue_reflectance": {"aggregation": ["avg"], "nodata": None},
    # modis-13A1-061 - Vegetation Indices 16-Day (500m)
    "500m_16_days_EVI": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "500m_16_days_NDVI": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "500m_16_days_NIR_reflectance": {"aggregation": ["avg"], "nodata": None},
    "500m_16_days_MIR_reflectance": {"aggregation": ["avg"], "nodata": None},
    "500m_16_days_red_reflectance": {"aggregation": ["avg"], "nodata": None},
    "500m_16_days_blue_reflectance": {"aggregation": ["avg"], "nodata": None},
    # modis-15A2H-061 / modis-15A3H-061 - Leaf Area Index/FPAR
    "Lai_500m": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": 25.4},
    "Fpar_500m": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": 2.54},
    # modis-10A2-061 - Snow Cover 8-day
    "Maximum_Snow_Extent": {"aggregation": ["avg"], "nodata": None},
    "Eight_Day_Snow_Cover": {"aggregation": ["avg"], "nodata": None},
    # modis-10A1-061 - Snow Cover Daily
    "NDSI_Snow_Cover": {"aggregation": ["avg", "min", "max", "sd", "ampl"], "nodata": None},
    "Snow_Albedo_Daily_Tile": {"aggregation": ["avg"], "nodata": None},
    "NDSI": {"aggregation": ["avg"], "nodata": -3.2768},
}


def get_modis(
    bbox: BoundingBox,
    variable: str,
    date_range: tuple[datetime, datetime],
) -> Dict[str, xr.DataArray] | None:
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
    """
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    variable = variable.removeprefix("modis_")
    collection = get_collection(variable)

    search = catalog.search(collections=[collection], bbox=bbox.to_list(), datetime=date_range)
    items = search.item_collection()

    # Nothing found for the AOI/date range
    if len(items) == 0:
        print(f"No MODIS tiles found for requested AOI/date range. {variable} will be skipped.")
        return None

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
        if nodata_value < 0:
            stack = stack.where(stack > nodata_value, np.nan)
        else:
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


def aggregate_ts(da_raster: xr.DataArray, method: str = "avg") -> Union[xr.DataArray, None]:
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
        "avg": lambda da: da.mean(dim="time", skipna=True),
        "min": lambda da: da.min(dim="time", skipna=True),
        "max": lambda da: da.max(dim="time", skipna=True),
        "sd": lambda da: da.std(dim="time", skipna=True),
        "ampl": lambda da: da.max(dim="time", skipna=True) - da.min(dim="time", skipna=True),
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
    end = datetime.strptime("2019-03-01", "%Y-%m-%d")

    var = "LST_Day_1KM"

    r = get_modis(
        bbox=BoundingBox([-2.7, 43.2, -2.502, 43.5]),
        variable=var,
        date_range=(start, end),
    )

    if r is not None:
        r[f"{var}_sd"].rio.write_crs("epsg:4326")
        r[f"{var}_sd"].rio.to_raster("modis.tif", compress="deflate", COMPRESS_LEVEL=9)
