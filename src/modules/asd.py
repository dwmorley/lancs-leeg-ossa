from datetime import datetime

from faicons import icon_svg
from shiny import module, reactive, ui

from runner_analysis import do_asd
from src.constants import ASD_OPTIONS
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer
from src.utils.downloads import save_artifacts_zip


@module.ui
def asd_ui():
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

    @reactive.effect
    @reactive.event(input.save_asd)
    def _handle_save_asd() -> None:
        if not reactive_values["asd_results"]():
            ui.notification_show(
                "Please run the ASD analysis first.",
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
    def _handle_run_asd() -> None:

        my_ossa_layers = reactive_values["my_ossa_layers"]

        ui.notification_show("Running Adaptive Sampling...", type="message")
        target = input.asd_target._value
        results = do_asd()

        if target == "H":
            plot_title = "ASD Hotspot"
        else:
            plot_title = "ASD Uncertainty"

        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(map_raster, categorical=False, name=plot_title)
        lcp_df = results["asd_sites"]
        points = make_point_layer(lcp_df, layer_name="ASD Sites")
        my_ossa_layers.set([overlay, points])

        # Zoom to raster extents by updating the shared `drawn_shapes` reactive
        # value. The `map` module reacts to `drawn_shapes` and will set the
        # draw control and call `fit_bounds` on the map widget.
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
