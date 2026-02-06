import pandas as pd
import rasterio
import rioxarray  # noqa: F401
import xarray as xr

from src.covariates.bounding_box import BoundingBox
from src.covariates.get_lulc import get_lulc
from src.covariates.get_modis import get_modis

BBOX = [1.5, 6.0, 2.1, 7.0]
DATE_RANGE = "2019-01-01/2019-01-31"
YEAR = 2019


def go():

    bbox = BoundingBox(*BBOX)

    rasters = []
    rasters.append(get_lulc(bbox, YEAR))

    modis_variables = ["ET_500m", "PET_500m"]
    for variable in modis_variables:
        rasters.append(
            get_modis(
                bbox=bbox,
                variable=variable,
                date_range=DATE_RANGE,
            )
        )

    reference = rasters[0]  # Use LULC as reference for alignment

    if reference.rio.crs != "EPSG:4326":
        reference = reference.rio.reproject("EPSG:4326")

    aligned_rasters = [reference]

    for i in range(1, len(rasters)):

        if rasters[i].rio.crs is None:
            rasters[i] = rasters[i].rio.write_crs("EPSG:4326")

        aligned = rasters[i].rio.reproject_match(
            reference, resampling=rasterio.enums.Resampling.bilinear
        )
        aligned_rasters.append(aligned)

    cleaned_rasters = [
        raster.drop_vars(
            [v for v in raster.coords if v not in ["x", "y", "band"]], errors="ignore"
        )
        for raster in aligned_rasters
    ]

    stack = xr.concat(cleaned_rasters, dim="band")

    # Sampling
    xyz = bbox.sampling_grid(nx=70, ny=70)

    sampled = stack.sel(
        x=xr.DataArray(xyz[:, 0], dims="points"),
        y=xr.DataArray(xyz[:, 1], dims="points"),
        method="nearest",
    )

    df = pd.DataFrame({"longitude": xyz[:, 0], "latitude": xyz[:, 1]})
    for band_name in sampled.band.values:
        df[str(band_name)] = sampled.sel(band=band_name).values

    # Remove rows with missing values or where LULC is 0
    df = df.dropna()
    df = df[df["lulc"] != 0]

    # NEXT STEP IS QDA

    # import rioxarray
    # stack = stack.rio.write_crs("EPSG:4326")
    # for band_name in stack.band.values:
    #     band_data = stack.sel(band=band_name)
    #     band_data.rio.to_raster(f'{band_name}.tif', compress='lzw')
    #     print(f'Saved {band_name}.tif')


if __name__ == "__main__":
    go()
