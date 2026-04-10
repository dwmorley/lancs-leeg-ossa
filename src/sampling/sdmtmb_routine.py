"""Routines for the SDMTMB spatiotemporal model. Luigi's original R code."""

from typing import Callable

import pandas as pd
import rpy2.robjects as ro
from rpy2.rinterface_lib.embedded import RRuntimeError
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr

from src.utils.r_base import RComputationBase


class SDMTMBComputation(RComputationBase):
    """SDMTMB computation using R."""

    def __init__(
        self,
        formula: str,
        time: str,
        family: str,
        spatial: str,
        spatiotemporal: str,
        data: pd.DataFrame,
        area: pd.DataFrame,
        on_progress: Callable[[float, str, str], None] | None = None,
    ):
        """Initialize SDMTMB computation.

        Parameters
        ----------
        formula : str
            Model formula string
        time : str
            Time column name or "None"
        family : str
            Distribution family (e.g., "Poisson")
        spatial : str
            Spatial random fields ("On" or "Off")
        spatiotemporal : str
            Spatiotemporal random fields type
        data : pd.DataFrame
            Training data
        area : pd.DataFrame
            Prediction grid
        on_progress : callable, optional
            Progress callback function
        """
        super().__init__(on_progress=on_progress)
        self.formula = formula
        self.time = time
        self.family = family
        self.spatial = spatial
        self.spatiotemporal = spatiotemporal
        self.data = data
        self.area = area

    def _compute(self) -> pd.DataFrame | None:
        """Perform SDMTMB computation."""
        self._prog(0.05, "Loading R packages")

        importr("sdmTMB")

        try:
            with localconverter(pandas2ri.converter):
                self._prog(0.10, "Transferring data to R")

                data = self.rename_lonlat_to_xy(self.data)
                area = self.rename_lonlat_to_xy(self.area)

                # Validate formula variables are in data
                self.validate_formula_variables(self.formula, data, "formula")
                if self.time != "None" and self.time not in data.columns:
                    raise ValueError(
                        f"Time column '{self.time}' not found in data. "
                        f"Available columns: {', '.join(sorted(data.columns))}"
                    )

                ro.globalenv["data"] = data
                ro.globalenv["area"] = area

                self._prog(0.15, "Fitting model...")

                ro.r(f"""form4 <-as.formula({self.formula})""")
                ro.r("""vars <- all.vars(form4)""")
                ro.r("""lhs <- as.character(form4[[2]])""")
                ro.r("""rhs <- vars[which(vars != lhs)]""")

                if self.time == "None":
                    ro.r("""d <- data[, c(vars, "x", "y"), drop = FALSE]""")
                    ro.r("""newdata <- area[, c(rhs, "x", "y"), drop = FALSE]""")
                else:
                    ro.r(f"""d <- data[, c(vars, "{self.time}", "x", "y"), drop = FALSE]""")
                    ro.r(f"""newdata <- area[, c(rhs, "{self.time}", "x", "y"), drop = FALSE]""")
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

                if self.time == "None":
                    time_r = ""
                    spatiotemporal = "off"
                else:
                    time_r = f"""time = "{self.time}","""
                    spatiotemporal = self.spatiotemporal

                ro.r(
                    f"""
                    fit_spatiotemporal1 <- sdmTMB(
                                  formula = form4,
                                  mesh = mesh,
                                  data= d,
                                  {time_r}
                                  family = {self.family.lower()}(),
                                  spatial = "{self.spatial}",
                                  spatiotemporal = "{spatiotemporal}",
                                  silent = FALSE)
                """
                )

                self._prog(0.75, "Predicting standard errors")

                ro.r("""p_se <- predict(fit_spatiotemporal1, newdata = newdata, nsim=200)""")

                if self.time == "None":
                    ro.r(
                        """dpred <-cbind(newdata[, c("x","y")], exp(apply(p_se,1,mean)), exp(apply(p_se,1,sd)))"""
                    )
                    ro.r("""colnames(dpred)=c("longitude","latitude","mean","sd")""")
                else:
                    ro.r(
                        f"""dpred <-cbind(newdata[, c("x","y","{self.time}")], exp(apply(p_se,1,mean)), exp(apply(p_se,1,sd)))"""
                    )
                    ro.r("""colnames(dpred)=c("longitude","latitude","time","mean","sd")""")

            self._prog(0.95, "Finalising")

            with localconverter(pandas2ri.converter):
                result_df = ro.r("dpred")

            return result_df

        except RRuntimeError as r_err:
            self._handle_r_error(r_err)
        except Exception as e:
            self._handle_python_error(e)


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
    computation = SDMTMBComputation(
        formula=formula,
        time=time,
        family=family,
        spatial=spatial,
        spatiotemporal=spatiotemporal,
        data=data,
        area=area,
        on_progress=on_progress,
    )
    return computation.compute()


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
