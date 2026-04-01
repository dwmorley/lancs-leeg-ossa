"""Utilities to download and prepare TerraClimate covariates for an AOI."""

from datetime import datetime

import numpy as np
import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_terraclimate_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    variable: str,
    date_range: tuple[datetime, datetime],
) -> np.ndarray:
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

    Returns
    -------
    np.ndarray
        Mean annual values at each point (NaN where no data).
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
    da = da.mean(dim="time", skipna=True)
    da = da.rename({"lon": "x", "lat": "y"})
    da = da.load()

    x_pts = xr.DataArray(xs, dims="points")
    y_pts = xr.DataArray(ys, dims="points")
    sampled = da.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)

    return sampled
