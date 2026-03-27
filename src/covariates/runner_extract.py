"""Utilities and runner entrypoint for extraction tasks used by OSSA."""

import contextlib
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

import pandas as pd
import urllib3
import xarray as xr
from pystac_client.exceptions import APIError
from shiny import ui

from src.constants import COVARIATE_OPTIONS, RESPONSE_OPTIONS
from src.covariates.get_dem import get_dem
from src.covariates.get_ecmwf import get_ecmwf
from src.covariates.get_esalulc import get_esalulc
from src.covariates.get_iolulc import get_iolulc
from src.covariates.get_modis import get_modis
from src.covariates.get_roaddensity import get_roaddensity
from src.covariates.get_soilgrids import get_soilgrids
from src.covariates.get_terraclimate import get_terraclimate
from src.covariates.get_worldpop import get_worldpop
from src.utils.bounding_box import BoundingBox

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
USE_THREADING_FOR_IO = True


@contextlib.contextmanager
def _suppress_hdf5_errors():
    """Redirect stderr at the file-descriptor level to silence HDF5 C-library diagnostics."""
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stderr_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(old_stderr_fd, 2)
        os.close(old_stderr_fd)


def _fetch_single_variable(
    var: str,
    bbox: BoundingBox,
    year: int,
    date_range: Tuple[datetime, datetime],
    variable_lut: dict,
) -> Tuple[str, Optional[dict], Optional[str]]:
    """Fetch a single variable (worker function for parallel processing).

    Parameters
    ----------
    var : str
        Variable name to fetch
    bbox : BoundingBox
        Area of interest
    year : int
        Year for extraction
    date_range : tuple
        Date range for time-series data
    variable_lut : dict
        Look-up table for variable names

    Returns
    -------
    tuple
        (variable_name, result_dict_or_array, error_message_or_None)
        - result_dict_or_array: either a dict of xr.DataArray (for multi-var results)
                                or single xr.DataArray
        - error_message: None if success, error string if failed
    """
    try:
        # Suppress HDF5 and SSL warnings in worker processes
        warnings.filterwarnings("ignore", category=UserWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        import logging

        logging.getLogger("h5py").setLevel(logging.CRITICAL)

        with _suppress_hdf5_errors():
            variable_funcs: dict[str, Callable] = {
                "io_landcoverio": lambda: get_iolulc(bbox=bbox, year=year),
                "esa_ccilc": lambda: get_esalulc(bbox=bbox, year=year),
                "wp_1km_unadj": lambda: get_worldpop(bbox=bbox, year=year, adjusted=True),
                "wp_1km": lambda: get_worldpop(bbox=bbox, year=year, adjusted=False),
            }

            # Dynamic variable mapping
            if var.startswith("terraclimate_"):
                func = lambda: get_terraclimate(
                    bbox=bbox, variable=var.split("terraclimate_")[1], date_range=date_range
                )
            elif var.startswith("grip_"):
                road_type = int(var.split("_")[1])
                func = lambda: get_roaddensity(bbox=bbox, road_type=road_type)
            elif var.startswith("sg_"):
                func = lambda: get_soilgrids(bbox=bbox, variable=var.split("sg_")[1])
            elif var.startswith("modis_"):
                func = lambda: get_modis(
                    bbox=bbox, variable=var.split("modis_")[1], date_range=date_range
                )
            elif var.startswith("cop_"):
                func = lambda: get_dem(bbox=bbox, res=int(var.split("_")[2]))
            elif var in variable_funcs:
                func = variable_funcs[var]
            else:
                return var, None, f"Unknown variable: {var}"

            # Call with retries
            raster = _call_with_retries(func, var)

            if raster is None:
                return var, None, f"API timeout/failure for {variable_lut.get(var, var)}"

            return var, raster, None

    except Exception as e:
        error_msg = str(e)
        return var, None, f"Error: {error_msg}"


def _call_with_retries(fn: Callable, var_name: str, retries: int = 3, base_delay: float = 1.0):
    """Call a function with exponential backoff retries.

    Parameters
    ----------
    fn : callable
        Function to call
    var_name : str
        Variable name for error messages
    retries : int
        Number of retry attempts
    base_delay : float
        Initial delay in seconds

    Returns
    -------
    result or None
        Result of function call, or None if all retries exhausted
    """
    for attempt in range(retries):
        try:
            return fn()
        except APIError:
            if attempt < retries - 1:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            return None
        except Exception:
            if attempt < retries - 1:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            return None
    return None


def run_extraction(
    bbox: BoundingBox,
    variables: List[str],
    date_range: tuple[datetime, datetime],
    sample_size: int,
    api_keys: dict[str, str],
    progress=None,
    max_workers: int = None,
    use_threading: bool = True,
) -> pd.DataFrame:
    """Extract selected covariates clipped to `bbox` at grid points - PARALLELIZED.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest.
    variables : list[str]
        Covariate keys to extract
    date_range : tuple[datetime, datetime]
        Date range to determine raster years.
    sample_size : int
        Target number of sample points.
    api_keys : dict[str, str]
        API keys for data sources, e.g. {"ecmwf": "my_key"}
    progress : optional
        Progress UI object supporting set(value=int, message=str).
    max_workers : int, optional
        Maximum number of parallel workers. Defaults to os.cpu_count() - 2.
        Set to 1 to disable parallelization.
    use_threading : bool, optional
        If True (default), use ThreadPoolExecutor (better for I/O-bound tasks like remote data).
        If False, use ProcessPoolExecutor (better for CPU-bound tasks).
        Threading is recommended for this use case.

    Returns
    -------
    pandas.DataFrame
        Sampled covariate values at the requested grid points.
    """
    if use_threading:
        from concurrent.futures import ThreadPoolExecutor

        ExecutorClass = ThreadPoolExecutor
    else:
        ExecutorClass = ProcessPoolExecutor

    if max_workers is None:
        cpu_count = os.cpu_count() or 2
        max_workers = max(1, cpu_count - 2)

    variable_lut = {**COVARIATE_OPTIONS, **RESPONSE_OPTIONS}

    # The maximum year from date_range
    year = max(date_range[0].year, date_range[1].year)

    # Set a default UTC TZ to avoid errors
    tz = timezone.utc

    def _to_utc(d) -> datetime:
        if not isinstance(d, datetime):
            d = datetime(d.year, d.month, d.day)
        return d.replace(tzinfo=tz) if d.tzinfo is None else d

    date_range = (_to_utc(date_range[0]), _to_utc(date_range[1]))

    # Separate ECMWF variables (batch processing) from others
    regular_vars = [v for v in variables if not v.startswith("ecmwf_")]
    ecmwf_vars = [v for v in variables if v.startswith("ecmwf_")]
    total_vars = len(regular_vars) + len(ecmwf_vars)

    # The points to sample the rasters at
    grid = bbox.sampling_grid(sample_size)
    df = pd.DataFrame({"longitude": grid[:, 0], "latitude": grid[:, 1]})
    x = xr.DataArray(grid[:, 0], dims="points")
    y = xr.DataArray(grid[:, 1], dims="points")

    # Process regular variables in parallel
    if regular_vars:
        progress.set(value=0, message="Starting extraction...")

        with ExecutorClass(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_var = {
                executor.submit(
                    _fetch_single_variable,
                    var,
                    bbox,
                    year,
                    date_range,
                    variable_lut,
                ): var
                for var in regular_vars
            }

            completed = 0
            for future in as_completed(future_to_var):
                var = future_to_var[future]

                try:
                    var_name, raster, error = future.result()

                    if error:
                        ui.notification_show(
                            f"Skipping {variable_lut.get(var_name, var_name)} — {error}",
                            type="warning",
                            duration=5,
                        )
                    elif raster is not None:
                        # Process the result
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
                            df[var_name] = values

                except Exception as e:
                    error_str = str(e)
                    if len(error_str) > 150:
                        error_str = error_str[:147] + "..."
                    ui.notification_show(
                        f"Failed to process {var}: {error_str}",
                        type="error",
                        duration=5,
                    )

                completed += 1
                progress_pct = int((completed / total_vars) * 100)
                progress.set(
                    value=progress_pct,
                    message=f"Extracted {completed}/{len(regular_vars)} variables...",
                )

    # Process ECMWF variables in batch (these should be done together)
    if ecmwf_vars:
        progress.set(
            value=int((len(regular_vars) / total_vars) * 100),
            message=f"Processing {len(ecmwf_vars)} ERA5 variable(s)...",
        )

        try:
            rasters = get_ecmwf(
                bbox=bbox,
                variables=ecmwf_vars,
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
                    if raster.size == 0:
                        ui.notification_show(
                            f"ECMWF variable {variable_lut.get(var, var)} not found for the AOI/date range. Skipped.",
                            type="warning",
                        )
                    else:
                        raster = _ensure_spatial_index(raster)
                        df[var] = raster.sel(x=x, y=y, method="nearest").values
        except Exception as e:
            ui.notification_show(
                f"Error processing ECMWF data: {str(e)}",
                type="error",
            )

    progress.set(value=95, message="Finalising...")

    df = df.dropna()

    progress.set(value=100, message="Complete!")

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
