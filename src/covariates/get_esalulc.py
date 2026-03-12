"""Fetch and prepare land use / land cover (LULC) covariates for an AOI."""

import xarray as xr

from src.utils.bounding_box import BoundingBox


def get_esalulc(
    bbox: BoundingBox,
    year: int,
    simplify: bool = True,
) -> xr.DataArray:
    """Fetch and prepare ESA CCI LULC covariates for an AOI.

    Parameters
    ----------
    bbox : BoundingBox
        Area of interest to clip the ESA CCI LULC raster to.
    year : int
        Year to extract (between 1992 and 2020).
    simplify : bool, default True
        If True, return a single DataArray with the dominant class per pixel.

    Returns
    -------
    xarray.DataArray
        ESA CCI LULC covariates clipped to the bounding box. If `simplify` is True, this will be a single DataArray with the dominant class per pixel.
        Otherwise, it will be a DataArray with one layer per class.

    """
    if 1992 > year > 2020:
        raise ValueError("Year must be between 1992 and 2020.")

    url = (
        f"https://dap.ceda.ac.uk/thredds/dodsC/neodc/esacci/land_cover/"
        f"data/pft/v2.0.81/ESACCI-LC-L4-PFT-Map-300m-P1Y-{year}-v2.0.81.nc"
    )
    ds = xr.open_dataset(url, engine="netcdf4")

    bounds_vars = [
        v for v in ds.data_vars if str(v).endswith("_bounds") or str(v).endswith("_bnds")
    ]
    ds = ds.drop_vars(bounds_vars, errors="ignore")
    ds = ds.rename({"lat": "y", "lon": "x"})
    ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=True)
    ds = ds.rio.write_crs("EPSG:4326", inplace=True)
    ds = ds.rio.clip_box(minx=bbox.xmin, miny=bbox.ymin, maxx=bbox.xmax, maxy=bbox.ymax)
    ds = ds.isel(time=0)
    da = ds.to_array()

    # Find dominant class for each pixel
    if simplify:
        vars_list = [
            "WATER",
            "BARE",
            "BUILT",
            "GRASS-MAN",
            "GRASS-NAT",
            "SHRUBS-BD",
            "SHRUBS-BE",
            "SHRUBS-ND",
            "SHRUBS-NE",
            "WATER_INLAND",
            "SNOWICE",
            "TREES-BD",
            "TREES-BE",
            "TREES-ND",
            "TREES-NE",
            "LAND",
            "WATER_OCEAN",
        ]
        stacked = xr.concat([ds[var] for var in vars_list], dim="class")
        dominant = stacked.argmax(dim="class") + 1

        class_map = {i + 1: name for i, name in enumerate(vars_list)}

        ds = dominant.rename("dominant_class").to_dataset()
        ds.attrs["class_map"] = class_map
        da = ds.to_array()

        # remove water
        da = da.where(~da.isin([1, 10, 17]))

    return da


if __name__ == "__main__":
    r = get_esalulc(
        # bbox=BoundingBox([-5, 31.0, 8.2968, 32.0]),
        bbox=BoundingBox([1.5, 6.0, 2.1, 7.0]),
        year=2020,
    )

    import rasterio  # noqa: F401

    r.rio.to_raster("esa.tif", compress="deflate", COMPRESS_LEVEL=9)
