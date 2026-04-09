"""Routines for the ASD sampling design. Luigi's original R code."""

from typing import Callable

import pandas as pd
import rpy2.robjects as ro
from rpy2.rinterface_lib import callbacks as rpy2_callbacks
from rpy2.rinterface_lib.embedded import RRuntimeError
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr


def sdmtmb_via_rpy2(
    formula: str,
    time: str,
    family: str,
    spatial: str,
    spatiotemporal: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    on_progress: Callable[[float, str, str], None] | None = None,
) -> pd.DataFrame:
    """Fit a TMB GLMM via R and produce an interpolated raster."""
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
        return _sdmtmb_via_rpy2_inner(
            formula=formula,
            time=time,
            family=family,
            spatial=spatial,
            spatiotemporal=spatiotemporal,
            data=data,
            area=area,
            on_progress=on_progress,
            _state=_state,
        )
    finally:
        rpy2_callbacks.consolewrite_print = _original_print
        rpy2_callbacks.consolewrite_warnerror = _original_warnerror


def _sdmtmb_via_rpy2_inner(
    formula: str,
    time: str,
    family: str,
    spatial: str,
    spatiotemporal: str,
    data: pd.DataFrame,
    area: pd.DataFrame,
    on_progress: Callable[[float, str, str], None] | None = None,
    _state: dict | None = None,
) -> pd.DataFrame:
    """Inner implementation called by sdmtmb_via_rpy2."""

    def _prog(value: float, message: str, detail: str = "") -> None:
        """Update shared state and fire the progress callback."""
        if _state is not None:
            _state["value"] = value
            _state["message"] = message
        if on_progress is not None:
            on_progress(value, message, detail)

    _prog(0.05, "Loading R packages")

    importr("sdmTMB")

    try:
        with localconverter(pandas2ri.converter):
            _prog(0.10, "Transferring data to R")

            # Rename longitude/latitude to x/y (case-insensitive) for R compatibility
            def _rename_lonlat_to_xy(df):
                col_map = {}
                for col in df.columns:
                    if col.lower() in ["longitude", "lng", "long"]:
                        col_map[col] = "x"
                    elif col.lower() in ["latitude", "lat", "ltd"]:
                        col_map[col] = "y"
                return df.rename(columns=col_map)

            data = _rename_lonlat_to_xy(data)
            area = _rename_lonlat_to_xy(area)

            ro.globalenv["data"] = data
            ro.globalenv["area"] = area

            _prog(0.15, "Fitting model...")

            ro.r(f"""form4 <-as.formula({formula})""")
            ro.r("""vars <- all.vars(form4)""")
            ro.r("""lhs <- as.character(form4[[2]])""")
            ro.r("""rhs <- vars[which(vars != lhs)]""")

            if time == "None":
                ro.r("""d <- data[, c(vars, "x", "y"), drop = FALSE]""")
                ro.r("""newdata <- area[, c(rhs, "x", "y"), drop = FALSE]""")
            else:
                ro.r(f"""d <- data[, c(vars, "{time}", "x", "y"), drop = FALSE]""")
                ro.r(f"""newdata <- area[, c(rhs, "{time}", "x", "y"), drop = FALSE]""")
            ro.r("""d <- na.omit(d)""")
            ro.r("""newdata <- na.omit(newdata)""")

            ro.r("""scaling_params <- list()""")
            ro.r(
                """for (col in rhs) { scaling_params[[col]] <- list(mean = mean(d[[col]]), sd = sd(d[[col]])) }"""
            )
            ro.r("""d[, rhs] <- scale(d[, rhs])""")
            ro.r(
                """for (col in rhs) { newdata[[col]] <- (newdata[[col]] - scaling_params[[col]]$mean) / scaling_params[[col]]$sd }"""
            )

            ro.r("""mesh <- make_mesh(d, xy_cols = c("x", "y"), cutoff = 0.15)""")

            if time == "None":
                time_r = ""
                spatiotemporal = "off"
            else:
                time_r = f"""time = "{time}","""

            ro.r(
                f"""
                fit_spatiotemporal1 <- sdmTMB(
                              formula = form4,
                              mesh = mesh,
                              data= d,
                              {time_r}
                              family = {family.lower()}(),
                              spatial = "{spatial}",
                              spatiotemporal = "{spatiotemporal}",
                              silent = FALSE)
            """
            )

            _prog(0.75, "Predicting standard errors")

            ro.r("""p_se <- predict(fit_spatiotemporal1, newdata = newdata, nsim=200)""")

            if time == "None":
                ro.r(
                    """dpred <-cbind(newdata[, c("x","y")], exp(apply(p_se,1,mean)), exp(apply(p_se,1,sd)))"""
                )
                ro.r("""colnames(dpred)=c("longitude","latitude","mean","sd")""")
            else:
                ro.r(
                    f"""dpred <-cbind(newdata[, c("x","y","{time}")], exp(apply(p_se,1,mean)), exp(apply(p_se,1,sd)))"""
                )
                ro.r("""colnames(dpred)=c("longitude","latitude","time","mean","sd")""")

        _prog(0.95, "Finalising")

        with localconverter(pandas2ri.converter):
            result_df = ro.r("dpred")

        return result_df

    except RRuntimeError as r_err:
        msg = str(r_err)
        if on_progress is not None:
            on_progress(1.0, "R Error", msg)
        raise RuntimeError(f"R error during sdmTMB computation: {msg}")
    except Exception as e:
        msg = str(e)
        if on_progress is not None:
            on_progress(1.0, "Python Error", msg)
        raise


if __name__ == "__main__":

    data = pd.read_csv("../../test_data/st_train.csv")
    area = pd.read_csv("../../test_data/st_newdata.csv")

    data.rename(columns={"LTD": "latitude", "LNG": "longitude"}, inplace=True)
    area.rename(columns={"LTD": "latitude", "LNG": "longitude"}, inplace=True)

    x_df = sdmtmb_via_rpy2(
        formula="OlivoP ~  soilhum + tmax + tmin + windspeed + NDVI + MIR + NIR + Red + Blu",
        time="YEA",
        family="poisson",
        data=data,
        area=area,
        spatial="off",
        spatiotemporal="ar1",
    )
