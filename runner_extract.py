"""Utilities and runner entrypoint for extraction tasks used by OSSA."""

import time
from datetime import datetime
from typing import List

import pandas as pd
import xarray as xr
from pystac_client.exceptions import APIError
from shiny import ui

from src.constants import COVARIATE_OPTIONS
from src.covariates.get_dem import get_dem
from src.covariates.get_ecmwf import get_ecmwf
from src.covariates.get_lulc import get_lulc
from src.covariates.get_modis import get_modis
from src.covariates.get_roaddensity import get_roaddensity
from src.covariates.get_soilgrids import get_soilgrids
from src.covariates.get_terraclimate import get_terraclimate
from src.covariates.get_worldpop import get_worldpop
from src.utils.bounding_box import BoundingBox


def run_extraction(
    bbox: BoundingBox,
    variables: List[str],
    date_range: tuple[datetime, datetime],
    sample_size: int,
    api_keys: dict[str, str],
    progress=None,
) -> pd.DataFrame:
    """Extract selected covariates clipped to `bbox` at grid points.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest.
    variables : list[str]
        Covariate keys to extract (see COVARIATE_OPTIONS).
    date_range : tuple[datetime, datetime]
        Date range to determine raster years.
    sample_size : int
        Target number of sample points.
    api_keys : dict[str, str]
        API keys for data sources, e.g. {"ecmwf": "my_key"}
    progress : optional
        Progress UI object supporting set(value=int, message=str).

    Returns
    -------
    pandas.DataFrame
        Sampled covariate values at the requested grid points.
    """
    # The maximum year from date_range
    year = max(date_range[0].year, date_range[1].year)

    # fmt: off
    variable_funcs = {
        "landcover": lambda: get_lulc(bbox=bbox, year=year),
        "dem": lambda: get_dem(bbox=bbox, res=30),
        "wp_1km_unadj": lambda: get_worldpop(bbox=bbox, year=year),
        "modis_ET_500m": lambda: get_modis(bbox=bbox, variable="ET_500m", date_range=date_range),
        "modis_LST_Day_1KM": lambda: get_modis(bbox=bbox, variable="LST_Day_1KM", date_range=date_range),
        "modis_Gpp_500m": lambda: get_modis(bbox=bbox, variable="Gpp_500m", date_range=date_range),
    }
    for var in variables:
        if var.startswith("terraclimate_"):
            variable_funcs[var] = lambda v=var: get_terraclimate(bbox=bbox, variable=v.split("terraclimate_")[1], date_range=date_range)
        elif var.startswith("grip_"):
            road_type = int(var.split("grip_")[1])
            variable_funcs[var] = lambda rt=road_type: get_roaddensity(bbox=bbox, road_type=rt)
        elif var.startswith("sg_"):
            variable_funcs[var] = lambda v=var: get_soilgrids(bbox=bbox, variable=v.split("sg_")[1])
    # fmt: on

    if "landcover" not in variables:
        raise ValueError("Landcover must be included in the selected variables.")

    # The points to sample the rasters at
    grid = bbox.sampling_grid(sample_size)
    df = pd.DataFrame({"longitude": grid[:, 0], "latitude": grid[:, 1]})
    x = xr.DataArray(grid[:, 0], dims="points")
    y = xr.DataArray(grid[:, 1], dims="points")

    ecmwfs = []
    for i, var in enumerate(variables):

        # We can do these as batch at the end
        if var.startswith("ecmwf_"):
            ecmwfs.append(var.removeprefix("ecmwf_"))
            continue

        progress.set(
            value=int((i / len(variables)) * 100),
            message=f"Processing {COVARIATE_OPTIONS[var]}...",
        )

        func = variable_funcs.get(var)

        if func:

            def _call_with_retries(fn, *, retries: int = 3, base_delay: float = 1.0):
                for attempt in range(retries):
                    try:
                        return fn()
                    except APIError:
                        if attempt < retries - 1:
                            delay = base_delay * (2**attempt)
                            time.sleep(delay)
                            continue
                        # Exhausted retries: notify and return None
                        try:
                            ui.notification_show(
                                "The API request timed out after multiple attempts. "
                                "Please try again later.",
                                type="error",
                            )
                        except Exception:
                            print("The API request timed out after multiple attempts.")
                        return None
                    except Exception as e:
                        ui.notification_show(
                            f"Error while fetching {var}: {e}", type="error", duration=5
                        )
                        return None

            raster = _call_with_retries(func)
        else:
            raise ValueError(f"Unknown variable: {var}")

        # If raster retrieval failed (None), skip this variable and continue.
        if raster is None:
            ui.notification_show(
                f"Skipping {COVARIATE_OPTIONS[var]} — failed to retrieve data.",
                type="warning",
                duration=None,
            )
            continue

        if isinstance(raster, dict):
            for k, v in raster.items():
                v = _ensure_spatial_index(v)
                values = v.sel(x=x, y=y, method="nearest").values
                if values.ndim > 1:
                    values = values.squeeze()
                df[k] = values

        else:
            raster = _ensure_spatial_index(raster)
            values = raster.sel(x=x, y=y, method="nearest").values
            if values.ndim > 1:
                values = values.squeeze()
            df[var] = values

    if len(ecmwfs):

        progress.set(
            value=int(((len(variables) - len(ecmwfs)) / len(variables)) * 100),
            message=f"Processing ERA5 variable(s)...{ecmwfs}",
        )

        rasters = get_ecmwf(
            bbox=bbox,
            variables=ecmwfs,
            api_keys=api_keys,
            date_range=date_range,
        )
        if rasters is None:
            ui.notification_show(
                "Failed to retrieve ECMWF data. Skipped. Please check your API key and try again.",
                type="warning",
            )
        else:
            for var, raster in rasters.items():
                raster = _ensure_spatial_index(raster)
                df[var] = raster.sel(x=x, y=y, method="nearest").values

    progress.set(value=100, message="Finalising...")

    df = df.dropna()
    df = df[df["landcover"] != 0]

    return df


def _ensure_spatial_index(da: xr.DataArray) -> xr.DataArray:
    """Rebuild x/y indexes if they are missing, so that .sel() works correctly.

    Newer xarray versions require an explicit PandasIndex backing each coordinate
    used in .sel().  Some data sources (stackstac mosaics, rioxarray clip_box …)
    return DataArrays where the coordinate values are present but the index is not,
    causing KeyError: "no index found for coordinate 'y'".
    """
    rebuild = {
        dim: da[dim].values for dim in ("x", "y") if dim in da.dims and dim not in da.indexes
    }
    if rebuild:
        da = da.assign_coords(rebuild)
    return da
