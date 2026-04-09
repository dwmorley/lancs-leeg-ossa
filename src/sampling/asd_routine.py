"""Routines for the ASD sampling design. Luigi's original R code."""

from typing import Callable

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import rpy2.robjects as ro
import xarray as xr
from rpy2.rinterface_lib import callbacks as rpy2_callbacks
from rpy2.rinterface_lib.embedded import RRuntimeError
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr
from scipy.spatial import cKDTree

from src.covariates.get_iolulc import get_iolulc
from src.utils.bounding_box import BoundingBox


def asd_via_rpy2(
    model: str,
    formulaf: str,
    formular: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    target: str,
    total: float = 15,
    delta: float = 0.01,
    resolution: int = 10,
    on_progress: Callable[[float, str, str], None] | None = None,
) -> tuple[xr.DataArray, pd.DataFrame]:
    """Fit a GLMM via R and produce an interpolated raster.

    Parameters
    ----------
    model: str
        The name of the R model to use for fitting.
    formulaf : str
        A formula string for the fixed effects in R syntax (e.g.
        "AnGam~Week+Elev+Soil").
    formular : str
        A formula string describing the random structure (e.g. "~1|LCD").
    data : pandas.DataFrame
        Observational data passed to the R model.
    area : pandas.DataFrame
        Prediction grid
    target : {'H','U'}
        If 'H' request raster of fitted values and uncertainties; if 'U'
        request raster of uncertainties only. Defaults to 'H'.
    total : float
        Maximum number of sample locations to return after thinning.
    delta : float
        Minimum allowed pairwise distance (in the same units as 'x'/'y')
        for the thinning step.
    resolution : int
        Multiplier for the resolution of the output raster relative to the grid
    on_progress : callable, optional
        If provided, called as ``on_progress(value, message, detail)`` where
        *value* is a float in [0, 1] indicating overall progress, *message*
        is the current stage label, and *detail* is a live string from the R
        console (e.g. ``glmmPQL`` iteration lines). Useful for updating a
        progress bar in a UI such as Shiny.

    Returns
    -------
    tuple
        A tuple (da, x_df) where ``da`` is an ``xarray.DataArray`` holding
        the interpolated raster (dimensions ['y', 'x']) and ``x_df`` is a
        pandas DataFrame with the sampled point locations (columns include
        'x' and 'y').
    """
    # Install rpy2 console-write hooks so R verbose output is forwarded.
    _original_print = rpy2_callbacks.consolewrite_print
    _original_warnerror = rpy2_callbacks.consolewrite_warnerror
    _state: dict = {"value": 0.0, "message": "Starting..."}
    if on_progress is not None:

        def _consolewrite_hook(s: str) -> None:
            stripped = s.strip()
            if stripped:
                on_progress(_state["value"], _state["message"], stripped)
            _original_print(s)

        def _warnerror_hook(s: str) -> None:
            stripped = s.strip()
            if stripped:
                on_progress(_state["value"], _state["message"], stripped)
            _original_warnerror(s)

        rpy2_callbacks.consolewrite_print = _consolewrite_hook
        rpy2_callbacks.consolewrite_warnerror = _warnerror_hook

    try:
        return _asd_via_rpy2_inner(
            model=model,
            formulaf=formulaf,
            formular=formular,
            data=data,
            area=area,
            target=target,
            total=total,
            delta=delta,
            resolution=resolution,
            on_progress=on_progress,
            _state=_state,
        )
    finally:
        rpy2_callbacks.consolewrite_print = _original_print
        rpy2_callbacks.consolewrite_warnerror = _original_warnerror


