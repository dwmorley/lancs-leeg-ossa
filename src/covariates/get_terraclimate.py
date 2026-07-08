"""Utilities to download and prepare TerraClimate covariates for an AOI."""

from datetime import datetime
from typing import Tuple, Union

import numpy as np
import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_terraclimate_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    variable: str,
    date_range: tuple[datetime, datetime],
    return_timeseries: bool = False,
) -> Union[np.ndarray, Tuple[np.ndarray, dict]]:
    """Sample TerraClimate mean values at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest (used to clip before sampling).
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    variable : str
        TerraClimate variable name.
    date_range : tuple[datetime, datetime]
        Months to extract and average.
    return_timeseries : bool, optional
        If True, also return raw timeseries data with dates (default: False).

    Returns
    -------
    np.ndarray or tuple
        If return_timeseries is False:
            Mean annual values at each point (NaN where no data).
        If return_timeseries is True:
            Tuple of (aggregated_array, timeseries_dict) where timeseries_dict contains
            {'dates': list of date strings, 'data': dict of {col_name: values_array}}.
    """
    possible = [
        "aet",
        "def",
        "pet",
        "ppt",
        "q",
        "soil",
        "srad",
        "swe",
        "tmax",
        "tmin",
        "vap",
        "vpd",
        "ws",
        "PDSI",
    ]
    if variable not in possible:
        raise ValueError(f"Variable must be one of {possible}")

    url = (
        f"http://thredds.northwestknowledge.net:8080/thredds/dodsC/"
        f"agg_terraclimate_{variable}_1950_CurrentYear_GLOBE.nc"
    )
    ds = xr.open_dataset(url, chunks={"time": 12, "lat": 500, "lon": 500})
    da = ds[variable].sel(
        time=slice(date_range[0].strftime("%Y-%m-%d"), date_range[1].strftime("%Y-%m-%d"))
    )
    da.rio.write_crs("EPSG:4326", inplace=True)
    da = da.rio.clip_box(
        bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
    )

    da_clipped = da.copy()
    da = da.mean(dim="time", skipna=True)
    da = da.rename({"lon": "x", "lat": "y"})
    da = da.load()

    x_pts = xr.DataArray(xs, dims="points")
    y_pts = xr.DataArray(ys, dims="points")
    sampled = da.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)

    if not return_timeseries:
        return sampled

    # Build timeseries data with date columns
    try:
        da_clipped = da_clipped.rename({"lon": "x", "lat": "y"}).load()
        timeseries_data = {}
        dates = []

        valid_times_found = False
        for i, time_val in enumerate(da_clipped.time.values):
            try:
                # Check if time value is NaT (Not a Time)
                if np.isnat(time_val):
                    continue

                date_str = str(time_val)[:10]  # YYYY-MM-DD format
                date_obj = datetime.fromisoformat(date_str)
                date_formatted = date_obj.strftime("%d%m%y")
                dates.append(date_str)
                ts_sampled = (
                    da_clipped.isel(time=i)
                    .sel(x=x_pts, y=y_pts, method="nearest")
                    .values.astype(float)
                )
                timeseries_data[f"{variable}_{date_formatted}"] = ts_sampled
                valid_times_found = True
            except Exception:
                # Skip this time step but continue with others
                continue

        if not valid_times_found:
            return sampled

        return sampled, {"dates": dates, "data": timeseries_data}
    except Exception:
        # Fall back to returning just aggregated results
        return sampled
