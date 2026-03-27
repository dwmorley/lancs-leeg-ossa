"""Utilities to download and prepare TerraClimate covariates for an AOI."""

from datetime import datetime

import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_terraclimate(
    bbox: BoundingBox,
    variable: str,
    date_range: tuple[datetime, datetime],
) -> xr.DataArray:
    """Fetch and prepare a yearly TerraClimate variable clipped to the AOI.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip the TerraClimate raster to.
    variable : str
        TerraClimate variable name
    date_range : tuple[datetime, datetime]
        Months to extract

    Returns
    -------
    xarray.DataArray
        Mean annual TerraClimate variable clipped to the bounding box.
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

    url = f"http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_terraclimate_{variable}_1950_CurrentYear_GLOBE.nc"

    ds = xr.open_dataset(url, chunks={"time": 12, "lat": 500, "lon": 500})
    da = ds[variable].sel(
        time=slice(date_range[0].strftime("%Y-%m-%d"), date_range[1].strftime("%Y-%m-%d"))
    )

    da.rio.write_crs("EPSG:4326", inplace=True)
    da_clipped = da.rio.clip_box(
        bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
    )

    # TODO: Only returning the mean for now.
    da_clipped = da_clipped.mean(dim="time", skipna=True)
    da_clipped = da_clipped.rename({"lon": "x", "lat": "y"})

    return da_clipped


if __name__ == "__main__":

    bbox = BoundingBox([-2.502, 42.698, -2.2, 43.0850])

    start = datetime.strptime("2019-01-01", "%Y-%m-%d")
    end = datetime.strptime("2019-03-17", "%Y-%m-%d")

    merged = get_terraclimate(
        bbox=bbox,
        variable="ppt",
        date_range=(start, end),
    )

    merged.rio.write_crs("EPSG:4326", inplace=True)
    merged.rio.to_raster("terraclimate.tif", compress="deflate", COMPRESS_LEVEL=9)