def _asd_via_rpy2_inner(
    model: str,
    formulaf: str,
    formular: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    target: str,
    total: float = 15,
    delta: float = 0.01,
    resolution: int = 10,
    on_progress: Callable[[float, str, str], None] | None = None,
    _state: dict | None = None,
) -> tuple[xr.DataArray, pd.DataFrame]:
    """Inner implementation called by glmmPQL_via_rpy2."""
    if target not in ("H", "U"):
        raise TypeError(f"target must be one of ('H', 'U'), got {target}")

    def _prog(value: float, message: str, detail: str = "") -> None:
        """Update shared state and fire the progress callback."""
        if _state is not None:
            _state["value"] = value
            _state["message"] = message
        if on_progress is not None:
            on_progress(value, message, detail)

    _prog(0.05, "Loading R packages")

    importr("MBA")
    if model == "glmmPQL":
        importr("MASS")
        importr("nlme")
        importr("AICcmodavg")
    elif model == "spglm":
        importr("spmodel")

    try:
        with localconverter(pandas2ri.converter):
            _prog(0.10, "Transferring data to R")

            # Rename longitude/latitude to x/y (case-insensitive) for R compatibility
            def _rename_lonlat_to_xy(df):
                col_map = {}
                for col in df.columns:
                    if col.lower() in ["longitude", "lng", "long"]:
                        col_map[col] = "x"
                    elif col.lower() in ["latitude", "lat"]:
                        col_map[col] = "y"
                return df.rename(columns=col_map)

            data = _rename_lonlat_to_xy(data)
            area = _rename_lonlat_to_xy(area)

            x_res = len(area["x"].unique()) * resolution
            y_res = len(area["y"].unique()) * resolution

            ymax = area["y"].max()
            ymin = area["y"].min()
            xmax = area["x"].max()
            xmin = area["x"].min()
            lclu = get_iolulc(
                bbox=BoundingBox([xmin, ymin, xmax, ymax]),
                year=2023,
            )

            ro.globalenv["data"] = data
            ro.globalenv["area"] = area

            if formulaf != "":
                cols = data.columns.tolist()
                formula_columns = [col for col in cols if col in formular]
                for col in formula_columns:
                    ro.r(f"data${col} <- as.factor(data${col})")

            _prog(0.15, f"Fitting model ({model})...")
            if model == "glmmPQL":
                ro.r(
                    f"""
                        model <- glmmPQL(
                            {formulaf},
                            random = {formular},
                            data = data,
                            correlation = corExp(form = ~x + y, nugget = T),
                            family = poisson,
                            verbose = TRUE
                        )
                    """
                )
            elif model == "spglm":
                ro.r(
                    f"""
                        model <- spglm(
                            {formulaf},
                            random = {formular},
                            xcoord= x,
                            ycoord= y,
                            family = poisson,
                            data = data,
                            spcov_type = "matern",
                            estmethod="ml",
                            verbose = TRUE
                        )
                        """
                )

            _prog(0.75, "Predicting standard errors")
            if model == "glmmPQL":
                ro.r(
                    """
                    modelse <- predictSE(model, newdata=area)
                """
                )
                ro.r(
                    f"""
                    modelgrid <- mba.surf(
                        cbind(area[, c("x", "y")], modelse$se.fit),
                        no.X = {x_res},
                        no.Y = {y_res},
                        extend = TRUE
                    )$xyz.est
                """
                )
            elif model == "spglm":
                ro.r("""modelse <- predict(model,newdata=area,interval="confidence")""")
                ro.r(
                    f"""
                    modelgrid <- mba.surf(
                        cbind(area[, c("x", "y")],abs(modelse[,3]-modelse[,2])),
                        no.X={x_res},
                        no.Y={y_res},
                        extend=TRUE
                    )$xyz.est"""
                )

            if target == "H":
                _prog(0.88, "Interpolating fitted values grid")
                if model == "glmmPQL":
                    ro.r(
                        f"""
                        modelgridX <- mba.surf(
                            cbind(area[, c("x", "y")], modelse$fit),
                            no.X = {x_res},
                            no.Y = {y_res},
                            extend = TRUE
                        )$xyz.est
                    """
                    )
                elif model == "spglm":
                    ro.r(
                        f"""
                        modelgridX <- mba.surf(
                            cbind(area[, c("x", "y")], modelse[,1]),
                            no.X={x_res},
                            no.Y={y_res},
                            extend=TRUE
                        )$xyz.est
                        """
                    )

        def _extract_r_grid(r_name: str):
            ro.r(f"{r_name}_x <- {r_name}$x")
            ro.r(f"{r_name}_y <- {r_name}$y")
            ro.r(f"{r_name}_z <- {r_name}$z")
            r_x = ro.globalenv[f"{r_name}_x"]
            r_y = ro.globalenv[f"{r_name}_y"]
            r_z = ro.globalenv[f"{r_name}_z"]

            with localconverter(pandas2ri.converter):
                x_array = pandas2ri.rpy2py(r_x)
                y_array = pandas2ri.rpy2py(r_y)
                z_array = pandas2ri.rpy2py(r_z)
            z_grid = z_array.reshape(len(x_array), len(y_array), order="F").T
            da = xr.DataArray(z_grid, coords={"y": y_array, "x": x_array}, dims=["y", "x"])
            da.rio.write_crs("EPSG:4326", inplace=True)
            return da, x_array, y_array, z_array

        # Make the raster
        _prog(0.75, "Making rasters")
        modelgrid, modelgrid_x_array, modelgrid_y_array, modelgrid_z_array = _extract_r_grid(
            "modelgrid"
        )
        if target == "H":
            modelgridX, modelgridX_x_array, modelgridX_y_array, modelgridX_z_array = (
                _extract_r_grid("modelgridX")
            )
            da = modelgridX
        else:
            modelgridX = None
            da = modelgrid

        _prog(0.80, "Selecting sample locations")
        x_coords = modelgrid.coords["x"].values
        y_coords = modelgrid.coords["y"].values

        if target == "H":
            x = pd.DataFrame(
                {
                    0: np.repeat(x_coords, len(y_coords)),
                    1: np.tile(y_coords, len(x_coords)),
                    2: modelgridX.values.ravel(order="F"),
                    3: modelgrid.values.ravel(order="F"),
                }
            )
            sort_cols = ["Fit", "Uncertainty"]
            col_names = ["x", "y", "Fit", "Uncertainty"]
        else:
            x = pd.DataFrame(
                {
                    0: np.repeat(x_coords, len(y_coords)),
                    1: np.tile(y_coords, len(x_coords)),
                    2: modelgrid.values.ravel(order="F"),
                }
            )
            sort_cols = ["Uncertainty"]
            col_names = ["x", "y", "Uncertainty"]

        x.columns = col_names
        x = x.sort_values(by=sort_cols, ascending=False).reset_index(drop=True)

        # Mask out points in the sea (where lulc raster is NaN)
        lulc_values = lclu.sel(
            x=xr.DataArray(x["x"].values, dims="points"),
            y=xr.DataArray(x["y"].values, dims="points"),
            method="nearest",
        ).values
        x["lulc"] = lulc_values
        x = x[~np.isnan(x["lulc"])].reset_index(drop=True)
        x = x.drop(columns=["lulc"])

        coords = x.iloc[:, 0:2].values
        tree = cKDTree(coords)
        to_remove = {j for i, j in tree.query_pairs(delta)}

        x = x.drop(index=list(to_remove)).reset_index(drop=True).iloc[:total]

        _prog(0.95, "Finalising")

        return da, x

    except RRuntimeError as r_err:
        msg = str(r_err)
        if on_progress is not None:
            on_progress(1.0, "R Error", msg)
        raise RuntimeError(f"R error during ASD computation: {msg}")
    except Exception as e:
        msg = str(e)
        if on_progress is not None:
            on_progress(1.0, "Python Error", msg)
        raise


if __name__ == "__main__":

    data = pd.read_csv("../../test_data/benin.csv")
    area = pd.read_csv("../../test_data/beningrid.csv")

    da, x_df = asd_via_rpy2(
        model="spglm",
        formulaf="AnGam~Week+Elev+Soil",
        formular="~1|LCD",
        data=data,
        area=area,
        target="H",
        total=15,
        delta=0.01,
    )
