"""ZSSA routine called directly from R."""

from typing import Optional, Tuple

import pandas as pd
import rpy2.robjects as ro
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import importr

from src.utils.r_base import RComputationBase


def zssa_via_rpy2(
    data: pd.DataFrame,
    nr_iterations: int = 100,
    init: int = 20,
    add: Tuple = (100, 200, 300, 500),
    from_glm: bool = False,
    progress=None,
    notify_fn=None,
) -> Optional[Tuple[pd.DataFrame, dict[int, pd.DataFrame]]]:
    """ZSSA via R.

    Parameters
    ----------
    data : pd.DataFrame
        The input data containing the columns to be used in the ZSSA routine.
    nr_iterations : int, optional
        The number of iterations to perform for each point addition, by default 100.
    init : int, optional
        The number of random points for validation.
    add : Tuple, optional
        A tuple of integers specifying how many points to add in each iteration.
    from_glm : bool, optional
        Do kriging
    progress : bool, optional
        A Shiny progress object to update during the iterations, by default None.
    notify_fn : callable, optional
        A callback function to display notifications. If provided, validation errors will
        call this function instead of raising exceptions. The function should accept
        a message string and optionally a type parameter (e.g., 'error'), by default None.

    Returns
    -------
    Tuple[pd.DataFrame, dict[int, pd.DataFrame]]
        A tuple containing a summary table of the results and a dictionary of proposed points for each addition

    """
    data = RComputationBase.rename_lonlat_to_xy(data)

    if data.shape[1] not in (4, 5):
        msg = f"Data must have 4 or 5 columns, got {data.shape[1]}"
        if notify_fn:
            notify_fn(msg, type="error")
            return None
        raise ValueError(msg)

    expected_cols_4 = ["mean", "sd", "x", "y"]
    expected_cols_5 = ["mean", "sd", "x", "y", "time"]
    expected_cols = expected_cols_4 if data.shape[1] == 4 else expected_cols_5

    if not all(col in data.columns for col in expected_cols):
        missing = set(expected_cols) - set(data.columns)
        msg = f"Data is missing required columns: {missing}"
        if notify_fn:
            notify_fn(msg, type="error")
            return None
        raise ValueError(msg)

    if list(data.columns) != expected_cols:
        data = data[expected_cols]

    try:
        importr("extRemes")
        importr("fields")

        with localconverter(pandas2ri.converter):

            ro.globalenv["data"] = data
            ro.r("""Nbig=ncol(data)""")

            if init is not None:
                ro.r(f"""a=sample(1:nrow(data),{init})""")
                ro.r("""init=data[a,]""")
                ro.r("""data=data[-a,]""")

            ro.r(
                "weight=(((data[,1]-min(data[,1],na.rm=TRUE))/(max(data[,1],na.rm=TRUE)-min(data[,1],na.rm=TRUE)))+((data[,2]-min(data[,2],na.rm=TRUE))/(max(data[,2],na.rm=TRUE)-min(data[,2],na.rm=TRUE))))/2"
            )
            ro.r("weight=weight/max(weight,na.rm=TRUE)")

            ro.r(f"""coolingFactor <- {nr_iterations / 10}""")
            ro.r(f"""countMax <- {nr_iterations / 5}""")
            ro.r(f"""start_p <- {0.2}""")
            ro.r(f"""PE <- {0.5}""")  # quantile for Point over threshold in fevd
            ro.r(f"""IE <- {500}""")  # number of iteration for fevd
            ro.r(f"""fromglm <- {str(from_glm).upper()}""")

            add_r = f"""c({",".join(map(str, add))})"""
            ro.r(f"""results=vector("list",{len(add)}+1)""")
            ro.r(f"""retable <- matrix(NA,length({add_r})+1,4)""")
            ro.r("""addi <- 0""")
            ro.r(
                """colnames(retable)=c("Npoints","GeneralStandardError","MeanErrorValidation","SqMeanErrorValidation")"""
            )
            ro.r("retable[1,1] <- 0")
            ro.r(
                """
                {
                    if(fromglm==FALSE){
                        if(Nbig==5) kfit=Krig(x=init[,3:5],init[,1])
                        else kfit=Krig(x=init[,3:4],init[,1])
                        retable[1,2]=mean(predictSE(kfit))
                    } else {
                        retable[1,2]=NA
                    }
                }
            """
            )

            for n, i in enumerate(add):
                ro.r(
                    """
                    addi <- addi + 1
                    z1 <- init[,1]
                    z2 <- init[,2]
                    if(min(z1) < 0) z1 <- z1 + min(z1)
                    if(min(z2) < 0) z2 <- z2 + min(z2)

                    fit1 <- fevd(x=z1, type="GP", threshold=quantile(z1, probs=PE), method="Bayesian", iter=IE, time.units="months")
                    fit2 <- fevd(x=z2, type="GP", threshold=quantile(z2, probs=PE), method="Bayesian", iter=IE, time.units="months")
                    crit1 <- abs(1 - as.numeric(BayesFactor(fit1, fit2, burn.in=100, method="harmonic")[[1]]))

                    nr_designs <- 1
                    criterionInitial <- crit1
                    criterionIterf <- NULL
                    bestCriterion <- Inf
                    count <- 0
                """
                )

                for ii in range(1, nr_iterations + 1):
                    ro.r(
                        """
                        a <- sample(1:nrow(data), {}, prob=weight)
                        z1 <- c(init[,1], data[a,1])
                        z2 <- c(init[,2], data[a,2])
                        if(min(z1) < 0) z1 <- z1 + min(z1)
                        if(min(z2) < 0) z2 <- z2 + min(z2)

                        fit1 <- fevd(x=z1, type="GP", threshold=quantile(z1, probs=PE), method="Bayesian", iter=IE, time.units="months")
                        fit2 <- fevd(x=z2, type="GP", threshold=quantile(z2, probs=PE), method="Bayesian", iter=IE, time.units="months")
                        critx <- abs(1 - BayesFactor(fit1, fit2, burn.in=100, method="harmonic")[[1]])

                        p <- runif(1)
                        if(critx <= crit1) {{
                            crit1 <- critx
                            nr_designs <- nr_designs + 1
                            count <- 0
                        }} else {{
                            if(critx > crit1 & p <= (start_p * exp(-{} / coolingFactor))) {{
                                crit1 <- critx
                                nr_designs <- nr_designs + 1
                                count <- count + 1
                            }} else {{
                                critx <- crit1
                            }}
                        }}
                        criterionIterf[{}] <- critx
                        if(critx < bestCriterion / 1.0000001) {{
                            bestpoints <- a
                            bestCriterion <- critx
                        }}

                        if(count == countMax) break
                    """.format(
                            i, ii, ii
                        )
                    )

                    if progress:
                        progress.set(
                            value=ii + (n * nr_iterations),
                            message=f"{ii} / {nr_iterations} iterations with {i} points added",
                        )

                ro.r(
                    """
                    retable[(addi+1),1]={}
                    new=rbind(init,data[bestpoints,])
                    if(Nbig==5) {{
                        kfit2=Krig(x=new[,3:5],new[,1])
                    }} else {{
                        kfit2=Krig(x=new[,3:4],new[,1])
                    }}
                    retable[(addi+1),2]=mean(predictSE(kfit2))
                    if(fromglm==FALSE) {{
                        if(Nbig==5) pre=predict(kfit,data[bestpoints,c(3:5)])
                        else pre=predict(kfit,data[bestpoints,c(3:4)])
                        retable[(addi+1),3]=mean(data[bestpoints,1]-pre)
                        retable[(addi+1),4]=mean((data[bestpoints,1]-pre)^2)
                    }}
                    results[[addi]]=list(bestpoints,bestCriterion,criterionInitial,criterionIterf,nr_designs,{})
                    names(results[[addi]])=c("bestpoints","bestCriterion","criterionInitial","criterionIterf","nr_designs","iterations")
                """.format(
                        i, ii
                    )
                )

        ro.r(
            f"""
            names(results)=c({add_r},"SummaryTable")
            results[[(addi+1)]]=retable
        """
        )

        ro.r("df <- data.frame(results$SummaryTable)")
        for i, p in enumerate(add):
            ro.r(f"""p{p} <- data[c("x","y")]""")
            ro.r(f"""p{p}$proposed <- 0""")
            ro.r(f"""p{p}$proposed[results[[{i + 1}]][[1]]]=1""")

        r_df = ro.globalenv["df"]
        proposed = {}
        with localconverter(pandas2ri.converter):
            summary_table = pandas2ri.rpy2py(r_df)
        for i, p in enumerate(add):
            proposed[p] = pandas2ri.rpy2py(ro.globalenv[f"p{p}"])

        if notify_fn:
            notify_fn("MC-ASD Finished!", type="message", duration=None)

        return summary_table, proposed

    except Exception as e:
        error_msg = f"Error during MC-ASD analysis: {str(e)}"
        if notify_fn:
            notify_fn(error_msg, type="error", duration=None)
            return None
        raise


if __name__ == "__main__":
    df = pd.read_csv("/Users/david/Documents/GitHub/lancs-leeg-ossa/test_data/zssa_st.csv")

    x = zssa_via_rpy2(df, nr_iterations=10, init=20, add=(10, 20), from_glm=False)

    zssa_proposed = x[1]
    combined_df = zssa_proposed[next(iter(zssa_proposed))][["y", "x"]].copy()
    combined_df = combined_df.drop_duplicates().reset_index(drop=True)

    for k, v in zssa_proposed.items():
        temp = (
            v[["x", "y", "proposed"]]
            .drop_duplicates()
            .rename(columns={"proposed": f"proposed_{k}"})
        )
        combined_df = combined_df.merge(temp, on=["x", "y"], how="left")

    kmls = {}
    for col in combined_df.columns:
        if col.startswith("proposed_"):
            kmls[f"zssa_{col}.kml"] = combined_df[["x", "y", col]].copy()

    for idx, row in kmls[next(iter(kmls))].iterrows():
        coords = f"{row.x},{row.y}"

    b = 0
