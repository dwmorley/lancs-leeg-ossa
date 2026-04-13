"""Get data from ERA5-Land reanalysis via the Copernicus Climate Data Store API."""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List

import numpy as np
import xarray as xr
from ecmwf.datastores import Client

from src.constants import RESPONSE_OPTIONS
from src.utils.bounding_box import BoundingBox

os.environ.setdefault("ECCODES_DEFINITION_PATH", "")

_COLLECTION = "reanalysis-era5-land"


def _build_base_request(bbox: BoundingBox, date_range: tuple[datetime, datetime]) -> dict:
    """Build the shared CDS request dict (no variable key yet)."""
    date_start, date_end = date_range
    all_dates = [date_start + timedelta(days=i) for i in range((date_end - date_start).days + 1)]
    return {
        "year": sorted({str(d.year) for d in all_dates}),
        "month": sorted({str(d.month).zfill(2) for d in all_dates}),
        "day": sorted({str(d.day).zfill(2) for d in all_dates}),
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [bbox.ymax, bbox.xmin, bbox.ymin, bbox.xmax],
    }


def _download_to_tempfile(client: Client, request: dict) -> str:
    """Submit a CDS job, block until complete, download to a temp file, return its path."""
    remote = client.submit(_COLLECTION, request)
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp_path = tmp.name
    remote.download(tmp_path)  # blocks until the job completes, handles retries
    return tmp_path


def _read_netcdf_file(tmp_path: str, cds_var_names: list[str]) -> dict[str, xr.DataArray]:
    """Open a NetCDF4 file and return one time-averaged DataArray per variable."""
    try:
        ds = xr.open_dataset(tmp_path, engine="netcdf4")
    except (OSError, Exception) as e:
        # If netcdf4 fails, try cfgrib (for GRIB files)
        if "Unknown file format" in str(e) or "NetCDF" in str(e):
            try:
                ds = xr.open_dataset(tmp_path, engine="cfgrib")
            except Exception:
                raise e  # Re-raise original error if cfgrib also fails
        else:
            raise

    rename_map = {}
    if "latitude" in ds.dims:
        rename_map["latitude"] = "y"
    if "longitude" in ds.dims:
        rename_map["longitude"] = "x"
    if rename_map:
        ds = ds.rename(rename_map)

    # Reverse lookup: normalised long_name → cds_request_name
    # e.g. "Soil temperature level 3" → "soil_temperature_level_3"
    long_name_lut = {n.lower().replace(" ", "_"): n for n in cds_var_names}
    _categorical = {k.removeprefix("ecmwf_") for k in RESPONSE_OPTIONS}

    results: dict[str, xr.DataArray] = {}
    for short_name in ds.data_vars:
        da = ds[short_name]
        attr_long = da.attrs.get("long_name", "")
        cds_name = long_name_lut.get(attr_long.lower().replace(" ", "_"), short_name)

        da = da.astype(float)

        if "valid_time" in da.dims:
            da = da.rename({"valid_time": "time"})

        if "time" in da.dims and da.sizes["time"] > 1:
            if cds_name in _categorical:
                from scipy import stats as _stats

                arr = da.values
                mode_vals = _stats.mode(arr, axis=0, keepdims=False, nan_policy="omit").mode
                da = xr.DataArray(mode_vals, dims=["y", "x"], coords={"y": da.y, "x": da.x})
            else:
                da = da.mean(dim="time", skipna=True)
        elif "time" in da.dims:
            da = da.isel(time=0)

        if cds_name == "soil_type":
            da = da.where(da != 0)
        elif cds_name in ("type_of_high_vegetation", "type_of_low_vegetation"):
            da = da.where(~da.isin([14, 15]))

        results[cds_name] = da.load()

    return results


def _fetch_batch(
    client: Client,
    request: dict,
    cds_var_names: list[str],
    bbox: BoundingBox,
) -> dict[str, xr.DataArray]:
    """Submit one CDS request for multiple variables, return dict of DataArrays."""
    tmp_path = _download_to_tempfile(client, {**request, "variable": cds_var_names})
    try:
        return _read_netcdf_file(tmp_path, cds_var_names)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _fetch_batch_with_static_fallback(
    client: Client,
    base_request: dict,
    cds_var_names: list[str],
    bbox: BoundingBox,
) -> dict[str, xr.DataArray]:
    """Try a batch request; if it fails (static fields), retry variable-by-variable.

    Static fields like ``lake_total_depth`` reject month/day/time parameters.
    When the whole batch fails we fall back to individual requests so one
    awkward variable doesn't block the rest.
    """
    try:
        return _fetch_batch(client, base_request, cds_var_names, bbox)
    except Exception as batch_err:
        if not (
            "MultiAdaptorNoDataError" in str(batch_err)
            or "400" in str(batch_err)
            or "failed" in str(batch_err).lower()
        ):
            raise

    # Batch failed — retry each variable individually, using year-only for static fields
    static_request = {k: v for k, v in base_request.items() if k not in ("month", "day", "time")}

    results: dict[str, xr.DataArray] = {}
    with ThreadPoolExecutor(max_workers=min(len(cds_var_names), 4)) as pool:
        futures = {
            pool.submit(
                _fetch_one_with_fallback, client, base_request, static_request, var, bbox
            ): var
            for var in cds_var_names
        }
        for f in as_completed(futures):
            try:
                results.update(f.result())
            except Exception:
                pass

    return results


def _fetch_one_with_fallback(
    client: Client,
    base_request: dict,
    static_request: dict,
    cds_var: str,
    bbox: BoundingBox,
) -> dict[str, xr.DataArray]:
    """Try a single-variable batch; fall back to the static (year-only) request."""
    try:
        return _fetch_batch(client, base_request, [cds_var], bbox)
    except Exception as e:
        if "MultiAdaptorNoDataError" in str(e) or "400" in str(e) or "failed" in str(e).lower():
            return _fetch_batch(client, static_request, [cds_var], bbox)
        raise


def get_ecmwf_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    variables: List[str],
    client: Client,
    date_range: tuple[datetime, datetime],
) -> dict[str, np.ndarray] | None:
    """Sample ECMWF ERA5-Land values at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest.
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    variables : list[str]
        ECMWF variable keys to fetch (e.g. ['ecmwf_runoff']).
    date_range : tuple[datetime, datetime]
        Start and end of the date range (inclusive).

    Returns
    -------
    dict[str, np.ndarray] or None
        {variable_key: values_array} at each sample point, or None on auth failure.
        Every point is guaranteed a value (NaN where no data).
    """
    base_request = _build_base_request(bbox, date_range)
    cds_vars = [v.removeprefix("ecmwf_") for v in variables]
    var_lut = dict(zip(cds_vars, variables))  # cds_name → app key

    # Single batch submission for all variables
    da_dict = _fetch_batch_with_static_fallback(client, base_request, cds_vars, bbox)

    if not da_dict:
        return None

    x_pts = xr.DataArray(xs, dims="points")
    y_pts = xr.DataArray(ys, dims="points")

    results: dict[str, np.ndarray] = {}
    for cds_var, da in da_dict.items():
        if da is None or da.size == 0:
            continue
        app_key = var_lut.get(cds_var, cds_var)
        sampled = da.sel(x=x_pts, y=y_pts, method="nearest").values.astype(float)
        results[app_key] = sampled

    return results
