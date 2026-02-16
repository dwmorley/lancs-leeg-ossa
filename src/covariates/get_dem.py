from typing import Literal

import numpy as np
import planetary_computer
import pystac_client
import stackstac
import xarray

from src.gis.bounding_box import BoundingBox


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

    return da_raster


if __name__ == "__main__":
    get_dem(
        bbox=BoundingBox([1.5, 6.0, 2.1, 7.0]),
        res=30,
    )
