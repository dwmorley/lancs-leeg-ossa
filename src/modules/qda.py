import base64
from io import BytesIO

import matplotlib.pyplot as plt
from faicons import icon_svg
from shiny import module, reactive, ui

from constants import LCP_OPTIONS, QDA_OPTIONS
from runner_analysis import do_qda
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer


@module.ui
def qda_ui():
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("Discriminant Analysis", class_="column-header"),
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
                    ],
                    class_="column-content text-inputs-column",
                ),
                # Right column
                ui.tags.div(
                    [
                        ui.h4("Lattice Close Pairs", class_="column-header"),
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
                            step=0.01,
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
            ],
            class_="content-columns",
        ),
        ui.tags.div(
            [
                ui.input_action_button(
                    "save_qda",
                    ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                    class_="action-button",
                ),
                ui.input_action_button(
                    "run_qda",
                    ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                    class_="action-button",
                ),
            ],
            class_="button-container",
        ),
        class_="tab-content",
    )


@module.server
def qda_server(input, output, session, reactive_values):

    @reactive.effect
    @reactive.event(input.run_qda)
    def _handle_run_qda() -> None:

        extracted_df = reactive_values.get("extracted_df")
        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]

        if extracted_df is None:
            ui.notification_show(
                "Please run the data extraction first, or load a csv", type="warning"
            )
            return

        # Run QDA analysis
        results = do_qda(extracted_df, input.qda_nx(), input.qda_nn())

        # Remove drawn bbox from the map and add LCP overlays
        # draw_control.data = []
        drawn_shapes.set([])
        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(
            map_raster, categorical=True, name="LUQDA Classes"
        )
        lcp_df = results["lcp_sites"]
        points = make_point_layer(lcp_df, layer_name="LCP Sites")
        my_ossa_layers.set([overlay, points])

        # Show Wilks plot in modal
        fig = results["wilks_plot"]
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        plt.close(fig)
        ui.modal_show(
            ui.modal(
                ui.h4("Wilks' Lambda Analysis"),
                ui.HTML(
                    f'<img src="data:image/png;base64,{img_base64}" style="width:100%; max-width:800px;">'
                ),
                ui.p(f"Found {results['best_n_classes']} optimal classes"),
                easy_close=True,
                size="l",
                footer=None,
            )
        )
