"""Fetch GRIP road density rasters for an AOI."""

import os
import zipfile

import numpy as np
import requests

from src.utils.bounding_box import BoundingBox
from src.utils.downloads import get_downloads_folder


def get_roaddensity_points(
    bbox: BoundingBox,
    xs: np.ndarray,
    ys: np.ndarray,
    road_type: int = 0,
) -> np.ndarray:
    """Sample GRIP road density at specific lon/lat coordinates.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest (used for download only).
    xs : np.ndarray
        Longitudes (EPSG:4326) of sample points.
    ys : np.ndarray
        Latitudes (EPSG:4326) of sample points.
    road_type : int, optional
        Road type code (0 = all roads combined).

    Returns
    -------
    np.ndarray
        Road density values (m/km²) at each point (NaN where no data).
    """
    import rasterio

    type_str = "total" if road_type == 0 else f"tp{road_type}"

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

    asc_file = next(f for f in os.listdir(exdir) if f.endswith("dens_m_km2.asc"))
    asc_path = os.path.join(exdir, asc_file)

    values = np.full(len(xs), np.nan)

    with rasterio.open(asc_path) as src:
        nodata = src.nodata
        coords = list(zip(xs, ys))
        sampled = np.array([v[0] for v in src.sample(coords)], dtype=float)
        if nodata is not None:
            sampled[sampled == nodata] = np.nan
        values = sampled

    try:
        os.remove(zippath)
        for f in os.listdir(exdir):
            os.remove(os.path.join(exdir, f))
        os.rmdir(exdir)
    except Exception:
        pass

    return values
