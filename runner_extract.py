from datetime import datetime
from typing import List

import pandas as pd
import xarray as xr

from constants import COVARIATE_OPTIONS
from src.covariates.get_dem import get_dem
from src.covariates.get_lulc import get_lulc
from src.covariates.get_modis import get_modis
from src.covariates.get_roaddensity import get_roaddensity
from src.covariates.get_terraclimate import get_terraclimate
from src.covariates.get_worldpop import get_worldpop
from src.covariates.make_stack import stack
from src.covariates.raster_to_grid import extract
from src.gis.bounding_box import BoundingBox


def run_extraction(
    bbox: BoundingBox,
    variables: List[str],
    date_range: tuple[datetime, datetime],
    sample_size: int,
    progress=None,
) -> tuple[pd.DataFrame, xr.DataArray]:

    # The maximum year from date_range
    year = max(date_range[0].year, date_range[1].year)

    total_steps = len(variables)
    rasters = {}

    year = 2020  # ################

    variable_funcs = {
        "landcover": lambda: get_lulc(bbox=bbox, year=year),
        "dem": lambda: get_dem(bbox=bbox, res=30),
        "wp_1km_unadj": lambda: get_worldpop(bbox=bbox, year=year),
        "modis": lambda: get_modis(bbox=bbox, variable="LST_Day_1KM", year=year),
        "grip0": lambda: get_roaddensity(bbox=bbox, road_type=0),
        "grip1": lambda: get_roaddensity(bbox=bbox, road_type=1),
        "grip2": lambda: get_roaddensity(bbox=bbox, road_type=2),
        "grip3": lambda: get_roaddensity(bbox=bbox, road_type=3),
        "grip4": lambda: get_roaddensity(bbox=bbox, road_type=4),
        "grip5": lambda: get_roaddensity(bbox=bbox, road_type=5),
        "terraclimate_aet": lambda: get_terraclimate(
            bbox=bbox, variable="aet", year=year
        ),
        "terraclimate_def": lambda: get_terraclimate(
            bbox=bbox, variable="def", year=year
        ),
        "terraclimate_pet": lambda: get_terraclimate(
            bbox=bbox, variable="pet", year=year
        ),
        "terraclimate_ppt": lambda: get_terraclimate(
            bbox=bbox, variable="ppt", year=year
        ),
        "terraclimate_q": lambda: get_terraclimate(bbox=bbox, variable="q", year=year),
        "terraclimate_soil": lambda: get_terraclimate(
            bbox=bbox, variable="soil", year=year
        ),
        "terraclimate_srad": lambda: get_terraclimate(
            bbox=bbox, variable="srad", year=year
        ),
        "terraclimate_swe": lambda: get_terraclimate(
            bbox=bbox, variable="swe", year=year
        ),
        "terraclimate_tmax": lambda: get_terraclimate(
            bbox=bbox, variable="tmax", year=year
        ),
        "terraclimate_tmin": lambda: get_terraclimate(
            bbox=bbox, variable="tmin", year=year
        ),
        "terraclimate_vap": lambda: get_terraclimate(
            bbox=bbox, variable="vap", year=year
        ),
        "terraclimate_vpd": lambda: get_terraclimate(
            bbox=bbox, variable="vpd", year=year
        ),
        "terraclimate_ws": lambda: get_terraclimate(
            bbox=bbox, variable="ws", year=year
        ),
        "terraclimate_pdsi": lambda: get_terraclimate(
            bbox=bbox, variable="pdsi", year=year
        ),
    }

    for i, var in enumerate(variables):
        if progress:
            progress.set(
                value=int((i / total_steps) * 100),
                message=f"Processing {COVARIATE_OPTIONS[var]}...",
            )
        func = variable_funcs.get(var)
        if func:
            rasters[var] = func()
        else:
            raise ValueError(f"Unknown variable: {var}")

    stacked = stack(rasters)

    grid = bbox.sampling_grid(sample_size)
    xyz = extract(stacked, grid)

    progress.set(value=100, message="Finalising...")

    return xyz, stacked
