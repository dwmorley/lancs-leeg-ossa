import numpy as np
import pandas as pd
import xarray as xr


def extract(
    stack: xr.DataArray,
    xyz: np.ndarray,
) -> pd.DataFrame:

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
    df = df[df["landcover"] != 0]

    return df
