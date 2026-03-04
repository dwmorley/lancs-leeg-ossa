"""Module for defining the AOI, i.e. the bounding box for the analysis."""

from shiny import module, reactive, ui


@module.ui
def aoi_ui():
    """Return UI components for the AOI tab, which includes text inputs for bounding box coordinates."""
    return ui.tags.div(
        ui.div(
            ui.div(
                ui.input_text("bounds_north", "North", value="", placeholder="--"),
                class_="bounds-cell",
            ),
            ui.div(
                ui.input_text("bounds_south", "South", value="", placeholder="--"),
                class_="bounds-cell",
            ),
            ui.div(
                ui.input_text("bounds_east", "East", value="", placeholder="--"),
                class_="bounds-cell",
            ),
            ui.div(
                ui.input_text("bounds_west", "West", value="", placeholder="--"),
                class_="bounds-cell",
            ),
            class_="bounds-row",
        ),
    )


@module.server
def aoi_server(input, output, session, reactive_values):
    """Server-side logic for AOI tab, syncing text inputs with drawn shapes on the map."""
    drawn_shapes = reactive_values["drawn_shapes"]
    updating_from_map = reactive_values["updating_from_map"]

    @reactive.effect
    @reactive.event(drawn_shapes)
    def _on_drawn_shapes() -> None:
        # Don't react if the map is the source of the update
        if updating_from_map.get():
            return

        shapes = drawn_shapes.get()
        if not shapes:
            # Clear fields when there are no shapes
            updating_from_map.set(True)
            try:
                ui.update_text("bounds_north", value="")
                ui.update_text("bounds_south", value="")
                ui.update_text("bounds_east", value="")
                ui.update_text("bounds_west", value="")
            finally:
                updating_from_map.set(False)
            return

        # Use the most-recent rectangle
        rectangle_data = shapes[0]

        updating_from_map.set(True)
        try:
            ui.update_text("bounds_north", value=f"{rectangle_data['bounds']['north']:.4f}")
            ui.update_text("bounds_south", value=f"{rectangle_data['bounds']['south']:.4f}")
            ui.update_text("bounds_east", value=f"{rectangle_data['bounds']['east']:.4f}")
            ui.update_text("bounds_west", value=f"{rectangle_data['bounds']['west']:.4f}")
        finally:
            updating_from_map.set(False)

    @reactive.effect
    @reactive.event(input.bounds_north, input.bounds_south, input.bounds_east, input.bounds_west)
    def _update_from_inputs() -> None:
        # Avoid reacting to updates that originated from the map
        if updating_from_map.get():
            return

        # Parse numeric inputs; if any missing, clear shapes
        try:
            north = float(input.bounds_north()) if input.bounds_north() else None
            south = float(input.bounds_south()) if input.bounds_south() else None
            east = float(input.bounds_east()) if input.bounds_east() else None
            west = float(input.bounds_west()) if input.bounds_west() else None
        except ValueError:
            return

        # Flip if we are crossing meridian or equator
        def _swap_if_less(val1, val2):
            if val1 is None or val2 is None:
                return val1, val2
            if val1 < val2:
                return val2, val1
            return val1, val2

        # Ensure east >= west and north >= south
        east, west = _swap_if_less(east, west)
        north, south = _swap_if_less(north, south)

        if not all(v is not None for v in [north, south, east, west]):
            drawn_shapes.set([])
            return

        # Build GeoJSON for rectangle and update shared reactive
        geo_json = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                        [west, south],
                    ]
                ],
            },
            "properties": {},
        }

        rectangle_data = {
            "type": "rectangle",
            "geometry": geo_json["geometry"],
            "bounds": {"north": north, "south": south, "east": east, "west": west},
        }

        # Only update text fields and drawn_shapes if not updating_from_map
        updating_from_map.set(True)
        try:
            ui.update_text("bounds_north", value=f"{rectangle_data['bounds']['north']:.4f}")
            ui.update_text("bounds_south", value=f"{rectangle_data['bounds']['south']:.4f}")
            ui.update_text("bounds_east", value=f"{rectangle_data['bounds']['east']:.4f}")
            ui.update_text("bounds_west", value=f"{rectangle_data['bounds']['west']:.4f}")
            drawn_shapes.set([rectangle_data])
        finally:
            updating_from_map.set(False)
