"""Download and process SoilGrids data for a given bounding box and variable."""

import os
import re
import tempfile

import rioxarray
import xarray as xr
from soilgrids import SoilGrids

from src.utils.bounding_box import BoundingBox


def get_soilgrids(bbox: BoundingBox, variable: str) -> xr.DataArray:
    """Download SoilGrids data for a variable and return a thickness-weighted average over the 0-30cm profile.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to fetch the SoilGrids data for.
    variable : str
        SoilGrids variable to fetch (e.g. 'phh2o')

    Returns
    -------
    xarray.DataArray
        Thickness-weighted average of the variable over the 0-30cm soil profile

    """
    soil_grids = SoilGrids()

    variable = variable.removeprefix("sg_")

    _, coverages = SoilGrids()._get_service_and_coverage_list(variable)
    mean_coverages = [c for c in coverages if c.endswith("_mean")]

    west, south, east, north = bbox.to_soilgrids()

    layers = []
    weights = []
    for coverage_id in mean_coverages:
        thickness = _parse_thickness(coverage_id)
        if thickness is None:
            continue
        da = _fetch_layer(soil_grids, variable, coverage_id, west, south, east, north)
        layers.append(da)
        weights.append(thickness)

    if not layers:
        raise ValueError(f"No layers found within 0-30cm for variable '{variable}'")

    total_weight = sum(weights)
    weighted: xr.DataArray = xr.zeros_like(layers[0])
    for da, w in zip(layers, weights):
        weighted = weighted + da * (w / total_weight)
    weighted.attrs["long_name"] = f"{variable} 0-30cm weighted mean"
    weighted.attrs["weights_cm"] = weights

    return weighted


def _parse_thickness(coverage_id: str) -> int | None:
    """Extract thickness in cm from a coverage_id like 'phh2o_0-5cm_mean'.

    Returns None if the bottom depth exceeds 30cm.
    """
    match = re.search(r"_(\d+)-(\d+)cm_", coverage_id)
    if not match:
        return None
    top, bottom = int(match.group(1)), int(match.group(2))
    if top >= 30:
        return None

    bottom = min(bottom, 30)
    return bottom - top


def _fetch_layer(
    soil_grids: SoilGrids,
    variable: str,
    coverage_id: str,
    west: float,
    south: float,
    east: float,
    north: float,
) -> xr.DataArray:
    """Download a single SoilGrids layer and return as a reprojected DataArray."""
    homolosine = "+proj=igh +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        soil_grids.get_coverage_data(
            service_id=variable,
            coverage_id=coverage_id,
            west=west,
            south=south,
            east=east,
            north=north,
            crs="urn:ogc:def:crs:EPSG::152160",
            output=tmp_path,
        )
        da = rioxarray.open_rasterio(tmp_path).squeeze().astype(float)
        da = da.rio.write_crs(homolosine)
        da = da.rio.reproject("EPSG:4326")
        da = da.where(da != -32768)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return da


if __name__ == "__main__":
    bbox = BoundingBox([-2.7, 43.2, -2.502, 43.5])
    r = get_soilgrids(bbox=bbox, variable="phh2o")
    r.rio.to_raster("sg.tif", compress="deflate", COMPRESS_LEVEL=9)
