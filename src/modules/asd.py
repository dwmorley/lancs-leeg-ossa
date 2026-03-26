"""ASD UI and server components for ASD sampling in OSSA."""

import asyncio
import queue
from datetime import datetime

import geopandas as gpd
import pandas as pd
import xarray as xr
from faicons import icon_svg
from shiny import module, reactive, ui

from src.constants import ASD_OPTIONS
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer
from src.sampling.asd_routine import asd_via_rpy2
from src.utils.downloads import save_artifacts_zip


@module.ui
def asd_ui():
    """Return UI components for the ASD panel."""
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("Adaptive Sampling Design", class_="column-header"),
                        ui.div(
                            ui.div(
                                {"style": "padding-top: 12px;"},
                                ui.input_radio_buttons(
                                    "asd_model",
                                    None,
                                    choices={
                                        "glmmPQL": "Penalized Quasi-Likelihood GLMM",
                                        "spglm": "Spatial GLM",
                                    },
                                    selected="glmmPQL",
                                ),
                            ),
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
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
                # Right column (empty for now)
            ],
            class_="content-columns",
        ),
        ui.tags.div(
            [
                ui.tooltip(
                    ui.input_action_button(
                        "save_asd",
                        ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    "Export ASD results",
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
    """Server logic for ASD controls (currently a placeholder)."""

    @reactive.effect
    @reactive.event(input.save_asd)
    def _handle_save_asd() -> None:
        if not reactive_values["asd_results"]():
            ui.notification_show(
                "Nothing to export. Please run the ASD analysis first.",
                type="error",
            )
            return

        asd_sites = reactive_values["asd_results"]()["asd_sites"]
        asd_raster = reactive_values["asd_results"]()["map_raster"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        asd_sites_gpkg = gpd.GeoDataFrame(
            asd_sites, geometry=gpd.points_from_xy(asd_sites.x, asd_sites.y), crs="EPSG:4326"
        )

        zip_path = save_artifacts_zip(
            zip_name=f"asd_results_{timestamp}.zip",
            csv_artifacts={"asd_sites.csv": asd_sites},
            gpkg_artifacts={"asd_sites.gpkg": asd_sites_gpkg},
            raster_artifacts={"asd_raster.tif": asd_raster},
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
        target = input.asd_target()

        # TODO: area will come from Leaflet, not specified grid?.
        # TODO: Validate CSV input not for when not hard-typing Benin.

        # Capture the R callbacks
        msg_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        def _on_progress(value: float, message: str, detail: str = "") -> None:
            msg_queue.put((value, message, detail))

        def do_asd(
            model: str,
            df: pd.DataFrame,
            formulaf: str,
            formular: str,
            target: str,
            total: int = 15,
            delta: float = 0.01,
            on_progress=None,
        ) -> dict[str, pd.DataFrame | xr.DataArray]:
            """Perform ASD sampling and analysis on the provided dataset."""
            debug = True
            if debug:
                df = pd.read_csv("test_data/benin.csv")
                area = pd.read_csv("test_data/beningrid.csv")
                formulaf = "AnGam~Week+Elev+Soil"
                formular = "~1|LCD"
            else:
                area = df[["longitude", "latitude"]]

            map_raster, sites = asd_via_rpy2(
                model=model,
                formulaf=formulaf,
                formular=formular,
                data=df,
                area=area,
                target=target,
                total=total,
                delta=delta,
                on_progress=on_progress,
            )

            return {
                "map_raster": map_raster,
                "asd_sites": sites,
            }

        # Launch R computation in a thread so the event loop stays unblocked.
        task = asyncio.create_task(
            asyncio.to_thread(
                do_asd,
                model=input.asd_model(),
                df=extracted_df,
                formulaf=input.asd_formulaf(),
                formular=input.asd_formular(),
                target=target,
                on_progress=_on_progress,
            )
        )

        with ui.Progress(min=0, max=1) as p:
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

        if target == "H":
            plot_title = "ASD Hotspot"
        else:
            plot_title = "ASD Uncertainty"

        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(map_raster, categorical=False, name=plot_title)
        lcp_df = results["asd_sites"]
        points = make_point_layer(lcp_df, layer_name="ASD Sites")
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
            map_ref = reactive_values.get("map_ref")
            if map_ref is not None:
                m = map_ref.get("m")
                if m is not None:
                    try:
                        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
                    except Exception:
                        pass

        reactive_values["asd_results"].set(results)
