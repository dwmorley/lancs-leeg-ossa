from typing import Literal

import numpy as np
import planetary_computer
import pystac_client
import rioxarray  # noqa: F401
import stackstac
import xarray

from src.gis.bounding_box import BoundingBox

# TODO: This dataset has a known issue with 1 pixel wide NaN edge artefacts


def get_dem(
    bbox: BoundingBox,
    res: int = Literal[30, 90],
) -> xarray.DataArray:

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=[f"cop-dem-glo-{res}"],
        bbox=bbox.to_list(),
    )

    items = [item for item in search.items()]

    stack = stackstac.stack(
        items,
        fill_value=np.nan,
        bounds_latlon=bbox.to_tuple(),
        epsg=4326,
    )
    da_raster = stack.mean(dim=["time"]).compute()

    da_raster.rio.write_crs("epsg:4326")
    # da_raster.rio.to_raster(f"dem_{res}m.tif", compress="deflate", COMPRESS_LEVEL=9)

    return da_raster


if __name__ == "__main__":
    get_dem(
        bbox=BoundingBox([-2.502, 42.698, -2.2, 43.0850]),
        res=30,
    )
