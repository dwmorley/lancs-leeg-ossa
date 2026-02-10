import pandas as pd
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr
from rpy2.robjects import pandas2ri
import rpy2.robjects as ro
import numpy as np
import xarray as xr
import rioxarray  # noqa: F401
import matplotlib.pyplot as plt


def glmmPQL_via_rpy2(formulaf, formular, data, area, target, total, delta):

    rpy2_version = ro.__version__
    if int(rpy2_version.split(".")[0]) < 3:
        pandas2ri.activate()

    # TODO: fix imports
    importr("MASS")
    importr("nlme")
    importr("AICcmodavg")
    importr("MBA")

    with localconverter(pandas2ri.converter):
        ro.globalenv["data"] = data
        ro.globalenv["area"] = area

        # Modelling
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

        # Finding locations
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
            colnames = """colnames(x)=c("x","y","Fit","Uncertainty")"""

        if target == "U":
            # TODO:

            colnames = """colnames(x)=c("x","y","Uncertainty")"""

    ro.r("""xx <- dist(x[, 1:2])""")
    ro.r("""xx <- as.matrix(xx)""")
    ro.r(
        f"""xx <- lapply(2:nrow(xx),function(y)which(xx[(y-1),y:nrow(xx)]<={delta})+(y-1))"""
    )
    ro.r("""xx <- unique(unlist(xx))""")
    ro.r("""x <- x[-xx,]""")
    ro.r(f"""x <- x[1:{total},]""")
    ro.r(colnames)

    ro.r(
        """
        image <- setNames(
            data.frame(modelgridX$x, modelgridX$y, modelgridX$z),
            c("x", "y", "z")
        )
    """
    )

    x_df = ro.globalenv["x"]
    with localconverter(pandas2ri.converter):
        x_df = pandas2ri.rpy2py(x_df)

    x_array = np.array(ro.r("modelgridX$x")).flatten()
    y_array = np.array(ro.r("modelgridX$y")).flatten()
    z_array = np.array(ro.r("modelgridX$z"))
    z_grid = z_array.reshape(len(x_array), len(y_array)).T

    da = xr.DataArray(z_grid, coords={"y": y_array, "x": x_array}, dims=["y", "x"])

    # # Assign CRS and save
    da.rio.write_crs("EPSG:4326", inplace=True)
    da.rio.to_raster("adaptive_sampling.tif")  # VERIFIED THE SAME

    # TODO: TUES - overlay the 15 points
    # TODO: TUES - for U as well

    from matplotlib.colors import BoundaryNorm
    from matplotlib.cm import get_cmap

    vmin, vmax = z_grid.min(), z_grid.max()
    bounds = np.linspace(vmin, vmax, 12)
    norm = BoundaryNorm(bounds, get_cmap("viridis").N)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(
        z_grid,
        extent=(x_array.min(), x_array.max(), y_array.min(), y_array.max()),
        origin="lower",
        cmap="hot",
        norm=norm,
    )
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Adaptive Sampling Raster (EPSG:4326)")
    cbar = plt.colorbar(im, ax=ax, boundaries=bounds, ticks=bounds)
    cbar.set_label("Value")
    plt.tight_layout()
    plt.show()

    return x_df  # Output is raster and points


if __name__ == "__main__":

    data = pd.read_csv("benin.csv")
    area = pd.read_csv("beningrid.csv")

    model1 = glmmPQL_via_rpy2(
        formulaf="AnGam~Week+Elev+Soil",
        formular="~1|LCD",
        data=data,
        area=area,
        target="H",
        total=15,
        delta=0.01,
    )

    #
    # adaptiveSites = asd(
    #     Data=benin[, -5],
    # area = beningrid,
    # formulaf = as.formula("AnGam~Week+Elev+Soil"),
    # formular = as.formula("~1|LCD"),
    # target = "H", total = 15, delta = 0.01
    # )
