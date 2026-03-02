import numpy as np
import planetary_computer
import pystac_client
import stackstac
import xarray

from src.utils.bounding_box import BoundingBox


def get_lulc(
    bbox: BoundingBox,
    year: int = 2023,
) -> xarray.DataArray:
    """
    Impact Observatory, Microsoft, and Esri. (2023). Global Land Use Land Cover (LULC) Dataset, 10m Resolution (2017-2023).
    ESA Sentinel-2 Imagery. Available at: https://planetarycomputer.microsoft.com/

    https://planetarycomputer.microsoft.com/dataset/io-lulc-annual-v02

    :param bbox: The BoundingBox
    :param year: Has to be between 2017 and 2023.
    :return: a land use land cover (LULC) raster for the specified area of interest (AOI) and year.
    """

    if 2017 > year > 2023:
        raise ValueError("Year must be between 2017 and 2023.")

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=["io-lulc-annual-v02"],
        bbox=bbox.to_list(),
        datetime=f"{year}",
    )
    items = [item for item in search.items() if int(item.id.split("-")[1]) == year]

    stack = stackstac.stack(
        items,
        dtype=np.ubyte,
        fill_value=np.uint8(0),
        bounds_latlon=bbox.to_tuple(),
        sortby_date=False,
        rescale=False,
        epsg=4326,
    )

    # Mosaic overlapping tiles: use mode across time dimension for each pixel
    da_raster = stack.max(dim="time").compute().squeeze()

    # Set values 1 - water and 0 - no data to np.nan
    da_raster = da_raster.where(~da_raster.isin([0, 1]), np.nan)

    # Set class names as attributes
    collection = catalog.get_collection("io-lulc-9-class")
    x = collection.item_assets["data"]
    class_names = {x["values"][0]: x["summary"] for x in x.properties["file:values"]}
    da_raster.attrs["class"] = class_names
    da_raster.attrs["start_time"] = f"{year}-01-01T00:00:00Z"
    da_raster.attrs["end_time"] = f"{year}-12-31T00:00:00Z"
    da_raster["band"] = "landcover"

    return da_raster


if __name__ == "__main__":
    get_lulc(
        # bbox=BoundingBox([-5, 31.0, 8.2968, 32.0]),
        bbox=BoundingBox([1.5, 6.0, 2.1, 7.0]),
        year=2020,
    )
