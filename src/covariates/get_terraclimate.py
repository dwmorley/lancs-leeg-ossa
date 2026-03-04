"""Utilities to download and prepare TerraClimate covariates for an AOI."""

import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_terraclimate(
    bbox: BoundingBox,
    variable: str = "aet",
    year: int = 2024,
) -> xr.DataArray:
    """Fetch and prepare a yearly TerraClimate variable clipped to the AOI.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip the TerraClimate raster to.
    variable : str, optional
        TerraClimate variable name (default: 'aet').
    year : int, optional
        Year to extract (default: current year).

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

    url = f"http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_terraclimate_{variable}_1958_CurrentYear_GLOBE.nc"

    ds = xr.open_dataset(url, chunks={"time": 12, "lat": 500, "lon": 500})
    da = ds[variable].sel(time=slice(f"{year}-01-01", f"{year}-12-31"))

    da.rio.write_crs("EPSG:4326", inplace=True)
    da_clipped = da.rio.clip_box(
        bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
    )

    da_clipped = da_clipped.mean(dim="time", skipna=True)

    # Rename lat/lon to x/y for consistency with other raster sources
    da_clipped = da_clipped.rename({"lon": "x", "lat": "y"})

    return da_clipped


if __name__ == "__main__":

    bbox = BoundingBox([-2.502, 42.698, -2.2, 43.0850])

    merged = get_terraclimate(
        bbox=bbox,
        variable="aet",
    )

    merged.rio.write_crs("EPSG:4326", inplace=True)
    merged.rio.to_raster("terraclimate_aet.tif", compress="deflate", COMPRESS_LEVEL=9)
