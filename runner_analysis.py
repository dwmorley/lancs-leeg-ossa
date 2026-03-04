"""Runner utilities for analysis workflows (QDA, LCP, ASD) used by OSSA."""

from typing import Any

import numpy as np
import pandas as pd

from src.sampling.asd_routine import asd_plot, glmmPQL_via_rpy2  # noqa: F401
from src.sampling.lcp_routine import lcp
from src.sampling.luqdaloop_routine import plot_wilks_lambda  # noqa: F401
from src.sampling.luqdaloop_routine import luqdaloop, newdata_to_raster


def do_qda_and_lcp(df: pd.DataFrame, nx: int, nn: float) -> None:
    """Run QDA classification followed by LCP sampling on the provided data.

    Parameters
    ----------
    df : pd.DataFrame
        Containing columns 'longitude', 'latitude', 'landcover', and
        predictor variables for QDA.
    nx : int
        Max number of QDA classes to consider in the classification loop.
    nn : float
        Nearest neighbor distance parameter for QDA classification.

    """
    X = df.drop(columns=["longitude", "latitude", "landcover"]).values
    y = df["landcover"].values.astype(int).astype(str)
    grid = df[["longitude", "latitude"]].values

    # Do QDA
    class_analysis = luqdaloop(X=X, y=y, grid=grid, nn=nn, nx=nx)

    new_data = class_analysis["NewData"][["grid1", "grid2", "BestClass"]].rename(
        columns={"grid1": "x", "grid2": "y"}
    )

    # Account for rank deficiency
    rank_deficient = class_analysis.get("ExcludedClusters")
    if rank_deficient is not None:
        indx = 2 + X.shape[1]
        n_excluded = len(np.unique(rank_deficient[:, indx]))
    else:
        n_excluded = 0

    unique_classes = new_data["BestClass"].unique()
    n_classes = len(unique_classes) - n_excluded

    # Map string labels to their index in unique_classes (sequential integer values)
    label_to_index = {cls: i for i, cls in enumerate(unique_classes)}
    new_data["id"] = new_data["BestClass"].map(label_to_index)

    wilks = class_analysis["WilksSummary"].loc["Wilks"][1::]
    fig = plot_wilks_lambda(wilks, n_classes, n_excluded)
    map_raster = newdata_to_raster(new_data)

    # Generate LCP sites
    sites = lcp(map_raster, delta=1.0, zeta=2.0, total=30, grid=0.7)

    return {
        "new_data": new_data,
        "best_n_classes": n_classes,
        "wilks_plot": fig,
        "class_analysis": class_analysis,
        "map_raster": map_raster,
        "lcp_sites": sites,
    }


def do_asd(data: Any) -> None:
    """Perform ASD sampling and analysis on the provided dataset.

    Parameters
    ----------
    data : Any
        Analysis-ready dataset for ASD.
    """
    benin = pd.read_csv("test_data/benin.csv")
    beningrid = pd.read_csv("test_data/beningrid.csv")
    target = "H"

    map_raster, sites = glmmPQL_via_rpy2(
        formulaf="AnGam~Week+Elev+Soil",
        formular="~1|LCD",
        data=benin,
        area=beningrid,
        target=target,
        total=15,
        delta=0.01,
    )

    return {
        "map_raster": map_raster,
        "asd_sites": sites,
    }
