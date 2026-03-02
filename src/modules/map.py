import ipyleaflet as L
import leafmap
from ipyleaflet import DrawControl, LayersControl, WidgetControl
from shiny import module, reactive
from shinywidgets import output_widget, render_widget

from src.plotting.maps import point_layer_legend


@module.ui
def map_ui():
    return output_widget("map", width="100%", height="100%")


@module.server
def map_server(input, output, session, reactive_values):

    drawn_shapes = reactive_values["drawn_shapes"]
    updating_from_map = reactive_values["updating_from_map"]
    my_ossa_layers = reactive_values["my_ossa_layers"]

    draw_control = DrawControl(
        polyline={},
        polygon={},
        circle={},
        circlemarker={},
        marker={},
        rectangle={"shapeOptions": {"color": "red", "fillColor": "red", "fillOpacity": 0.2}},
        edit=False,
        remove=False,
    )

    def on_draw_remove(change) -> None:
        # Clear drawn_shapes when a shape is removed
        if change["new"]:
            drawn_shapes.set([])

    draw_control.observe(on_draw_remove, "last_remove")

    # Holder for the map widget so other effects or other modules can call methods
    m_ref = {"m": None}

    def on_draw_change(change) -> None:
        if change["new"] and change["new"].get("geometry"):
            geo_json = change["new"]
            if geo_json.get("geometry", {}).get("type") == "Polygon":
                coords = geo_json["geometry"]["coordinates"][0]
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]

                rectangle_data = {
                    "type": "rectangle",
                    "geometry": geo_json["geometry"],
                    "bounds": {
                        "north": max(lats),
                        "south": min(lats),
                        "east": max(lons),
                        "west": min(lons),
                    },
                }

                # Keep only the latest rectangle
                draw_control.data = [geo_json]
                drawn_shapes.set([rectangle_data])

    # Observe changes to last_draw trait
    draw_control.observe(on_draw_change, "last_draw")

    @reactive.effect
    @reactive.event(drawn_shapes)
    def _on_drawn_shapes_from_other() -> None:

        shapes = drawn_shapes.get()

        # Wrap map updates so other modules know this came from code, not user draw
        if not shapes:
            updating_from_map.set(True)
            try:
                draw_control.data = []
            finally:
                updating_from_map.set(False)
            return

        rectangle_data = shapes[0]
        geo = {
            "type": "Feature",
            "geometry": rectangle_data["geometry"],
            "properties": {},
        }

        updating_from_map.set(True)
        try:
            draw_control.data = [geo]
        finally:
            updating_from_map.set(False)

    @reactive.effect
    @reactive.event(input.delete_button)
    async def _():
        await session.send_custom_message("refresh", "")

    @reactive.effect
    @reactive.event(my_ossa_layers)
    def _render_my_layers() -> None:

        m = m_ref.get("m")
        if m is None:
            return

        base_layers = [
            lyr for lyr in m.layers if isinstance(lyr, (L.TileLayer, L.LayersControl, DrawControl))
        ]

        to_render = []
        legend_needed = ""
        for layer in my_ossa_layers.get():
            to_render.append(layer)
            if isinstance(layer, L.LayerGroup):
                legend_needed = layer.name

        m.layers = tuple(base_layers + to_render)

        # Remove any existing legend controls
        m.controls = tuple(
            c
            for c in m.controls
            if not (
                isinstance(c, WidgetControl)
                and getattr(c.widget, "value", "").find("LCP Sites") != -1
            )
        )
        # Add legend control if needed
        if legend_needed != "":
            legend_control = WidgetControl(
                widget=point_layer_legend(legend_needed), position="bottomright"
            )
            m.add_control(legend_control)

    @render_widget
    def map():

        m = leafmap.Map(
            center=(1.5, 20.0),
            zoom=3,
            draw_control=False,
            toolbar_control=False,
            scroll_wheel_zoom=True,
        )
        m.layout.width = "100%"
        m.layout.height = "100%"
        m.add_basemap("Esri.WorldImagery")
        m.add(LayersControl(position="topright"))
        m.add(draw_control)

        # expose map instance for other modules
        m_ref["m"] = m
        try:
            reactive_values["map_ref"] = m_ref
        except Exception:
            pass

        return m
