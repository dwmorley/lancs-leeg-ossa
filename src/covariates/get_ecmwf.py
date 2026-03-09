"""Get data from ERA5-Land reanalysis via the Copernicus Climate Data Store API."""

import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List

import cfgrib
import xarray as xr
from ecmwf.datastores import Client
from requests.exceptions import HTTPError

from src.utils.bounding_box import BoundingBox


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
            ): var
            for var in variables
        }
        for future in as_completed(futures):
            var_key, da = future.result()
            rasters[f"{var_key}_mean"] = da

    return rasters


def _fetch_variable(client, collection_id, request, var_key) -> tuple[str, xr.DataArray]:
    """Submit and download a single variable request, returning (var_key, DataArray)."""
    with tempfile.NamedTemporaryFile(suffix=".grib", delete=True) as tmp:
        remote = client.submit(collection_id, request)
        remote.download(tmp.name)
        datasets = cfgrib.open_datasets(tmp.name)

        das = []
        for ds in datasets:
            if (ds.longitude > 180).any():
                ds = ds.assign_coords(longitude=(ds.longitude + 180) % 360 - 180)
                ds = ds.sortby("longitude")
            v = list(ds.data_vars)[0]
            da = ds[v].load()
            das.append(da)

        da = (
            das[0]
            if len(das) == 1
            else xr.merge(das, compat="override", join="override")[list(das[0].data_vars)[0]]
        )
        da = da.rename({"longitude": "x", "latitude": "y"})
        if "time" in da.dims:
            da = da.mean(dim="time", skipna=True)

    return var_key, da


if __name__ == "__main__":
    bbox = BoundingBox([-5, 21, -1.2416, 23.8564])

    start = datetime.strptime("2019-01-01", "%Y-%m-%d")
    end = datetime.strptime("2019-12-31", "%Y-%m-%d")

    r = get_ecmwf(
        bbox=bbox,
        variables=["ecmwf_snow_albedo", "ecmwf_evaporation_from_bare_soil"],
        api_keys={"ecmwf_api_key": "f12aaef4-xxxxxxxxx"},
        date_range=(start, end),
    )

    import rasterio  # noqa: F401

    r["ecmwf_snow_albedo_mean"].rio.write_crs("epsg:4326").rio.to_raster("ecmwf_snow_albedo.tif")
    r["ecmwf_evaporation_from_bare_soil_mean"].rio.write_crs("epsg:4326").rio.to_raster(
        "ecmwf_evaporation_from_bare_soil.tif"
    )
