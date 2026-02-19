import platform
from pathlib import Path
from typing import List

import pandas as pd

from src.covariates.get_dem import get_dem
from src.covariates.get_lulc import get_lulc

# from src.covariates.get_modis import get_modis
from src.covariates.make_stack import stack
from src.covariates.raster_to_grid import extract
from src.gis.bounding_box import BoundingBox


def run_extraction(
    bbox: BoundingBox,
    variables: List[str],
    date_range: str,
    sample_size: int,
    save_stack: bool,
    save_csv: bool,
    progress=None,
) -> pd.DataFrame:

    year = 2021  # TODO: IS HARDTYPED

    total_steps = len(variables)
    rasters = {}

    for i, var in enumerate(variables):
        if progress:
            progress.set(
                value=int((i / total_steps) * 100), message=f"Processing {var}..."
            )

        if var == "landcover":
            rasters["landcover"] = get_lulc(
                bbox=bbox,
                year=year,
            )
        elif var == "dem":
            rasters["dem"] = get_dem(
                bbox=bbox,
                res=30,
            )
        elif var == "modis":
            pass

        else:
            raise ValueError(f"Unknown variable: {var}")

    stacked = stack(rasters)

    # Sample
    grid = bbox.sampling_grid(sample_size)
    xyz = extract(stacked, grid)

    # ts = datetime.now().strftime("%d%m%y_%H%M")
    ts = "XXXXXXX"
    if save_stack:
        progress.set(value=100, message="Saving...")
        fn = get_downloads_folder() / f"ossa_rasters_{ts}.tif"
        stacked_ds = stacked.to_dataset(dim="band")
        stacked_ds.rio.to_raster(str(fn), compress="deflate", COMPRESS_LEVEL=9)
    if save_csv:
        fn = get_downloads_folder() / f"ossa_extracted_{ts}.csv"
        xyz.to_csv(fn, index=False)

    else:
        progress.set(value=100, message="Finalising...")

    return xyz


def get_downloads_folder():
    """Get the Downloads folder path for the current platform."""
    if platform.system() == "Windows":
        import winreg

        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return Path(location)
    else:
        # macOS and Linux
        return Path.home() / "Downloads"
