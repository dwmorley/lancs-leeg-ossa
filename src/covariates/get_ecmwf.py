"""Get data from ERA5-Land reanalysis via the Copernicus Climate Data Store API."""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List

import rioxarray  # noqa: F401 - registers the .rio accessor
import xarray as xr
from ecmwf.datastores import Client
from requests.exceptions import HTTPError

from src.constants import RESPONSE_OPTIONS
from src.utils.bounding_box import BoundingBox

os.environ.setdefault("ECCODES_DEFINITION_PATH", "")


def get_ecmwf(
    bbox: BoundingBox,
    variables: List[str],
    api_keys: dict[str, str],
    date_range: tuple[datetime, datetime],
) -> dict[str, xr.DataArray] | None:
    """Fetch and prepare ECMWF ERA5-Land rasters for the AOI and variables.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to fetch the ECMWF rasters for.
    variables : list[str]
        ECMWF variable keys to fetch (e.g. 'ecmwf_runoff)
    api_keys : dict[str, str]
        API keys for data sources, e.g. {"ecmwf_api_key": "my key"}
    date_range : tuple[datetime, datetime]
        Start and end of the date range to fetch (inclusive).

    Returns
    -------
    dict[str, xarray.DataArray] or None
        Dictionary of rasters, where keys are variable names, or None if there was an error
        Time series mean averaged.
    """
    url = "https://cds.climate.copernicus.eu/api"
    api_key = api_keys.get("ecmwf_api_key")

    try:
        client = Client(key=api_key, url=url)
        client.check_authentication()
    except HTTPError:
        return None

    collection_id = "reanalysis-era5-land"

    date_start, date_end = date_range
    all_dates = [date_start + timedelta(days=i) for i in range((date_end - date_start).days + 1)]
    years = sorted({str(d.year) for d in all_dates})
    months = sorted({str(d.month).zfill(2) for d in all_dates})
    days = sorted({str(d.day).zfill(2) for d in all_dates})

    request = {
        "year": years,
        "month": months,
        "day": days,
        "time": ["00:00"],
        "data_format": "grib",
        "download_format": "unarchived",
        "area": [bbox.ymax, bbox.xmin, bbox.ymin, bbox.xmax],
    }

    rasters = {}
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                _fetch_variable,
                client,
                collection_id,
                {**request, "variable": [var.removeprefix("ecmwf_")]},
                var,
                bbox,
            ): var
            for var in variables
        }
        for future in as_completed(futures):
            var_key, da = future.result()
            rasters[var_key] = da

    return rasters


def _fetch_variable(
    client, collection_id, request, var_key, bbox: BoundingBox
) -> tuple[str, xr.DataArray]:
    """Submit and download a single variable request, returning (var_key, DataArray).

    Tries the full request (with month/day/time) first. If the CDS job fails —
    which happens for static fields like lake_total_depth that don't accept
    temporal parameters — retries with year-only.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".grib", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        da = _download_and_read(client, collection_id, request, tmp_path, bbox)
    except Exception as e:
        # Static fields (e.g. lake_total_depth) reject month/day/time —
        # retry with year only
        if "MultiAdaptorNoDataError" in str(e) or "400" in str(e) or "failed" in str(e).lower():
            static_request = {k: v for k, v in request.items() if k not in ("month", "day", "time")}
            da = _download_and_read(client, collection_id, static_request, tmp_path, bbox)
        else:
            da = xr.DataArray()  # TODO: sort skipping
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return var_key, da


def _download_and_read(client, collection_id, request, tmp_path, bbox: BoundingBox) -> xr.DataArray:
    """Submit a CDS request, download to tmp_path, and return a georeferenced DataArray."""
    remote = client.submit(collection_id, request)
    remote.download(tmp_path)

    da = rioxarray.open_rasterio(tmp_path)

    # Average multiple bands (time steps)
    var = request["variable"][0]
    if "band" in da.dims and da.sizes["band"] > 1:
        if var in RESPONSE_OPTIONS.keys():
            # if categorical, use mode
            da = da.mode(dim="band", skipna=True).isel(mode=0)
        else:
            da = da.mean(dim="band", skipna=True)
    else:
        da = da.squeeze("band", drop=True)

    # Rename spatial dims to x/y if needed
    if "x" not in da.dims or "y" not in da.dims:
        da = da.rename({list(da.dims)[-1]: "x", list(da.dims)[-2]: "y"})

    # Assign correct spatial coordinates from the bbox — GRIB2 has no embedded geotransform
    ny, nx = da.sizes["y"], da.sizes["x"]
    xs = [bbox.xmin + (i + 0.5) * (bbox.xmax - bbox.xmin) / nx for i in range(nx)]
    ys = [bbox.ymax - (i + 0.5) * (bbox.ymax - bbox.ymin) / ny for i in range(ny)]
    da = da.assign_coords(x=xs, y=ys)
    da = da.rio.write_crs("EPSG:4326")

    if var == "soil_type":
        da = da.where(da != 0)
    elif var in ["type_of_high_vegetation", "type_of_low_vegetation"]:
        da = da.where(~da.isin([14, 15]))

    return da.load()


if __name__ == "__main__":
    bbox = BoundingBox([-2, 21, -1.2416, 21.8564])
    # bbox = BoundingBox([106.54, 52.23, 107, 52.54])

    start = datetime.strptime("2019-01-01", "%Y-%m-%d")
    end = datetime.strptime("2019-12-31", "%Y-%m-%d")

    var = "soil_temperature_level_3"

    r = get_ecmwf(
        bbox=bbox,
        variables=[var],
        api_keys={"ecmwf_api_key": "f12aaef4-9be5-4fe2-a9a9-c8d99646ea6d"},
        date_range=(start, end),
    )

    import rasterio  # noqa: F401

    r[var].rio.write_crs("epsg:4326").rio.to_raster(f"{var}.tif")
