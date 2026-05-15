"""Utilities and runner entrypoint for extraction tasks used by OSSA."""

import contextlib
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

import numpy as np
import pandas as pd
import urllib3
from ecmwf.datastores import Client
from pystac_client.exceptions import APIError
from shiny import ui

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
                print(f"Retrying {var_name} after API error (attempt {attempt + 1}/{retries})...")
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
) -> pd.DataFrame:
    """Extract selected covariates at grid points - SEQUENTIAL point-based extraction.

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

    Returns
    -------
        Sampled covariate values at the requested grid points
    """
    regular_vars = [v for v in variables if not v.startswith("ecmwf_")]
    ecmwf_vars = [v for v in variables if v.startswith("ecmwf_")]

    client = None

    if ecmwf_vars:
        ecmwf_key = api_keys.get("ecmwf_api_key", "") or ""
        if not ecmwf_key.strip():
            ui.notification_show(
                "No ECMWF API key provided. Skipping ECMWF variables.",
                type="error",
                duration=None,
            )
        else:
            client = Client(
                key=ecmwf_key,
                url="https://cds.climate.copernicus.eu/api",
                progress=False,
                sleep_max=1,
            )

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

    # Calculate total variables for unified progress bar
    total_vars = len(regular_vars) + len(ecmwf_vars)
    completed = 0

    # Create unified progress bar for all variables
    with ui.Progress(min=0, max=total_vars) as progress:
        progress.set(message="Extracting variables...")
        print("Starting extraction...")

        # Use a single executor for both regular and ECMWF variables
        cpu_count = os.cpu_count() or 1
        max_workers = max(1, cpu_count - 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            # Dictionary to track all futures
            future_to_var = {}

            # Submit regular variables to the executor
            for var in regular_vars:
                future = executor.submit(
                    _fetch_single_variable_points,
                    var,
                    bbox,
                    xs,
                    ys,
                    year,
                    date_range,
                    variable_lut,
                )
                future_to_var[future] = ("regular", var)

            # Submit ECMWF processing as a single batch task if variables exist and client is available
            if ecmwf_vars and client is not None:

                def _fetch_ecmwf_batch():
                    try:
                        print(f"Processing {len(ecmwf_vars)} ERA5 variable(s)...")
                        results = get_ecmwf_points(
                            bbox=bbox,
                            xs=xs,
                            ys=ys,
                            variables=ecmwf_vars,
                            client=client,
                            date_range=date_range,
                        )
                        if results is None:
                            return None, "Failed to retrieve ECMWF data"
                        return results, None
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
                            return None, "ECMWF authentication failed. Please check your API key."
                        return None, f"Error processing ECMWF data: {error_str}"

                ecmwf_future = executor.submit(_fetch_ecmwf_batch)
                future_to_var[ecmwf_future] = ("ecmwf", "ecmwf_batch")

            # Process results as they complete
            for future in as_completed(future_to_var):
                var_type, var_info = future_to_var[future]
                display_name = ""

                if var_type == "regular":
                    var = var_info
                    try:
                        var_name, result, error = future.result()
                        display_name = variable_lut.get(var_name, var_name)

                        if error:
                            error_msg = f"Skipping {display_name} — {error}"
                            print(f"  ERROR: {error_msg}")
                            ui.notification_show(
                                error_msg,
                                type="warning",
                                duration=None,
                            )
                        elif result is not None:
                            print(f"  SUCCESS: Added column {var_name}")
                            if isinstance(result, dict):
                                for k, v in result.items():
                                    df[k] = np.asarray(v, dtype=float)
                            else:
                                df[var_name] = np.asarray(result, dtype=float)

                    except Exception as e:
                        error_str = str(e)
                        if len(error_str) > 150:
                            error_str = error_str[:147] + "..."
                        print(f"  EXCEPTION: Failed to process {var}: {error_str}")
                        ui.notification_show(
                            f"Failed to process {var}: {error_str}",
                            type="warning",
                            duration=None,
                        )

                else:  # ecmwf batch
                    display_name = "ERA5 Variables"
                    try:
                        results, error = future.result()
                        if error:
                            print(f"  ERROR: {error}")
                            ui.notification_show(
                                error,
                                type="warning",
                                duration=None,
                            )
                        elif results is not None:
                            for var, values in results.items():
                                df[var] = np.asarray(values, dtype=float)
                            print(f"  SUCCESS: Added {len(results)} ECMWF variable(s)")

                    except Exception as e:
                        error_str = str(e)
                        if len(error_str) > 150:
                            error_str = error_str[:147] + "..."
                        print(f"  EXCEPTION: Failed to process ECMWF batch: {error_str}")
                        ui.notification_show(
                            f"Failed to process ECMWF batch: {error_str}",
                            type="warning",
                            duration=None,
                        )

                completed += 1
                progress.set(
                    completed,
                    detail=f"{completed}/{total_vars} variables, {display_name}",
                )
                print(f"Extracted {completed}/{total_vars} variables...")

    print("Complete!")

    return df
