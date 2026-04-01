"""QDA UI and server components."""

import base64
from datetime import datetime
from io import BytesIO

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, ui

from src.constants import COVARIATE_OPTIONS, LCP_OPTIONS, QDA_OPTIONS, RESPONSE_OPTIONS
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer
from src.sampling.lcp_routine import lcp
from src.sampling.luqdaloop_routine import luqdaloop, make_qda_raster, plot_wilks_lambda
from src.utils.downloads import save_artifacts_zip


@module.ui
def qda_ui():
    """Return UI components for the QDA/LCP panel."""
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("Discriminant Analysis", class_="column-header"),
                        ui.input_select(
                            "qda_response",
                            "Categorical (response) variable",
                            choices=[],
                            selected=None,
                        ),
                        ui.input_numeric(
                            "qda_nx",
                            "Maximum QDA classes allowed (nx)",
                            value=QDA_OPTIONS["nx"],
                            min=1,
                            step=1,
                        ),
                        ui.input_numeric(
                            "qda_nn",
                            "QDA Local frequency prior distance (nn)",
                            value=QDA_OPTIONS["nn"],
                            step=0.1,
                        ),
                        ui.tags.div(
                            ui.tooltip(
                                ui.input_action_button(
                                    "show_wilks_stats",
                                    ui.tags.span(
                                        [icon_svg("table-list")], class_="icon-square-btn"
                                    ),
                                    class_="action-button",
                                ),
                                "Show Wilks' Lambda statistics",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            ui.tooltip(
                                ui.input_action_button(
                                    "show_wilks_plot",
                                    ui.tags.span(
                                        [icon_svg("chart-line")], class_="icon-square-btn"
                                    ),
                                    class_="action-button",
                                ),
                                "Show Wilks' Lambda plot",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            ui.tooltip(
                                ui.input_action_button(
                                    "run_qda",
                                    ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                                    class_="action-button",
                                ),
                                "Run QDA analysis",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            style="margin-top: auto; align-self: flex-end;",
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
                # Right column
                ui.tags.div(
                    [
                        ui.h4("Lattice Close Pairs", class_="column-header"),
                        ui.input_slider(
                            "lcp_classes",
                            "Classes to use",
                            value=1,
                            min=2,
                            max=QDA_OPTIONS["nx"],
                            step=1,
                            ticks=False,
                        ),
                        ui.input_numeric(
                            "lcp_delta",
                            "Inhibition distance (delta)",
                            value=LCP_OPTIONS["delta"],
                            step=0.01,
                        ),
                        ui.input_numeric(
                            "lcp_zeta",
                            "Allocation radius (zeta)",
                            value=LCP_OPTIONS["zeta"],
                            step=0.1,
                        ),
                        ui.input_numeric(
                            "lcp_total",
                            "Number of locations to optimise",
                            value=LCP_OPTIONS["total"],
                            min=1,
                            step=1,
                        ),
                        ui.input_numeric(
                            "lcp_grid",
                            "Proportion of grid locations (to close pairs)",
                            value=LCP_OPTIONS["grid"],
                            min=0,
                            max=1,
                            step=0.01,
                        ),
                        ui.tags.div(
                            ui.tooltip(
                                ui.input_action_button(
                                    "save_qdalcp",
                                    ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                                    class_="action-button",
                                ),
                                "Export QDA/LCP results",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            ui.tooltip(
                                ui.input_action_button(
                                    "run_lcp",
                                    ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                                    class_="action-button",
                                ),
                                "Run LCP analysis",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            style="margin-top: auto; align-self: flex-end;",
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
            ],
            class_="content-columns",
        ),
        class_="tab-content",
    )


@module.server
def qda_server(input, output, session, reactive_values):
    """Server-side logic for QDA."""
    _map_raster = reactive.Value(None)

    @reactive.effect
    def _update_qda_response_choices() -> None:
        extracted_df = reactive_values["extracted_df"]()
        if extracted_df is not None:
            cols = extracted_df.columns.tolist()
            response_choices = [
                col
                for col in cols
                if col in RESPONSE_OPTIONS.keys()
                or col not in COVARIATE_OPTIONS.keys()
                and col not in ["longitude", "latitude"]
                and not col.endswith(("_avg", "_min", "_max", "_sd", "_ampl"))
            ]
            response_choices = [RESPONSE_OPTIONS.get(col, col) for col in response_choices]
        else:
            response_choices = []
        ui.update_select(
            "qda_response",
            choices=response_choices,
            selected=response_choices[0] if response_choices else None,
        )

    @reactive.effect
    def _clamp_lcp_grid() -> None:
        val = input.lcp_grid()
        if val is not None:
            if val < 0:
                ui.update_numeric("lcp_grid", value=0)
            elif val > 1:
                ui.update_numeric("lcp_grid", value=1)

    @reactive.effect
    @reactive.event(input.save_qdalcp)
    def _handle_save_qdalcp() -> None:
        if not reactive_values["lcp_results"]() or not reactive_values["qda_results"]():
            ui.notification_show(
                "Nothing to export. Please run the QDA/LCP analysis first.",
                type="error",
            )
            return

        lcp_sites = reactive_values["lcp_results"]()["lcp_sites"]
        wilks_plot = reactive_values["qda_results"]()["wilks_plot"]
        lcp_sites_gpkg = gpd.GeoDataFrame(
            lcp_sites, geometry=gpd.points_from_xy(lcp_sites.x, lcp_sites.y), crs="EPSG:4326"
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        zip_path = save_artifacts_zip(
            zip_name=f"qda_lcp_results_{timestamp}.zip",
            csv_artifacts={"lcp_sites.csv": lcp_sites},
            gpkg_artifacts={"lcp_sites.gpkg": lcp_sites_gpkg},
            raster_artifacts={"qda_raster.tif": _map_raster._value},
            figure_artifacts={"wilks_plot.png": wilks_plot},
        )
        plt.close(wilks_plot)

        ui.notification_show(
            f"Results saved to {zip_path}",
            type="message",
        )

    @reactive.effect
    @reactive.event(input.run_qda)
    def _handle_run_qda() -> None:

        extracted_df = reactive_values["extracted_df"]()
        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]

        if input.qda_response() is None:
            ui.notification_show(
                "Please select, or ensure there is a valid response variable.",
                type="error",
            )
            return
        else:
            response = next(
                (k for k, v in RESPONSE_OPTIONS.items() if v == input.qda_response()),
                input.qda_response(),
            )

        constant_cols = extracted_df.columns[np.where(extracted_df.std(axis=0) == 0)[0]].tolist()
        if len(constant_cols) > 0:
            ui.notification_show(
                f"Data contains constant columns: {constant_cols}. I have dropped these",
                type="warning",
                duration=None,
            )
            extracted_df = extracted_df.drop(columns=constant_cols)

        if not validate_extracted_df(extracted_df, response):
            return

        # Do QDA
        X = extracted_df.drop(columns=["longitude", "latitude", response]).values
        y = extracted_df[response].values.astype(int).astype(str)
        spatial_grid = extracted_df[["longitude", "latitude"]].values
        nn = input.qda_nn()
        nx = input.qda_nx()
        class_analysis = luqdaloop(X=X, y=y, grid=spatial_grid, nn=nn, nx=nx)

        # Check if class_analysis is a string (error message)
        if isinstance(class_analysis, str):
            ui.notification_show(
                f"QDA analysis failed: {class_analysis}",
                type="error",
                duration=None,
            )
            return

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

        results = {
            "best_n_classes": n_classes,
            "wilks_plot": fig,
            "class_analysis": class_analysis,
        }

        reactive_values["qda_results"].set(results)

        # Update the UI with recommended number of classes and corresponding raster
        ui.update_slider("lcp_classes", value=results["best_n_classes"], min=2, max=input.qda_nx())

        map_raster = make_qda_raster(results["class_analysis"], results["best_n_classes"])
        _map_raster.set(map_raster)

        drawn_shapes.set([])
        overlay = dataarray_to_image_overlay(map_raster, categorical=True, name="LUQDA Classes")
        my_ossa_layers.set([overlay])

        ui.notification_show(
            ui.HTML(
                f"QDA analysis recommends {results['best_n_classes']} classes.<br>You can adjust this after looking at the Wilks' Lambda statistics and plot."
            ),
            type="message",
        )

    @reactive.effect
    @reactive.event(input.show_wilks_plot)
    def _handle_show_wilks_plot() -> None:

        if not reactive_values["qda_results"]():
            ui.notification_show(
                "Please run the QDA analysis first to see the Wilks' Lambda plot.",
                type="error",
            )
            return

        fig = reactive_values["qda_results"]()["wilks_plot"]
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        plt.close(fig)
        ui.modal_show(
            ui.modal(
                ui.HTML(
                    f'<img src="data:image/png;base64,{img_base64}" style="width:100%; max-width:800px;">'
                ),
                easy_close=True,
                size="l",
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.show_wilks_stats)
    def _handle_show_wilks_stats() -> None:

        if not reactive_values["qda_results"]():
            ui.notification_show(
                "Please run the QDA analysis first to see the Wilks' Lambda statistics.",
                type="error",
            )
            return

        # Make invalid clusters explicit in the table.
        df = reactive_values["qda_results"]()["class_analysis"]["WilksSummary"]
        for c in df.columns:
            if c != "1":
                if (
                    f"{c}cluster"
                    not in reactive_values["qda_results"]()["class_analysis"]["NewData"]
                ):
                    df[c] = np.nan

        header = ui.tags.thead(
            ui.tags.tr(
                ui.tags.th(""),
                *[ui.tags.th(col, style="text-align:right;") for col in df.columns],
            )
        )
        body = ui.tags.tbody(
            *[
                ui.tags.tr(
                    ui.tags.th(row, style="white-space:nowrap;"),
                    *[ui.tags.td(f"{val:.4f}", style="text-align:right;") for val in df.loc[row]],
                )
                for row in df.index
            ]
        )
        table = ui.tags.table(
            header,
            body,
            class_="table table-sm table-bordered",
        )

        ui.modal_show(
            ui.modal(
                ui.tags.h5("Wilks' Lambda Cluster Statistics", style="margin-bottom:10px;"),
                table,
                title=None,
                easy_close=True,
                footer=ui.modal_button("Close"),
                size="l",
            )
        )

    @reactive.effect
    @reactive.event(input.qda_nx)
    def _handle_change_nx() -> None:
        nx = input.qda_nx()
        if nx is not None and not reactive_values["qda_results"]():
            ui.update_slider("lcp_classes", max=nx, min=2)

    @reactive.effect
    @reactive.event(input.lcp_classes)
    def _handle_lcp_classes() -> None:

        results = reactive_values["qda_results"]()
        if not results:
            return

        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]

        n = input.lcp_classes()

        if (
            results["class_analysis"]["NewData"] is None
            or f"{n}cluster" not in results["class_analysis"]["NewData"]
        ):
            ui.notification_show(
                f"QDA results do not contain a classification for {n} classes. Please choose a different number.",
                type="error",
            )
            return

        map_raster = make_qda_raster(results["class_analysis"], n)
        _map_raster.set(map_raster)

        reactive_values["lcp_results"] = reactive.Value([])
        drawn_shapes.set([])

        overlay = dataarray_to_image_overlay(map_raster, categorical=True, name="LUQDA Classes")
        my_ossa_layers.set([overlay])

    @reactive.effect
    @reactive.event(input.run_lcp)
    def _handle_run_lcp() -> None:

        qda = reactive_values["qda_results"]()
        if not qda:
            ui.notification_show(
                "Please run the QDA analysis first before running LCP.",
                type="error",
            )
            return

        if f"{input.lcp_classes()}cluster" not in qda["class_analysis"]["NewData"]:
            ui.notification_show(
                f"QDA results do not contain a valid classification for {input.lcp_classes()} classes. Please choose a different number.",
                type="error",
            )
            return

        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]
        map_raster = _map_raster()

        # Do LCP
        sites = lcp(
            map_raster,
            delta=input.lcp_delta(),
            zeta=input.lcp_zeta(),
            total=input.lcp_total(),
            grid=input.lcp_grid(),
        )
        results = {"lcp_sites": sites}

        drawn_shapes.set([])
        overlay = dataarray_to_image_overlay(map_raster, categorical=True, name="LUQDA Classes")
        lcp_df = results["lcp_sites"]
        points = make_point_layer(lcp_df, layer_name="LCP Sites")
        my_ossa_layers.set([overlay, points])

        reactive_values["lcp_results"].set(results)

    def validate_extracted_df(extracted_df: pd.DataFrame | None, response: str) -> bool:
        """Validate extracted DataFrame before running analysis."""
        if extracted_df is None:
            ui.notification_show(
                "Please run the data extraction first, or upload a csv", type="error"
            )
            return False

        if "longitude" not in extracted_df.columns or "latitude" not in extracted_df.columns:
            ui.notification_show(
                "Data table must contain 'longitude' and 'latitude' columns.", type="error"
            )
            return False

        if len(extracted_df.columns) <= 4:
            ui.notification_show(
                "DataFrame must contain more than one covariate column for analysis.",
                type="error",
            )
            return False

        response_data = extracted_df[response]

        is_integer_valued = pd.api.types.is_integer_dtype(response_data) or (
            pd.api.types.is_float_dtype(response_data)
            and response_data.dropna().apply(float.is_integer).all()
        )
        if not is_integer_valued:
            ui.notification_show(
                f"Response variable '{response}' must be categorical.",
                type="error",
            )
            return False

        if response_data.nunique() < 2:
            ui.notification_show(
                f"Response variable '{response}' must contain at least 2 unique classes.",
                type="error",
            )
            return False

        if response_data.nunique() > 20:
            ui.notification_show(
                f"Response variable '{response}' contains more than 20 unique classes, which may lead to unstable QDA results. Consider reducing the number of classes or choosing a different response variable.",
                type="warning",
            )
            return False

        return True
