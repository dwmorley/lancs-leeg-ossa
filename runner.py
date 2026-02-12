import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import xarray as xr

from src.covariates.get_lulc import get_lulc
from src.covariates.get_modis import get_modis
from src.gis.bounding_box import BoundingBox
from src.gis.make_stack import stack
from src.sampling.luqdaloop import luqdaloop
from src.sampling.raster_to_grid import extract

SKIP_RS = True


# ====== User defined input =======
extents = [1.5, 6.2, 1.7, 6.5]
year = 2021
modis_variables = ["ET_500m", "LST_Day_1KM"]
samping_grid_size = (70, 70)

bbox = BoundingBox(extents)
# ================================

# STEP 1: Extract data from rasters
if not SKIP_RS:

    # Get the LCLU raster as template for alignment
    print("getting LULC raster...")
    rasters = {
        "lulc": get_lulc(
            bbox=bbox,
            year=year,
        )
    }

    # Get the MODIS rasters
    for variable in modis_variables:
        print(f"getting {variable} raster...")
        da_dict = get_modis(
            bbox=bbox,
            variable=variable,
            year=year,
        )
        rasters.update(da_dict)

    # Raster stack of all covariates
    stack = stack(rasters)

    grid = bbox.sampling_grid(nx=samping_grid_size[0], ny=samping_grid_size[1])
    xyz = extract(stack, grid)
    xyz.to_csv("output/xyz.csv")
else:
    xyz = pd.read_csv("output/xyz.csv", index_col=0)

# Possibly OK TO HERE!!!

# STEP 2: Ecological classification

X = xyz.drop(columns=["lulc", "longitude", "latitude"]).values
y = xyz["lulc"].values.astype(int).astype(str)
grid = xyz[["longitude", "latitude"]].values

class_analysis = luqdaloop(X, y, grid)

best_n_cluster = 3
df = class_analysis["NewData"]

# Create raster from dataframe
x_coords = np.sort(df["grid1"].unique())
y_coords = np.sort(df["grid2"].unique())
z_grid = np.full((len(y_coords), len(x_coords)), np.nan)
x_idx = np.searchsorted(x_coords, df["grid1"].values)
y_idx = np.searchsorted(y_coords, df["grid2"].values)

# Convert unique BestClass values to sequential integers
unique_classes = np.sort(df["BestClass"].unique())
class_map = {cls: i for i, cls in enumerate(unique_classes)}
z_values = df["BestClass"].map(class_map).values

z_grid[y_idx, x_idx] = z_values
raster = xr.DataArray(z_grid, coords={"y": y_coords, "x": x_coords}, dims=["y", "x"])
raster.rio.write_crs("EPSG:4326", inplace=True)
raster.rio.to_raster("output/best_class.tif")


# - The number of classes, best_idx to extract from 'class_analysis'
# - The confusion matrix
# - The NewData
# - The Wilkes Lambda graph


b = 0

# STEP 3: Lattice with close pairs design for the spatial allocation of sampling sites


# STEP 4: Step 4. Adaptive sampling design

# DEBUG:
# Save each raster as GeoTIFF
# for name, raster in rasters.items():
#     filename = f"output/{name}.tif"
#     raster.rio.to_raster(filename)
#     print(f"Saved {filename}")
