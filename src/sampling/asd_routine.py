"""Routines for the ASD sampling design. Luigi's original R code."""

from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import rpy2.robjects as ro
import xarray as xr
from matplotlib.colors import BoundaryNorm
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr


def glmmPQL_via_rpy2(
    formulaf: str,
    formular: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    target: Literal["H", "U"],
    total: float = 15,
    delta: float = 0.01,
) -> tuple[xr.DataArray, pd.DataFrame]:
    """Fit a GLMM via R (glmmPQL) and produce an interpolated raster.

    This function uses rpy2 to call R packages (MASS, nlme, AICcmodavg,
    MBA) to fit a penalised quasi-likelihood GLMM with an exponential
    spatial correlation structure, predict standard errors on a supplied
    `area` grid, and produce a regularly-gridded raster using MBA
    interpolation. It also selects sampling locations using a simple
    thinning procedure.

    Parameters
    ----------
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

    Returns
    -------
    tuple
        A tuple (da, x_df) where ``da`` is an ``xarray.DataArray`` holding
        the interpolated raster (dimensions ['y', 'x']) and ``x_df`` is a
        pandas DataFrame with the sampled point locations (columns include
        'x' and 'y').

    Notes
    -----
    - This function requires the R packages MASS, nlme, AICcmodavg and
      MBA to be installed and available to rpy2. If they are missing the
      calls will raise an error from rpy2.
    - The function communicates with R via global environment variables
      and runs several R scripts; the behaviour mirrors a direct R
      workflow and is not vectorised in pure Python.
    """
    # TODO: fix imports
    importr("MASS")
    importr("nlme")
    importr("AICcmodavg")
    importr("MBA")

    with localconverter(pandas2ri.converter):
        ro.globalenv["data"] = data
        ro.globalenv["area"] = area

        ro.r(
            f"""
            model <- glmmPQL(
                {formulaf},
                random = {formular},
                data = data,
                correlation = corExp(form = ~x + y, nugget = T),
                family = poisson
            )
        """
        )

        ro.r(
            """
            modelse <- predictSE(model, newdata=area)
        """
        )
        ro.r(
            """
            modelgrid <- mba.surf(
                cbind(area[, c("x", "y")], modelse$se.fit),
                no.X = 100,
                no.Y = 100,
                extend = TRUE
            )$xyz.est
        """
        )

        if target == "H":
            ro.r(
                """
                modelgridX <- mba.surf(
                    cbind(area[, c("x", "y")], modelse$fit),
                    no.X = 100,
                    no.Y = 100,
                    extend = TRUE
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
            ro.r(
                """
                x <- cbind(
                    expand.grid(modelgrid[[1]], modelgrid[[2]]),
                    c(modelgrid[[3]])
                )
            """
            )
            ro.r(
                """
                 xx <- sort(x[,3],decreasing=T,index.return=T)$ix
            """
            )
            ro.r(
                """
                x <- x[xx,]
            """
            )

            the_raster = "modelgrid"
            colnames = """colnames(x)=c("x","y","Uncertainty")"""

    ro.r("""xx <- dist(x[, 1:2])""")
    ro.r("""xx <- as.matrix(xx)""")
    ro.r(f"""xx <- lapply(2:nrow(xx),function(y)which(xx[(y-1),y:nrow(xx)]<={delta})+(y-1))""")
    ro.r("""xx <- unique(unlist(xx))""")
    ro.r("""x <- x[-xx,]""")
    ro.r(f"""x <- x[1:{total},]""")
    ro.r(colnames)

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

    # da.rio.to_raster("adaptive_sampling.tif")

    return da, x_df


def asd_plot(plot_title: str, da: xr.DataArray, x_df: pd.DataFrame, z_grid: np.ndarray) -> None:
    """Plot an ASD raster with sampled points overlaid.

    Parameters
    ----------
    plot_title : str
        Title to use for the matplotlib figure.
    da : xarray.DataArray
        The raster DataArray used to derive the plot extent. Expected to
        have coordinate dims 'x' and 'y'.
    x_df : pandas.DataFrame
        DataFrame of sampled point locations. Must have columns 'x' and
        'y' containing coordinates.
    z_grid : numpy.ndarray
        2-D array of raster values shaped to match the coordinates in
        ``da`` (rows correspond to y coordinates, columns to x).

    Returns
    -------
    None
        Displays a matplotlib figure and returns None.
    """
    extent = (
        float(da.x.min().values),
        float(da.x.max().values),
        float(da.y.min().values),
        float(da.y.max().values),
    )

    vmin, vmax = z_grid.min(), z_grid.max()
    bounds = np.linspace(vmin, vmax, 12)
    cmap = plt.get_cmap("hot")
    norm = BoundaryNorm(bounds, cmap.N)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(
        z_grid,
        extent=extent,
        origin="lower",
        cmap="hot",
        norm=norm,
    )
    ax.set_title(plot_title)
    cbar = plt.colorbar(im, ax=ax, boundaries=bounds, ticks=bounds)
    cbar.set_label("Value")

    ax.plot(x_df["x"], x_df["y"], "x", color="blue", markersize=10, markeredgewidth=2)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":

    data = pd.read_csv("../../test_data/benin.csv")
    area = pd.read_csv("../../test_data/beningrid.csv")

    da, x_df = glmmPQL_via_rpy2(
        formulaf="AnGam~Week+Elev+Soil",
        formular="~1|LCD",
        data=data,
        area=area,
        target="H",
        total=15,
        delta=0.01,
    )
