"""Utilities and runner entrypoint for extraction tasks used by OSSA."""

import contextlib
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

import numpy as np
import pandas as pd
import urllib3
from ecmwf.datastores import Client
from pystac_client.exceptions import APIError

from src.constants import COVARIATE_OPTIONS, RESPONSE_OPTIONS
from src.covariates.get_dem import get_dem_points
from src.covariates.get_ecmwf import get_ecmwf_points
from src.covariates.get_esalulc import get_esalulc_points
from src.covariates.get_iolulc import get_iolulc_points
from src.covariates.get_modis import get_modis_points
from src.covariates.get_roaddensity import get_roaddensity_points
from src.covariates.get_soilgrids import get_soilgrids_points
from src.covariates.get_terraclimate import get_terraclimate_points
from src.covariates.get_worldpop import get_worldpop_points
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


def _fetch_single_variable_points(
    var: str,
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    year: int,
    date_range: Tuple[datetime, datetime],
    variable_lut: dict,
) -> Tuple[str, Optional[dict], Optional[str]]:
    """Fetch a single variable as point values (worker function for parallel processing).

    Parameters
    ----------
    var : str
        Variable name to fetch.
    bbox : BoundingBox
        Area of interest.
    xs : np.ndarray
        Longitudes of sample points.
    ys : np.ndarray
        Latitudes of sample points.
    year : int
        Year for extraction.
    date_range : tuple
        Date range for time-series data.
    variable_lut : dict
        Look-up table for variable names.

    Returns
    -------
    tuple
        (variable_name, result_dict_or_array, error_message_or_None)
        - result: either a dict of np.ndarray (for multi-output variables like MODIS)
                  or a single np.ndarray.
        - error_message: None if success, error string if failed.
    """
    try:
        warnings.filterwarnings("ignore", category=UserWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        import logging

        logging.getLogger("h5py").setLevel(logging.CRITICAL)

        with _suppress_hdf5_errors():
            variable_funcs: dict[str, Callable] = {
                "io_landcoverio": lambda: get_iolulc_points(bbox=bbox, xs=xs, ys=ys, year=year),
                "esa_ccilc": lambda: get_esalulc_points(bbox=bbox, xs=xs, ys=ys, year=year),
                "wp_1km_unadj": lambda: get_worldpop_points(
                    bbox=bbox, xs=xs, ys=ys, year=year, adjusted=True
                ),
                "wp_1km": lambda: get_worldpop_points(
                    bbox=bbox, xs=xs, ys=ys, year=year, adjusted=False
                ),
            }

            if var.startswith("terraclimate_"):
                func = lambda: get_terraclimate_points(
                    bbox=bbox,
                    xs=xs,
                    ys=ys,
                    variable=var.split("terraclimate_")[1],
                    date_range=date_range,
                )
            elif var.startswith("grip_"):
                road_type = int(var.split("_")[1])
                func = lambda: get_roaddensity_points(bbox=bbox, xs=xs, ys=ys, road_type=road_type)
            elif var.startswith("sg_"):
                func = lambda: get_soilgrids_points(
                    bbox=bbox, xs=xs, ys=ys, variable=var.split("sg_")[1]
                )
            elif var.startswith("modis_"):
                func = lambda: get_modis_points(
                    bbox=bbox,
                    xs=xs,
                    ys=ys,
                    variable=var.split("modis_")[1],
                    date_range=date_range,
                )
            elif var.startswith("cop_"):
                func = lambda: get_dem_points(bbox=bbox, xs=xs, ys=ys, res=int(var.split("_")[2]))
            elif var in variable_funcs:
                func = variable_funcs[var]
            else:
                return var, None, f"Unknown variable: {var}"

            result = _call_with_retries(func, var)

            if result is None:
                return var, None, f"API timeout/failure for {variable_lut.get(var, var)}"

            return var, result, None

    except Exception as e:
        return var, None, f"Error: {str(e)}"


def _call_with_retries(fn: Callable, var_name: str, retries: int = 3, base_delay: float = 1.0):
    """Call a function with exponential backoff retries."""
    for attempt in range(retries):
        try:
            return fn()
        except APIError:
            if attempt < retries - 1:
                time.sleep(base_delay * (2**attempt))
                continue
            return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(base_delay * (2**attempt))
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
) -> Tuple[pd.DataFrame, List[dict]]:
    """Extract selected covariates at grid points - PARALLELIZED point-based extraction.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest.
    variables : list[str]
        Covariate keys to extract.
    date_range : tuple[datetime, datetime]
        Date range to determine raster years.
    sample_size : int
        Target number of sample points.
    api_keys : dict[str, str]
        API keys for data sources, e.g. {"ecmwf": "my_key"}.
    progress : optional
        Progress UI object supporting set(value=int, message=str).
    max_workers : int, optional
        Maximum number of parallel workers.
    use_threading : bool, optional
        If True (default), use ThreadPoolExecutor.

    Returns
    -------
    tuple[pandas.DataFrame, list[dict]]
        Sampled covariate values at the requested grid points, and a list of
        notification dicts with keys "message", "type", "duration" to be shown
        in the Shiny session after the executor returns.
    """
    regular_vars = [v for v in variables if not v.startswith("ecmwf_")]
    ecmwf_vars = [v for v in variables if v.startswith("ecmwf_")]
    total_vars = len(regular_vars) + (1 if ecmwf_vars else 0)

    client = None

    notifications: List[dict] = []

    if ecmwf_vars:
        ecmwf_key = api_keys.get("ecmwf_api_key", "") or ""
        if not ecmwf_key.strip():
            notifications.append(
                {
                    "message": "No ECMWF API key provided. Skipping ECMWF variables.",
                    "type": "error",
                    "duration": None,
                }
            )
        else:
            client = Client(
                key=ecmwf_key,
                url="https://cds.climate.copernicus.eu/api",
                progress=False,
                sleep_max=1,
            )

    if use_threading:
        from concurrent.futures import ThreadPoolExecutor

        ExecutorClass = ThreadPoolExecutor
    else:
        ExecutorClass = ProcessPoolExecutor

    if max_workers is None:
        cpu_count = os.cpu_count() or 2
        max_workers = max(1, cpu_count - 2)

    variable_lut = {**COVARIATE_OPTIONS, **RESPONSE_OPTIONS}
    year = max(date_range[0].year, date_range[1].year)

    tz = timezone.utc

    def _to_utc(d) -> datetime:
        if not isinstance(d, datetime):
            d = datetime(d.year, d.month, d.day)
        return d.replace(tzinfo=tz) if d.tzinfo is None else d

    date_range = (_to_utc(date_range[0]), _to_utc(date_range[1]))

    # The points to sample
    grid = bbox.sampling_grid(sample_size)
    xs = grid[:, 0]
    ys = grid[:, 1]
    df = pd.DataFrame({"longitude": xs, "latitude": ys})

    # Process regular variables in parallel
    if regular_vars:
        progress.set(value=0, message="Starting extraction...")

        with ExecutorClass(max_workers=max_workers) as executor:
            future_to_var = {
                executor.submit(
                    _fetch_single_variable_points,
                    var,
                    bbox,
                    xs,
                    ys,
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
                    var_name, result, error = future.result()

                    if error:
                        notifications.append(
                            {
                                "message": f"Skipping {variable_lut.get(var_name, var_name)} — {error}",
                                "type": "warning",
                                "duration": 5,
                            }
                        )
                    elif result is not None:
                        if isinstance(result, dict):
                            # Multi-output variables (e.g. MODIS with multiple aggregations)
                            for k, v in result.items():
                                df[k] = np.asarray(v, dtype=float)
                        else:
                            df[var_name] = np.asarray(result, dtype=float)

                except Exception as e:
                    error_str = str(e)
                    if len(error_str) > 150:
                        error_str = error_str[:147] + "..."
                    notifications.append(
                        {
                            "message": f"Failed to process {var}: {error_str}",
                            "type": "error",
                            "duration": None,
                        }
                    )

                completed += 1
                progress_pct = int((completed / max(total_vars, 1)) * 90)
                progress.set(
                    value=progress_pct,
                    message=f"Extracted {completed}/{len(regular_vars)} variables...",
                )

    # Process ECMWF variables in batch
    if ecmwf_vars and client is not None:

        progress.set(
            value=int((len(regular_vars) / max(total_vars, 1)) * 90),
            message=f"Processing {len(ecmwf_vars)} ERA5 variable(s)...",
        )

        try:
            results = get_ecmwf_points(
                bbox=bbox,
                xs=xs,
                ys=ys,
                variables=ecmwf_vars,
                client=client,
                date_range=date_range,
            )
            if results is None:
                notifications.append(
                    {
                        "message": "Failed to retrieve ECMWF data. Skipped. Please check your API key and try again.",
                        "type": "warning",
                        "duration": 5,
                    }
                )
            else:
                for var, values in results.items():
                    df[var] = np.asarray(values, dtype=float)
        except Exception as e:
            error_str = str(e)
            auth_hints = (
                "401",
                "403",
                "unauthorized",
                "authentication",
                "invalid key",
                "forbidden",
            )
            if any(h in error_str.lower() for h in auth_hints):
                notifications.append(
                    {
                        "message": "ECMWF authentication failed. Please check your API key and try again.",
                        "type": "error",
                        "duration": None,
                    }
                )
            else:
                notifications.append(
                    {
                        "message": f"Error processing ECMWF data: {error_str}",
                        "type": "error",
                        "duration": None,
                    }
                )

    progress.set(value=95, message="Finalising...")
    df = df.dropna()
    progress.set(value=100, message="Complete!")

    return df, notifications
