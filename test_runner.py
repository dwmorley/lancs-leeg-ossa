import geopandas as gpd  # noqa: F401
import pandas as pd

from covariates.raster_to_grid import extract
from src.covariates.get_dem import get_dem
from src.covariates.get_lulc import get_lulc
from src.covariates.make_stack import stack
from src.gis.bounding_box import BoundingBox
from src.sampling.asd import asd_plot, glmmPQL_via_rpy2
from src.sampling.lcp import lcp, plot_lcp
from src.sampling.luqdaloop import luqdaloop, newdata_to_raster, plot_wilks_lambda

SKIP_RS = False
SKIP_QDA_LCP = True
SKIP_ASD = True

# =========================================
# STEP 0: User defined input
# =========================================
extents = [1.5, 6.2, 1.7, 6.5]
year = 2021
modis_variables = ["ET_500m", "LST_Day_1KM"]
sample_size = 5000

bbox = BoundingBox(extents)

# =========================================
# STEP 1: Extract data from rasters
# =========================================
if not SKIP_RS:

    # Get the LCLU raster as template for alignment
    print("getting LULC raster...")
    rasters = {
        "landcover": get_lulc(
            bbox=bbox,
            year=year,
        )
    }

    # Get the DEM raster
    print("getting DEM raster...")
    rasters["dem"] = get_dem(
        bbox=bbox,
        res=30,
    )

    # Get the MODIS rasters
    for variable in modis_variables:
        print(f"getting {variable} raster...")
        # da_dict = get_modis(
        #     bbox=bbox,
        #     variable=variable,
        #     year=year,
        # )
        # rasters.update(da_dict)

    # Raster stack of all covariates
    stack = stack(rasters)

    grid = bbox.sampling_grid(sample_size)
    xyz = extract(stack, grid)
    xyz.to_csv("output/xyz.csv")
else:
    xyz = pd.read_csv("output/xyz.csv", index_col=0)

# =========================================
# STEP 2: Ecological classification
# =========================================

if not SKIP_QDA_LCP:

    X = xyz.drop(columns=["landcover", "longitude", "latitude"]).values
    y = xyz["landcover"].values.astype(int).astype(str)
    grid = xyz[["longitude", "latitude"]].values

    # Do QDA
    class_analysis = luqdaloop(X=X, y=y, grid=grid)

    best_n_classes = class_analysis["NewData"]["BestClass"].nunique()
    new_data = class_analysis["NewData"][["grid1", "grid2", "BestClass"]].rename(
        columns={"grid1": "x", "grid2": "y"}
    )
    unique_classes = new_data["BestClass"].unique()
    n_classes = len(unique_classes)
    new_data["id"] = new_data["BestClass"].map(
        {cls: i + 1 for i, cls in enumerate(sorted(unique_classes))}
    )

    wilks = class_analysis["WilksSummary"].loc["Wilks"][1::]
    plot_wilks_lambda(wilks, best_n_classes)

    # =========================================
    # STEP 3: Lattice with close pairs design
    # =========================================

    # Convert to raster
    map_raster = newdata_to_raster(new_data)
    map_raster.rio.to_raster("output/map_raster.tif")

    # Generate LCP sites
    sites = lcp(map_raster, delta=1.0, zeta=2.0, total=30, grid=0.7)

    # Plot the map_raster with the sites (G and I)
    plot_lcp(
        map_raster=map_raster,
        sites=sites,
        n_classes=n_classes,
    )

# =========================================
# STEP 4: Step 4. Adaptive sampling design
# =========================================

if not SKIP_ASD:

    benin = pd.read_csv("test_data/benin.csv")
    beningrid = pd.read_csv("test_data/beningrid.csv")
    target = "H"

    da, x_df = glmmPQL_via_rpy2(
        formulaf="AnGam~Week+Elev+Soil",
        formular="~1|LCD",
        data=benin,
        area=beningrid,
        target=target,
        total=15,
        delta=0.01,
    )

    asd_plot(
        plot_title="Targeting Hotspot" if target == "H" else "Targeting Uncertainty",
        da=da,
        x_df=x_df,
        z_grid=da.values,
    )
