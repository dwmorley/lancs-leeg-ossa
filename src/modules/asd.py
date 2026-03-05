"""ASD UI and server components for ASD sampling in OSSA."""

import asyncio
import queue
from datetime import datetime

from faicons import icon_svg
from shiny import module, reactive, ui

from runner_analysis import do_asd
from src.constants import ASD_OPTIONS
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer
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
                                step=0.01,
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
                ui.input_action_button(
                    "save_asd",
                    ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                    class_="action-button",
                ),
                ui.input_action_button(
                    "run_asd",
                    ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                    class_="action-button",
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
                type="warning",
            )
            return

        asd_sites = reactive_values["asd_results"]()["asd_sites"]
        asd_raster = reactive_values["asd_results"]()["map_raster"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        zip_path = save_artifacts_zip(
            zip_name=f"asd_results_{timestamp}.zip",
            csv_artifacts={"asd_sites.csv": asd_sites},
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
        target = input.asd_target._value

        # Capture the R callbacks
        msg_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        def _on_progress(value: float, message: str, detail: str = "") -> None:
            msg_queue.put((value, message, detail))

        # Launch R computation in a thread so the event loop stays unblocked.
        task = asyncio.create_task(asyncio.to_thread(do_asd, on_progress=_on_progress))

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
