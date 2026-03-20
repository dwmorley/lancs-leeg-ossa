"""Runner utilities for analysis workflows (QDA, LCP, ASD) used by OSSA."""

import numpy as np
import pandas as pd
import xarray as xr

from src.sampling.asd_routine import glmmPQL_via_rpy2
from src.sampling.luqdaloop_routine import luqdaloop, plot_wilks_lambda


def do_qda(
    df: pd.DataFrame, response: str, nx: int, nn: float
) -> dict[str, pd.DataFrame | xr.DataArray | dict]:
    """Run QDA classification on the provided data and determine the best number of classes."""
    X = df.drop(columns=["longitude", "latitude", response]).values
    y = df[response].values.astype(int).astype(str)
    spatial_grid = df[["longitude", "latitude"]].values

    # Do QDA
    class_analysis = luqdaloop(X=X, y=y, grid=spatial_grid, nn=nn, nx=nx)

    # Find QDA-Wilks defined best class
    wilks_values = class_analysis["WilksSummary"].loc["Wilks"].values
    wilks_diff = wilks_values[1 : nx - 1] - wilks_values[2:nx]
    best_idx = int(np.argmax(wilks_diff))
    best = best_idx + 3
    best_key = f"{best}cluster"

    # Make the overall Wilks plot
    rank_deficient = class_analysis.get("ExcludedClusters")
    if rank_deficient is not None:
        indx = 2 + X.shape[1]
        n_excluded = len(np.unique(rank_deficient[:, indx]))
    else:
        n_excluded = 0

    unique_classes = class_analysis["NewData"][best_key].unique()
    n_classes = len(unique_classes) - n_excluded
    wilks = class_analysis["WilksSummary"].loc["Wilks"][1::]
    fig = plot_wilks_lambda(wilks, n_classes, n_excluded)

    return {
        "best_n_classes": n_classes,
        "wilks_plot": fig,
        "class_analysis": class_analysis,
    }


def do_lcp():
    """Run LCP sampling on a provided classification map."""
    pass


# def do_qda_and_lcp(
#     df: pd.DataFrame,
#     nx: int,
#     nn: float,
#     delta: float,
#     zeta: float,
#     total: int,
#     grid: float,
# ) -> dict[str, pd.DataFrame | xr.DataArray | dict]:
#     """Run QDA classification followed by LCP sampling on the provided data.

#     Parameters
#     ----------
#     df : pd.DataFrame
#         Containing columns 'longitude', 'latitude', 'landcover', and
#         predictor variables for QDA.
#     nx : int
#         Max number of QDA classes to consider in the classification loop.
#     nn : float
#         Nearest neighbor distance parameter for QDA classification.
#     delta : float
#         Minimum separation distance for inhibitory points in LCP sampling
#     zeta : float
#         Maximum distance used when creating closed pairs in LCP sampling
#     total : int
#         Target total number of sample points for LCP sampling.
#     grid : float
#         Fraction of 'G' to 'I' points

#     """
#     # Assuming df has already been validated.
#     response = [k for k in RESPONSE_OPTIONS.keys() if k in df.columns]
#     response = response[0]

#     X = df.drop(columns=["longitude", "latitude", response]).values
#     y = df[response].values.astype(int).astype(str)
#     spatial_grid = df[["longitude", "latitude"]].values

#     # Do QDA
#     class_analysis = luqdaloop(X=X, y=y, grid=spatial_grid, nn=nn, nx=nx)

#     new_data = class_analysis["NewData"][["grid1", "grid2", "BestClass"]].rename(
#         columns={"grid1": "x", "grid2": "y"}
#     )

#     # Account for rank deficiency
#     rank_deficient = class_analysis.get("ExcludedClusters")
#     if rank_deficient is not None:
#         indx = 2 + X.shape[1]
#         n_excluded = len(np.unique(rank_deficient[:, indx]))
#     else:
#         n_excluded = 0

#     unique_classes = new_data["BestClass"].unique()
#     n_classes = len(unique_classes) - n_excluded

#     # Map string labels to their index in unique_classes (sequential integer values)
#     label_to_index = {cls: i for i, cls in enumerate(unique_classes)}
#     new_data["id"] = new_data["BestClass"].map(label_to_index)

#     wilks = class_analysis["WilksSummary"].loc["Wilks"][1::]
#     fig = plot_wilks_lambda(wilks, n_classes, n_excluded)
#     map_raster = newdata_to_raster(new_data)

#     # Generate LCP sites
#     sites = lcp(map_raster, delta=delta, zeta=zeta, total=total, grid=grid)

#     return {
#         "new_data": new_data,
#         "best_n_classes": n_classes,
#         "wilks_plot": fig,
#         "class_analysis": class_analysis,
#         "map_raster": map_raster,
#         "lcp_sites": sites,
#     }


def do_asd(
    df: pd.DataFrame,
    formulaf: str,
    formular: str,
    target: str,
    total: int = 15,
    delta: float = 0.01,
    on_progress=None,
) -> dict[str, pd.DataFrame | xr.DataArray]:
    """Perform ASD sampling and analysis on the provided dataset."""
    debug = True
    if debug:
        df = pd.read_csv("test_data/benin.csv")
        area = pd.read_csv("test_data/beningrid.csv")
        formulaf = "AnGam~Week+Elev+Soil"
        formular = "~1|LCD"
    else:
        area = df[["longitude", "latitude"]]

    map_raster, sites = glmmPQL_via_rpy2(
        formulaf=formulaf,
        formular=formular,
        data=df,
        area=area,
        target=target,
        total=total,
        delta=delta,
        on_progress=on_progress,
    )

    return {
        "map_raster": map_raster,
        "asd_sites": sites,
    }
