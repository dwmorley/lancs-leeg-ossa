"""Routines for the ASD sampling design. Luigi's original R code."""

from typing import Callable

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import rpy2.robjects as ro
import xarray as xr
from rpy2.rinterface_lib.embedded import RRuntimeError
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr
from scipy.spatial import cKDTree

from src.covariates.get_iolulc import get_iolulc
from src.utils.bounding_box import BoundingBox
from src.utils.r_base import RComputationBase


class ASDComputation(RComputationBase):
    """ASD computation using R."""

    def __init__(
        self,
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
    ):
        """Initialize ASD computation.

        Parameters
        ----------
        model : str
            The name of the R model to use for fitting.
        formulaf : str
            A formula string for the fixed effects in R syntax.
        formular : str
            A formula string describing the random structure.
        data : pd.DataFrame
            Observational data passed to the R model.
        area : pd.DataFrame
            Prediction grid
        target : {'H','U'}
            If 'H' request raster of fitted values and uncertainties; if 'U'
            request raster of uncertainties only.
        total : float
            Maximum number of sample locations to return after thinning.
        delta : float
            Minimum allowed pairwise distance for the thinning step.
        resolution : int
            Multiplier for the resolution of the output raster relative to the grid
        on_progress : callable, optional
            Progress callback function
        """
        super().__init__(on_progress=on_progress)
        self.model = model
        self.formulaf = formulaf
        self.formular = formular
        self.data = data
        self.area = area
        self.target = target
        self.total = total
        self.delta = delta
        self.resolution = resolution

    def _compute(self) -> tuple[xr.DataArray, pd.DataFrame] | None:
        """Perform ASD computation."""
        if self.target not in ("H", "U"):
            raise TypeError(f"target must be one of ('H', 'U'), got {self.target}")

        self._prog(0.05, "Loading R packages")

        importr("MBA")
        if self.model == "glmmPQL":
            importr("MASS")
            importr("nlme")
            importr("AICcmodavg")
        elif self.model == "spglm":
            importr("spmodel")

        try:
            with localconverter(pandas2ri.converter):
                self._prog(0.10, "Transferring data to R")

                data = self.rename_lonlat_to_xy(self.data)
                area = self.rename_lonlat_to_xy(self.area)

                x_res = len(area["x"].unique()) * self.resolution
                y_res = len(area["y"].unique()) * self.resolution

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

                if self.formulaf != "":
                    cols = data.columns.tolist()
                    formula_columns = [col for col in cols if col in self.formular]
                    for col in formula_columns:
                        ro.r(f"data${col} <- as.factor(data${col})")

                self._prog(0.15, f"Fitting model ({self.model})...")
                if self.model == "glmmPQL":
                    ro.r(
                        f"""
                            model <- glmmPQL(
                                {self.formulaf},
                                random = {self.formular},
                                data = data,
                                correlation = corExp(form = ~x + y, nugget = T),
                                family = poisson,
                                verbose = TRUE
                            )
                        """
                    )
                elif self.model == "spglm":
                    ro.r(
                        f"""
                            model <- spglm(
                                {self.formulaf},
                                random = {self.formular},
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

                self._prog(0.75, "Predicting standard errors")
                if self.model == "glmmPQL":
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
                elif self.model == "spglm":
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

                if self.target == "H":
                    self._prog(0.88, "Interpolating fitted values grid")
                    if self.model == "glmmPQL":
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
                    elif self.model == "spglm":
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
            self._prog(0.75, "Making rasters")
            modelgrid, modelgrid_x_array, modelgrid_y_array, modelgrid_z_array = _extract_r_grid(
                "modelgrid"
            )
            if self.target == "H":
                modelgridX, modelgridX_x_array, modelgridX_y_array, modelgridX_z_array = (
                    _extract_r_grid("modelgridX")
                )
                da = modelgridX
            else:
                modelgridX = None
                da = modelgrid

            self._prog(0.80, "Selecting sample locations")
            x_coords = modelgrid.coords["x"].values
            y_coords = modelgrid.coords["y"].values

            if self.target == "H":
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
            to_remove = {j for i, j in tree.query_pairs(self.delta)}

            x = x.drop(index=list(to_remove)).reset_index(drop=True).iloc[: self.total]

            self._prog(0.95, "Finalising")

            return da, x

        except RRuntimeError as r_err:
            self._handle_r_error(r_err)
        except Exception as e:
            self._handle_python_error(e)


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
    computation = ASDComputation(
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
    )
    return computation.compute()


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
