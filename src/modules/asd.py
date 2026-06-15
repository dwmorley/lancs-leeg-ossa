"""ASD UI and server components for ASD sampling in OSSA."""

import asyncio
import queue
from datetime import datetime

import geopandas as gpd
import pandas as pd
import xarray as xr
from faicons import icon_svg
from shiny import module, reactive, render, ui

from src.constants import ASD_OPTIONS, URLS
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer
from src.sampling.asd_routine import asd_via_rpy2
from src.utils.downloads import save_artifacts_zip
from src.utils.progress import non_closeable_progress
from src.utils.r_base import RComputationBase

DEBUG = False


@module.ui
def asd_ui():
    """Return UI components for the ASD panel."""
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("Single Criterion Adaptive Sampling Design", class_="column-header"),
                        ui.div(
                            ui.div(
                                {"style": "padding-top: 12px;"},
                                ui.input_radio_buttons(
                                    "asd_model",
                                    None,
                                    choices={
                                        "glmmPQL": "Penalized Quasi-Likelihood GLMM",
                                        "spglm": "Spatial GLM",
                                        "spatial_design": "Spatial Design Only",
                                    },
                                    selected="glmmPQL",
                                ),
                            ),
                            ui.output_ui("model_dependent_inputs"),
                            ui.input_numeric(
                                "asd_total",
                                "Adaptive sampling locations to allocate",
                                value=ASD_OPTIONS["total"],
                                min=1,
                                step=1,
                            ),
                            ui.input_numeric(
                                "asd_delta",
                                "Inhibition distance (delta)",
                                value=ASD_OPTIONS["delta"],
                                min=0.001,
                                step=0.001,
                            ),
                            ui.input_numeric(
                                "asd_resolution",
                                "Surface sampling resolution",
                                value=ASD_OPTIONS["resolution"],
                                min=10,
                                step=10,
                            ),
                        ),
                        ui.div(
                            {"style": "padding-top: 12px;"},
                            ui.input_radio_buttons(
                                "asd_target",
                                None,
                                choices={
                                    "H": "Targeting Hotspots",
                                    "U": "Targeting Uncertainty",
                                },
                                selected=ASD_OPTIONS["target"],
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
                        "r_info_asd",
                        ui.tags.span(
                            [
                                ui.tags.i(
                                    class_="devicon-r-original",
                                    style="font-size: 16px; color: black;",
                                )
                            ],
                            class_="icon-square-btn",
                        ),
                        class_="action-button",
                    ),
                    "Show R help pages for this model",
                    options={"delay": {"show": 1000, "hide": 0}},
                ),
                ui.tooltip(
                    ui.input_action_button(
                        "save_asd",
                        ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    "Export Single-Criterion ASD results",
                    options={"delay": {"show": 1000, "hide": 0}},
                ),
                ui.tooltip(
                    ui.input_action_button(
                        "run_asd",
                        ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    "Run ASD analysis",
                    options={"delay": {"show": 1000, "hide": 0}},
                ),
            ],
            class_="button-container",
        ),
        class_="tab-content",
    )


