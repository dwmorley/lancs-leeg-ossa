import pandas as pd
from src.gis.bounding_box import BoundingBox
from src.covariates.get_lulc import get_lulc
from src.covariates.get_modis import get_modis
from src.gis.make_stack import stack
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
    xyz = pd.read_csv("output/xyz.csv")  #

# STEP 2: Ecological classification

classanalysis = 0


b = 0

# STEP 3: Lattice with close pairs design for the spatial allocation of sampling sites


# STEP 4: Step 4. Adaptive sampling design

# DEBUG:
# Save each raster as GeoTIFF
# for name, raster in rasters.items():
#     filename = f"output/{name}.tif"
#     raster.rio.to_raster(filename)
#     print(f"Saved {filename}")
