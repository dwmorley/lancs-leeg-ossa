"""Get and transform MODIS rasters."""

from datetime import datetime
from typing import Dict, Tuple, Union

import numpy as np
import planetary_computer
import pystac_client
import rioxarray  # noqa: F401
import stackstac
import xarray as xr
from shiny import ui

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


def get_modis_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    variable: str,
    date_range: tuple[datetime, datetime],
    return_timeseries: bool = False,
) -> Union[Dict[str, np.ndarray], Tuple[Dict[str, np.ndarray], Dict], None]:
    """Sample MODIS values at specific lon/lat coordinates.

    Builds the same spatially-mosaicked stack as :func:`get_modis`, applies
    the same temporal aggregation, then samples each aggregated raster at the
    supplied point coordinates using nearest-neighbour lookup.  Every (xs, ys)
    pair is guaranteed an output value (NaN where the raster contains no data).

    Parameters
    ----------
    bbox : BoundingBox
        Bounding box used to search for MODIS tiles.
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    variable : str
        MODIS variable to fetch (e.g. 'ET_500m').
    date_range : tuple[datetime, datetime]
        Date range.
    return_timeseries : bool, optional
        If True, also return the raw timeseries data with dates (default: False).

    Returns
    -------
    dict[str, np.ndarray] or tuple or None
        If return_timeseries is False:
            Dictionary of {aggregation_key: values_array}, or None if no data found.
        If return_timeseries is True:
            Tuple of (aggregated_dict, timeseries_dict) where timeseries_dict contains
            {'dates': list of date strings, 'data': dict of {col_name: values_array}}.
        Each array has the same length as *xs* / *ys*.
    """
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    variable = variable.removeprefix("modis_")
    collection = get_collection(variable)

    search = catalog.search(collections=[collection], bbox=bbox.to_list(), datetime=date_range)
    items = search.item_collection()

    if len(items) == 0:
        ui.notification_show(
            f"No MODIS tiles found for requested AOI/date range. {variable} will be skipped.",
            type="warning",
        )
        return None

    # Extract item dates for fallback when xarray time dimension is NaT
    item_dates = []
    for item in items:
        try:
            # Try to get the start_datetime from properties
            start_dt = item.properties.get("start_datetime") or item.properties.get("datetime")
            if start_dt:
                item_dates.append(start_dt[:10])  # Get YYYY-MM-DD part
        except Exception:
            pass

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

    nodata_value = MODIS_CONFIGS[variable]["nodata"]
    if nodata_value is not None:
        if nodata_value < 0:
            stack = stack.where(stack > nodata_value, np.nan)
        else:
            stack = stack.where(stack < nodata_value, np.nan)

    da_raster = stackstac.mosaic(stack, dim="band", nodata=np.nan).load()
    x_pts = xr.DataArray(xs, dims="points")
    y_pts = xr.DataArray(ys, dims="points")

    results: Dict[str, np.ndarray] = {}
    for method in MODIS_CONFIGS[variable]["aggregation"]:
        agg = aggregate_ts(da_raster, method=method)
        if agg is None:
            agg = da_raster.isel(time=0) if "time" in da_raster.dims else da_raster

        sampled = agg.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)
        results[f"{variable}_{method}"] = sampled

    if not return_timeseries:
        return results if results else None

    # Build timeseries data with date columns
    timeseries_data = {}
    dates = []
    try:
        if "time" in da_raster.dims:
            # Handle numpy datetime64 arrays safely
            time_values = da_raster.time.values
            valid_times_found = False

            for i, t_val in enumerate(time_values):
                try:
                    # Check if time value is NaT (Not a Time)
                    if np.isnat(t_val):
                        continue

                    # Convert numpy datetime64 to string
                    date_str = str(t_val)[:10]  # YYYY-MM-DD
                    date_formatted = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m%y")
                    sampled = (
                        da_raster.isel(time=i)
                        .sel(x=x_pts, y=y_pts, method="nearest")
                        .values.astype(float)
                    )
                    timeseries_data[f"{variable}_{date_formatted}"] = sampled
                    dates.append(date_str)
                    valid_times_found = True
                except Exception:
                    # Skip this time step but continue with others
                    continue

            # If no valid xarray times found, fall back to item dates
            if not valid_times_found and item_dates:
                for i, date_str in enumerate(item_dates):
                    try:
                        if i >= len(da_raster.time):
                            break
                        date_formatted = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m%y")
                        sampled = (
                            da_raster.isel(time=i)
                            .sel(x=x_pts, y=y_pts, method="nearest")
                            .values.astype(float)
                        )
                        timeseries_data[f"{variable}_{date_formatted}"] = sampled
                        dates.append(date_str)
                    except Exception:
                        continue

            if not valid_times_found and not item_dates:
                # Return aggregated results without timeseries
                return results if results else None
        else:
            # Single time step, treat as single entry
            date_formatted = datetime.now().strftime("%d%m%y")
            sampled = da_raster.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)
            timeseries_data[f"{variable}_{date_formatted}"] = sampled
            dates.append(datetime.now().strftime("%Y-%m-%d"))
    except Exception:
        # Fall back to returning just aggregated results
        return results if results else None

    if not timeseries_data:
        return results if results else None

    agg_result = results if results else None
    ts_info = {"dates": dates, "data": timeseries_data}
    return (agg_result, ts_info)


if __name__ == "__main__":

    start = datetime.strptime("2019-01-01", "%Y-%m-%d")
    end = datetime.strptime("2019-03-01", "%Y-%m-%d")

    var = "LST_Day_1KM"

    bbox = BoundingBox([38.6, 6.17, 41, 7.36])
    xy = bbox.sampling_grid(500)
    x = xy[:, 0]
    y = xy[:, 1]
    points = get_modis_points(
        bbox=bbox,
        variable=var,
        date_range=(start, end),
        xs=x,
        ys=y,
    )
    b = 0