@module.server
def asd_server(input, output, session, reactive_values):
    """Server logic for ASD controls."""

    @reactive.effect
    @reactive.event(input.r_info_asd)
    async def _handle_r_info_asd():
        url = URLS.get(input.asd_model())
        if url is not None:
            await session.send_custom_message("open_url", {"url": url})

    @reactive.effect
    @reactive.event(input.save_asd)
    def _handle_save_asd() -> None:
        if not reactive_values["sc-asd_results"]():
            ui.notification_show(
                "Nothing to export. Please run the Single-Criterion ASD analysis first.",
                type="error",
            )
            return

        asd_sites = reactive_values["sc-asd_results"]()["sc-asd_sites"]
        asd_raster = reactive_values["sc-asd_results"]()["map_raster"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        asd_sites_gpkg = gpd.GeoDataFrame(
            asd_sites, geometry=gpd.points_from_xy(asd_sites.x, asd_sites.y), crs="EPSG:4326"
        )

        zip_path = save_artifacts_zip(
            zip_name=f"sc-asd_results_{timestamp}.zip",
            csv_artifacts={"sc-asd_sites.csv": asd_sites},
            gpkg_artifacts={"sc-asd_sites.gpkg": asd_sites_gpkg},
            kml_artifacts={"sc-asd_sites.kml": asd_sites_gpkg},
            raster_artifacts={"sc-asd_raster.tif": asd_raster},
        )

        ui.notification_show(
            f"Results saved to {zip_path}",
            type="message",
        )

    @reactive.effect
    @reactive.event(input.run_asd)
    async def _handle_run_asd() -> None:

        my_ossa_layers = reactive_values["my_ossa_layers"]
        extracted_df = reactive_values["extracted_df"]()
        prediction_df = reactive_values["prediction_df"]()
        target = input.asd_target()
        model = input.asd_model()

        formulaf = input.asd_formulaf()
        formular = input.asd_formular()
        existing_target = (input.asd_existing_target1(), input.asd_existing_target2())

        if model == "spatial_design":
            if not validate_extracted_df(prediction_df):
                return

            extracted_df = None
        else:
            if not validate_extracted_df(extracted_df):
                return

        try:

            if model == "spatial_design":
                if existing_target is None:
                    raise ValueError("No existing target variable provided")

            else:
                RComputationBase.validate_fixed_formula_syntax(
                    formulaf, formula_name="Fixed effects formula"
                )

                if model == "glmmPQL" or formular.strip():
                    RComputationBase.validate_random_formula_syntax(
                        formular, formula_name="Random effects formula"
                    )

        except ValueError as e:
            ui.notification_show(str(e), type="error")
            return

        # Validate random effects formula (formular format is different: ~1|LCD)
        if model != "spatial_design":
            if formular and formular.strip():
                try:
                    if "~" not in formular:
                        raise ValueError(
                            "Random effects formula must contain a tilde (~) separator. "
                            "Expected format: ~effect (e.g., ~1|LCD)"
                        )
                    left_side = formular.split("~")[0].strip()
                    if left_side:
                        raise ValueError(
                            "Random effects formula must have nothing on the left side of the tilde (~). "
                            "Expected format: ~effect (e.g., ~1|LCD)"
                        )
                except ValueError as e:
                    ui.notification_show(str(e), type="error")
                    return

        # Capture the R callbacks
        msg_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        def _on_progress(value: float, message: str, detail: str = "") -> None:
            msg_queue.put((value, message, detail))

        def do_asd(
            model: str,
            training_df: pd.DataFrame,
            prediction_df: pd.DataFrame,
            formulaf: str,
            formular: str,
            existing_target: tuple[str, str],
            target: str,
            family: str,
            total: int = 15,
            delta: float = 0.01,
            resolution: int = 10,
            on_progress=None,
        ) -> dict[str, pd.DataFrame | xr.DataArray]:
            """Perform ASD sampling and analysis on the provided dataset."""
            if DEBUG:
                formulaf = "AnGam~Week+Elev+Soil"
                formular = "~1|LCD"

            map_raster, sites = asd_via_rpy2(
                model=model,
                formulaf=formulaf,
                formular=formular,
                data=training_df,
                area=prediction_df,
                target=target,
                existing_target=existing_target,
                family=family,
                total=total,
                delta=delta,
                resolution=resolution,
                on_progress=on_progress,
            )

            return {
                "map_raster": map_raster,
                "sc-asd_sites": sites,
            }

        # Launch R computation in a thread so the event loop stays unblocked.
        try:
            task = asyncio.create_task(
                asyncio.to_thread(
                    do_asd,
                    model=model,
                    training_df=extracted_df,
                    prediction_df=prediction_df,
                    formulaf=input.asd_formulaf(),
                    formular=input.asd_formular(),
                    existing_target=(input.asd_existing_target1(), input.asd_existing_target2()),
                    target=target,
                    family=input.asd_family(),
                    resolution=input.asd_resolution(),
                    on_progress=_on_progress,
                )
            )

            with non_closeable_progress(min=0, max=1) as p:
                p.set(0, message="Starting Adaptive Sampling...")
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

            if results["sc-asd_sites"].isnull().values.any():
                ui.notification_show(
                    "Single-Criterion ASD analysis model created, but required sites number of sites could not be identified, please check model parameters and your input data.",
                    type="error",
                    duration=None,
                )
                return

        except Exception as e:
            ui.notification_show(
                f"Single-Criterion ASD analysis failed: {str(e)}", type="error", duration=None
            )
            return

        if target == "H":
            plot_title = "SC-ASD Hotspot"
        else:
            plot_title = "SC-ASD Uncertainty"

        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(map_raster, categorical=False, name=plot_title)
        lcp_df = results["sc-asd_sites"]
        points = make_point_layer(lcp_df, layer_name="SC-ASD Sites")
        my_ossa_layers.set([overlay, points])

        # Zoom to raster extents
        drawn_shapes = reactive_values.get("drawn_shapes")
        if drawn_shapes is not None:
            lats = map_raster.coords.get(
                "y", map_raster.coords.get("lat", map_raster.coords.get("latitude"))
            )
            lons = map_raster.coords.get(
                "x", map_raster.coords.get("lon", map_raster.coords.get("longitude"))
            )
            lat_min = float(lats.min())
            lat_max = float(lats.max())
            lon_min = float(lons.min())
            lon_max = float(lons.max())

            # Do not draw a rectangle; just instruct the map to fit these bounds.
            drawn_shapes.set([])
            map_ref = reactive_values.get("map_ref")
            if map_ref is not None:
                m = map_ref.get("m")
                if m is not None:
                    try:
                        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
                    except Exception:
                        pass

        reactive_values["sc-asd_results"].set(results)

    @render.ui
    def model_dependent_inputs():
        if input.asd_model() == "spatial_design":
            return ui.div(
                ui.input_select(
                    "asd_existing_target1",
                    "Target variable",
                    choices=get_target(),
                ),
                ui.input_select(
                    "asd_existing_target2",
                    "Target variable uncertainty",
                    choices=get_target(),
                ),
            )
        return ui.div(
            ui.input_text(
                "asd_formulaf",
                "Fixed effects formula",
                value=ASD_OPTIONS["formulaf"],
                placeholder="e.g. AnGam~Week+Elev+Soil",
            ),
            ui.input_text(
                "asd_formular",
                "Random effects formula",
                value=ASD_OPTIONS["formular"],
                placeholder="e.g. ~1|LCD",
            ),
            ui.input_select(
                "asd_family",
                "Model family",
                choices=ASD_OPTIONS["family"],
                selected="Poisson",
            ),
        )

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

    @render.ui
    def prediction_columns():
        prediction_df = reactive_values["prediction_df"]()
        training_df = reactive_values["extracted_df"]()
        if input.asd_model() != "spatial_design":
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
        else:
            if prediction_df is not None:
                cols = set(prediction_df.columns)
                cols -= {"longitude", "latitude"}
                if cols:
                    return ui.tags.div(
                        ui.tags.ul(
                            [ui.tags.li(col) for col in sorted(cols)],
                            style="list-style-type: disc; margin-left: 2px; margin-bottom: 0;",
                        ),
                        style="border: 1px solid #ccc; border-radius: 6px; padding: 12px; background: #f9f9f9; margin-top: 8px; margin-bottom: 8px;",
                    )
                else:
                    return ui.div("No candidate target variables found")
            return ui.div("Prediction data not loaded.")

    def validate_extracted_df(extracted_df: pd.DataFrame | None) -> bool:
        """Validate extracted DataFrame before running analysis."""
        if extracted_df is None:
            ui.notification_show("Please upload a csv containing your data", type="error")
            return False

        return True

    def get_target():
        prediction_df = reactive_values["prediction_df"]()
        if prediction_df is not None:
            cols = set(prediction_df.columns)
            cols -= {"longitude", "latitude"}
            if cols:
                return [c for c in cols]
        return []
