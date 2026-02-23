from shiny import module, reactive, ui

from constants import ASD_OPTIONS
from runner_analysis import do_asd
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer


@module.ui
def asd_ui():
    return ui.div(
        ui.h4("Adaptive Spatial Design"),
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
        ui.div({"class": "qda-actions"}, ui.input_action_button("run_asd", "Run")),
    )


@module.server
def asd_server(input, output, session, reactive_values):

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
        overlay = dataarray_to_image_overlay(
            map_raster, categorical=False, name=plot_title
        )
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
