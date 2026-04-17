"""ASD UI and server components for ASD sampling in OSSA."""

import asyncio
import queue
from datetime import datetime

import pandas as pd
import xarray as xr
from faicons import icon_svg
from shiny import module, reactive, render, ui

from src.constants import SDMTMB_OPTIONS
from src.sampling.sdmtmb_routine import sdmtmb_via_rpy2
from src.utils.downloads import save_artifacts_zip
from src.utils.r_base import RComputationBase


@module.ui
def sdmtmb_ui():
    """Return UI components for the ASD panel."""
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("ST Model with TMB", class_="column-header"),
                        ui.div(
                            ui.input_text(
                                "sdmtmb_formula",
                                "Model formula",
                                value=SDMTMB_OPTIONS["formula"],
                                placeholder="e.g. AnGam~Week+Elev+Soil",
                            ),
                            ui.output_ui("time_select_ui"),
                            ui.input_select(
                                "sdmtmb_family",
                                "Model family",
                                choices=SDMTMB_OPTIONS["family"],
                                selected="Poisson",
                            ),
                            ui.input_select(
                                "sdmtmb_spatial",
                                "Spatial random fields estimate",
                                choices=["On", "Off"],
                                selected="On",
                            ),
                            ui.input_select(
                                "sdmtmb_spatiotemporal",
                                "Spatiotemporal random fields estimate",
                                choices=["iid", "ar1", "rw", "off"],
                                selected="ar1",
                            ),
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
                # Right column
                ui.tags.div(
                    [
                        ui.h4("Available Response", class_="column-header"),
                        ui.output_ui("response_columns"),
                        ui.br(),
                        ui.h4("Available Variables", class_="column-header"),
                        ui.output_ui("prediction_columns"),
                    ]
                ),
            ],
            class_="content-columns",
        ),
        ui.tags.div(
            [
                ui.tooltip(
                    ui.input_action_button(
                        "save_sdmtmb",
                        ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    "Export ST Model results",
                    options={"delay": {"show": 1000, "hide": 0}},
                ),
                ui.tooltip(
                    ui.input_action_button(
                        "run_sdmtmb",
                        ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    "Run ST Model",
                    options={"delay": {"show": 1000, "hide": 0}},
                ),
            ],
            class_="button-container",
        ),
        class_="tab-content",
    )


@module.server
def sdmtmb_server(input, output, session, reactive_values):
    """Server logic for sdmTMB controls."""

    @reactive.effect
    @reactive.event(input.save_sdmtmb)
    def _handle_save_sdmtmb() -> None:

        if not reactive_values["sdmtmb_results"]():
            ui.notification_show(
                "Nothing to export. Please run the sdmTMB analysis first.",
                type="error",
            )
            return

        st_stats = reactive_values["sdmtmb_results"]()["sdmtmb_table"]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        zip_path = save_artifacts_zip(
            zip_name=f"stmodel_results_{timestamp}.zip",
            csv_artifacts={"stmodel_stats.csv": st_stats},
        )

        ui.notification_show(
            f"Results saved to {zip_path}",
            type="message",
        )

    @reactive.effect
    @reactive.event(input.run_sdmtmb)
    async def _handle_run_sdmtmb() -> None:

        extracted_df = reactive_values["extracted_df"]()
        prediction_df = reactive_values["prediction_df"]()
        formula = input.sdmtmb_formula()

        if not validate_df(extracted_df, prediction_df):
            return

        try:
            RComputationBase.validate_formula_syntax(formula, formula_name="Model formula")
        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return

        # Capture the R callbacks
        msg_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        def _on_progress(value: float, message: str, detail: str = "") -> None:
            msg_queue.put((value, message, detail))

        def do_sdmtmb(
            training_df: pd.DataFrame,
            prediction_df: pd.DataFrame,
            formula: str,
            family: str,
            time: str,
            spatial: str,
            spatiotemporal: str,
            on_progress=None,
        ) -> dict[str, pd.DataFrame | xr.DataArray]:
            """Perform sdmtmb analysis on the provided dataset."""
            sdmtmb_table = sdmtmb_via_rpy2(
                formula=formula,
                time=time,
                family=family,
                spatial=spatial,
                spatiotemporal=spatiotemporal,
                data=training_df,
                area=prediction_df,
                on_progress=on_progress,
            )

            return {
                "sdmtmb_table": sdmtmb_table,
            }

        # Launch R computation in a thread so the event loop stays unblocked.
        try:
            task = asyncio.create_task(
                asyncio.to_thread(
                    do_sdmtmb,
                    formula=input.sdmtmb_formula(),
                    family=input.sdmtmb_family(),
                    time=input.sdmtmb_time(),
                    spatial=input.sdmtmb_spatial(),
                    spatiotemporal=input.sdmtmb_spatiotemporal(),
                    training_df=extracted_df,
                    prediction_df=prediction_df,
                    on_progress=_on_progress,
                )
            )

            with ui.Progress(min=0, max=1) as p:
                p.set(0, message="Starting ST Model...")
                print("Started sdmtmb task, waiting for completion...")
                while not task.done():
                    await asyncio.sleep(0.1)
                    # Apply all queued updates; final one will be the most recent.
                    while not msg_queue.empty():
                        value, message, detail = msg_queue.get_nowait()
                        p.set(value, message=message, detail=detail)
                # Drain any last items after the task finishes.
                while not msg_queue.empty():
                    value, message, detail = msg_queue.get_nowait()
                    p.set(value, message=message, detail=detail)
                p.set(1, message="Done")

            results = task.result()

        except Exception as e:
            ui.notification_show(f"sdmTMB analysis failed: {str(e)}", type="error", duration=None)
            return

        reactive_values["sdmtmb_results"].set(results)

        ui.notification_show(
            ui.HTML(
                "sdmTMB analysis completed successfully!<br>" "<br>Export to use as input to ZSSA"
            ),
            type="message",
            duration=None,
        )

    @output
    @render.ui
    def time_select_ui():
        return ui.input_select(
            "sdmtmb_time",
            "Time",
            choices=get_time(),
            multiple=False,
        )

    @render.ui
    def prediction_columns():
        prediction_df = reactive_values["prediction_df"]()
        training_df = reactive_values["extracted_df"]()
        if prediction_df is not None and training_df is not None:
            common_cols = set(prediction_df.columns) & set(training_df.columns)
            common_cols -= {"longitude", "latitude"}
            if common_cols:
                return ui.tags.div(
                    ui.tags.ul(
                        [ui.tags.li(col) for col in sorted(common_cols)],
                        style="list-style-type: disc; margin-left: 2px; margin-bottom: 0;",
                    ),
                    style="border: 1px solid #ccc; border-radius: 6px; padding: 12px; background: #f9f9f9; margin-top: 8px; margin-bottom: 8px;",
                )
            else:
                return ui.div(
                    "Loaded Training and Prediction data have no common columns other than coordinates."
                )
        else:
            return ui.div("")

    @render.ui
    def response_columns():
        prediction_df = reactive_values["prediction_df"]()
        training_df = reactive_values["extracted_df"]()
        if prediction_df is not None and training_df is not None:
            response_cols = set(training_df.columns) - set(prediction_df.columns)
            response_cols -= {"longitude", "latitude"}
            if response_cols:
                return ui.tags.div(
                    ui.tags.ul(
                        [ui.tags.li(col) for col in sorted(response_cols)],
                        style="list-style-type: disc; margin-left: 2px; margin-bottom: 0;",
                    ),
                    style="border: 1px solid #ccc; border-radius: 6px; padding: 12px; background: #f9f9f9; margin-top: 8px; margin-bottom: 8px;",
                )
            else:
                return ui.div("No candidate response variable found")
        else:
            return ui.div("Training and/or Prediction data not loaded.")

    def get_time():
        prediction_df = reactive_values["prediction_df"]()
        training_df = reactive_values["extracted_df"]()
        if prediction_df is not None and training_df is not None:
            common_cols = set(prediction_df.columns) & set(training_df.columns)
            common_cols -= {"longitude", "latitude"}
            if common_cols:
                return ["None"] + [c for c in common_cols]
        return ["None"]

    def validate_df(extracted_df: pd.DataFrame, prediction_df: pd.DataFrame) -> bool:
        """Validate DataFrames before running analysis."""
        if extracted_df is None:
            ui.notification_show("Please upload a csv containing your training data", type="error")
            return False

        if prediction_df is None:
            ui.notification_show(
                "Please upload a csv containing your prediction data", type="error"
            )
            return False

        return True
