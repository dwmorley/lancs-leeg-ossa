import numpy as np
import rasterio
import rioxarray  # noqa: F401
import xarray as xr


def stack(rasters: dict) -> xr.DataArray:
    """
    Stack multiple rasters into a single DataArray.

    Parameters
    ----------
    rasters : dict
        Dictionary where keys are layer names and values are xr.DataArray objects

    Returns
    -------
    xr.DataArray
        Stacked DataArray with dimensions (band, y, x) where band contains layer names
    """
    # Use LULC as reference for grid alignment
    reference = rasters["lulc"]

    # Ensure reference is in EPSG:4326
    if reference.rio.crs != "EPSG:4326":
        reference = reference.rio.reproject("EPSG:4326")

    # Get reference grid
    ref_y = reference.y.values
    ref_x = reference.x.values

    # Collect aligned data arrays
    band_data = []
    band_names = []

    for name, raster in rasters.items():
        # Ensure CRS is set
        if raster.rio.crs is None:
            raster = raster.rio.write_crs("EPSG:4326")

        # Reproject to match reference grid
        aligned = raster.rio.reproject_match(
            reference, resampling=rasterio.enums.Resampling.bilinear
        )

        # Extract just the data values
        data_values = aligned.values
        if data_values.ndim > 2:
            data_values = data_values.squeeze()

        band_data.append(data_values)
        band_names.append(name)

    # Stack data arrays manually and create new DataArray
    stacked_values = np.stack(band_data, axis=0)

    stacked = xr.DataArray(
        stacked_values,
        coords={
            "band": band_names,
            "y": ref_y,
            "x": ref_x,
        },
        dims=["band", "y", "x"],
    )

    # Copy CRS from reference
    stacked.rio.write_crs(reference.rio.crs, inplace=True)

    # DEBUG:
    # import rioxarray
    # stack = stacked.rio.write_crs("EPSG:4326")
    # for band_name in stack.band.values:
    #     band_data = stack.sel(band=band_name)
    #     band_data.rio.to_raster(f'{band_name}.tif', compress='lzw')
    #     print(f'Saved {band_name}.tif')

    return stacked
