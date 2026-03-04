"""Fetch GRIP road density rasters for an AOI."""

import os
import zipfile

import requests
import xarray as xr

from src.utils.bounding_box import BoundingBox
from src.utils.downloads import get_downloads_folder


def get_roaddensity(
    bbox: BoundingBox,
    road_type: int = 0,
) -> xr.DataArray:
    """Return road density raster clipped to the bounding box.

    Road density data from the Global Roads Inventory Project (GRIP), version 4.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip to.
    road_type : int, optional
        Road type code (default 0). Options are:

        0 - All road types combined (total density).
        1 - Highways.
        2 - Primary roads.
        3 - Secondary roads.
        4 - Tertiary roads.
        5 - Local roads.

    Returns
    -------
    xarray.DataArray
        Clipped road density raster.
    """
    type_str = "total" if road_type == 0 else f"tp{road_type}"

    # Download the zip file
    zipfilename = f"GRIP4_density_{type_str}.zip"
    url = f"https://dataportaal.pbl.nl/downloads/GRIP4/{zipfilename}"
    downloaddir = get_downloads_folder()
    downloaddir.mkdir(parents=True, exist_ok=True)
    zippath = downloaddir / zipfilename

    response = requests.get(url, verify=False)
    with open(zippath, "wb") as f:
        f.write(response.content)

    exdir = downloaddir / f"roaddensity_{type_str}"
    os.makedirs(exdir, exist_ok=True)

    with zipfile.ZipFile(zippath, "r") as zip_ref:
        zip_ref.extractall(exdir)

    # Get rasters
    asc_file = next(f for f in os.listdir(exdir) if f.endswith("dens_m_km2.asc"))
    raster = xr.open_dataarray(os.path.join(exdir, asc_file), engine="rasterio")
    raster.rio.write_crs("EPSG:4326", inplace=True)
    raster_clipped = raster.rio.clip_box(
        bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax, allow_one_dimensional_raster=True
    )

    try:
        os.remove(zippath)
        for f in os.listdir(exdir):
            os.remove(os.path.join(exdir, f))
        os.rmdir(exdir)
    except Exception:
        pass

    return raster_clipped


if __name__ == "__main__":

    bbox = BoundingBox([-2.502, 42.698, -2.2, 43.0850])

    merged = get_roaddensity(bbox=bbox)

    merged.rio.write_crs("EPSG:4326", inplace=True)
    merged.rio.to_raster("roads.tif", compress="deflate", COMPRESS_LEVEL=9)
