"""Fetch and prepare land use / land cover (LULC) covariates for an AOI."""

import numpy as np
import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_esalulc_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    year: int,
) -> np.ndarray:
    """Sample ESA CCI dominant LULC class at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest (used to clip before sampling).
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    year : int
        Year to extract (between 1992 and 2020).

    Returns
    -------
    np.ndarray
        Dominant LULC class index at each point (NaN for water / no-data).
    """
    if 1992 > year > 2020:
        raise ValueError("Year must be between 1992 and 2020.")

    url = (
        f"https://dap.ceda.ac.uk/thredds/dodsC/neodc/esacci/land_cover/"
        f"data/pft/v2.0.81/ESACCI-LC-L4-PFT-Map-300m-P1Y-{year}-v2.0.81.nc"
    )
    ds = xr.open_dataset(url, engine="netcdf4")

    bounds_vars = [
        v for v in ds.data_vars if str(v).endswith("_bounds") or str(v).endswith("_bnds")
    ]
    ds = ds.drop_vars(bounds_vars, errors="ignore")
    ds = ds.rename({"lat": "y", "lon": "x"})
    ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)
    ds = ds.rio.write_crs("EPSG:4326", inplace=True)
    ds = ds.rio.clip_box(minx=bbox.xmin, miny=bbox.ymin, maxx=bbox.xmax, maxy=bbox.ymax)
    ds = ds.isel(time=0)

    vars_list = [
        "WATER",
        "BARE",
        "BUILT",
        "GRASS-MAN",
        "GRASS-NAT",
        "SHRUBS-BD",
        "SHRUBS-BE",
        "SHRUBS-ND",
        "SHRUBS-NE",
        "WATER_INLAND",
        "SNOWICE",
        "TREES-BD",
        "TREES-BE",
        "TREES-ND",
        "TREES-NE",
        "LAND",
        "WATER_OCEAN",
    ]
    stacked = xr.concat([ds[var] for var in vars_list], dim="class").load()
    dominant = (stacked.argmax(dim="class") + 1).astype(float)

    # NaN out water classes (indices 1=WATER, 10=WATER_INLAND, 17=WATER_OCEAN)
    dominant = dominant.where(~dominant.isin([1, 10, 17]))

    x_pts = xr.DataArray(xs, dims="points")
    y_pts = xr.DataArray(ys, dims="points")
    sampled = dominant.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)

    return sampled
