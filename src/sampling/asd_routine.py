"""Routines for the ASD sampling design. Luigi's original R code."""

from typing import Callable

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import rpy2.robjects as ro
import xarray as xr
from rpy2.rinterface_lib import callbacks as rpy2_callbacks
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr

RESOLUTION = 10  # TODO: That is, 10 interpolated grid cells between supplied sampling grid


def asd_via_rpy2(
    model: str,
    formulaf: str,
    formular: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    target: str,
    total: float = 15,
    delta: float = 0.01,
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
        Observational data passed to the R model. Must contain columns
        referenced by `formulaf` and coordinate columns named 'x' and 'y'.
    area : pandas.DataFrame
        Prediction grid (data frame with 'x' and 'y') on which predictions
        and prediction standard errors will be computed.
    target : {'H','U'}
        If 'H' request raster of fitted values and uncertainties; if 'U'
        request raster of uncertainties only. Defaults to 'H'.
    total : float
        Maximum number of sample locations to return after thinning.
    delta : float
        Minimum allowed pairwise distance (in the same units as 'x'/'y')
        for the thinning step.
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

    with localconverter(pandas2ri.converter):
        _prog(0.10, "Transferring data to R")
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
                        spcov_type = "exponential",
                        estmethod="ml",
                        verbose = TRUE
                    )
                    """
            )

        _prog(0.75, "Predicting standard errors")
        x_res = len(area["x"].unique()) * RESOLUTION
        y_res = len(area["y"].unique()) * RESOLUTION

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
                    cbind(area[,1:2],abs(modelse[,3]-modelse[,2])),
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
                        cbind(area[,1:2], modelse[,1]),
                        no.X={x_res},
                        no.Y={y_res},
                        extend=TRUE
                    )$xyz.est
                    """
                )
            ro.r(
                """
                x <- cbind(
                    expand.grid(modelgrid[[1]], modelgrid[[2]]),
                    c(modelgridX[[3]]),
                    c(modelgrid[[3]])
                )
            """
            )
            ro.r(
                """
                x <- x[order(x[,3],x[,4],decreasing=T),]
            """
            )
            the_raster = "modelgridX"
            colnames = """colnames(x)=c("x","y","Fit","Uncertainty")"""

        if target == "U":
            ro.r("""x=cbind(expand.grid(modelgrid[[1]],modelgrid[[2]]),c(modelgrid[[3]]))""")
            ro.r("""xx=sort(x[,3],decreasing=T,index.return=T)$ix""")
            ro.r("""x=x[xx,]""")
            the_raster = "modelgrid"
            colnames = """colnames(x)=c("x","y","Uncertainty")"""

        _prog(0.90, "Selecting sample locations")
        ro.r("""xx=dist(x[,1:2])""")
        ro.r("""xx=as.matrix(xx)""")
        ro.r("""b=nrow(xx)""")
        ro.r(f"""xx=lapply(2:b,function(y)which(xx[(y-1),y:b]<={delta})+(y-1))""")
        ro.r("""xx=unique(unlist(xx))""")
        ro.r("""x=x[-xx,]""")
        ro.r(f"""x=x[1:{total},]""")
        ro.r(colnames)

    _prog(0.95, "Finalising")
    ro.r(
        f"""
        image <- setNames(
            data.frame({the_raster}$x, {the_raster}$y, {the_raster}$z),
            c("x", "y", "z")
        )
    """
    )

    # sample point locations
    x_df = ro.globalenv["x"]
    with localconverter(pandas2ri.converter):
        x_df = pandas2ri.rpy2py(x_df)

    x_array = np.array(ro.r(f"{the_raster}$x")).flatten()
    y_array = np.array(ro.r(f"{the_raster}$y")).flatten()
    z_array = np.array(ro.r(f"{the_raster}$z"))
    z_grid = z_array.reshape(len(x_array), len(y_array)).T

    da = xr.DataArray(z_grid, coords={"y": y_array, "x": x_array}, dims=["y", "x"])
    da.rio.write_crs("EPSG:4326", inplace=True)

    return da, x_df


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
