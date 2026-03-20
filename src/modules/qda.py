"""QDA UI and server components."""

import base64
from datetime import datetime
from io import BytesIO

import geopandas as gpd
import matplotlib.pyplot as plt
from faicons import icon_svg
from shiny import module, reactive, ui

from runner_analysis import do_qda
from src.constants import COVARIATE_OPTIONS, LCP_OPTIONS, QDA_OPTIONS, RESPONSE_OPTIONS
from src.plotting.maps import dataarray_to_image_overlay  # make_point_layer
from src.sampling.luqdaloop_routine import make_qda_raster
from src.utils.downloads import save_artifacts_zip
from src.utils.validate import validate_extracted_df


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
                        ui.input_numeric(
                            "lcp_classes",
                            "Classes to use",
                            value=None,
                            min=1,
                            step=1,
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
        if not reactive_values["lcp_results"]() and not reactive_values["qda_results"]():
            ui.notification_show(
                "Nothing to export. Please run the QDA/LCP analysis first.",
                type="error",
            )
            return

        # TODO: split to qda and lcp
        lcp_sites = reactive_values["qda_lcp_results"]()["lcp_sites"]
        qda_raster = reactive_values["qda_lcp_results"]()["map_raster"]
        wilks_plot = reactive_values["qda_lcp_results"]()["wilks_plot"]
        lcp_sites_gpkg = gpd.GeoDataFrame(
            lcp_sites, geometry=gpd.points_from_xy(lcp_sites.x, lcp_sites.y), crs="EPSG:4326"
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        zip_path = save_artifacts_zip(
            zip_name=f"qda_lcp_results_{timestamp}.zip",
            csv_artifacts={"lcp_sites.csv": lcp_sites},
            gpkg_artifacts={"lcp_sites.gpkg": lcp_sites_gpkg},
            raster_artifacts={"qda_raster.tif": qda_raster},
            figure_artifacts={"wilks_plot.png": wilks_plot},
        )
        plt.close(wilks_plot)

        ui.notification_show(
            f"Results saved to {zip_path}",
            type="info",
        )

    @reactive.effect
    @reactive.event(input.run_qda)
    def _handle_run_qda() -> None:

        extracted_df = reactive_values["extracted_df"]()
        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]

        if not validate_extracted_df(extracted_df):
            return

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

        # Run QDA analysis
        results = do_qda(df=extracted_df, response=response, nx=input.qda_nx(), nn=input.qda_nn())
        reactive_values["qda_results"].set(results)

        # Update the UI with recommended number of classes and corresponding raster
        ui.update_numeric("lcp_classes", value=results["best_n_classes"], min=1, max=input.qda_nx())

        map_raster = make_qda_raster(results["class_analysis"], results["best_n_classes"])

        drawn_shapes.set([])
        overlay = dataarray_to_image_overlay(map_raster, categorical=True, name="LUQDA Classes")
        my_ossa_layers.set([overlay])

        ui.notification_show(
            ui.HTML(
                f"QDA analysis recommends {results['best_n_classes']} classes.<br>You can adjust this after looking at the Wilks' Lambda statistics and plot."
            ),
            type="info",
        )

    @reactive.effect
    @reactive.event(input.show_wilks_plot)
    def _handle_show_wilks_plot() -> None:

        if not reactive_values["qda_results"]():
            ui.notification_show(
                "Please run the QDA analysis first to see the Wilks' Lambda plot.",
                type="warning",
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

    @reactive.effect
    @reactive.event(input.lcp_classes)
    def _handle_lcp_classes() -> None:
        # TODO: if QDA not existing, do not jump the numbers.
        print("LCP classes changed, but LCP routine not implemented yet.")

        # Run QDA analysis
        # results = do_qda_and_lcp(
        #     df=extracted_df,
        #     nx=input.qda_nx(),
        #     nn=input.qda_nn(),
        #     delta=input.lcp_delta(),
        #     zeta=input.lcp_zeta(),
        #     total=input.lcp_total(),
        #     grid=input.lcp_grid(),
        # )

        # # Remove drawn bbox from the map and add LCP overlays
        # drawn_shapes.set([])
        # map_raster = results["map_raster"]
        # overlay = dataarray_to_image_overlay(map_raster, categorical=True, name="LUQDA Classes")
        # lcp_df = results["lcp_sites"]
        # points = make_point_layer(lcp_df, layer_name="LCP Sites")
        # my_ossa_layers.set([overlay, points])

        # # Show Wilks plot in modal
        # fig = results["wilks_plot"]
        # buf = BytesIO()
        # fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        # buf.seek(0)
        # img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        # plt.close(fig)
        # ui.modal_show(
        #     ui.modal(
        #         ui.HTML(
        #             f'<img src="data:image/png;base64,{img_base64}" style="width:100%; max-width:800px;">'
        #         ),
        #         easy_close=True,
        #         size="l",
        #         footer=None,
        #     )
        # )

        # reactive_values["qda_lcp_results"].set(results)
