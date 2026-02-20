# Delay heavy widget imports (leafmap/ipyleaflet) until a Shiny session is active.
_lazy = {}


class MapManager:
    """Encapsulates map creation and draw control handling.

    The actual ipyleaflet `Map` and draw controls are created lazily via
    `create_map()` so they are constructed inside an active Shiny session.
    """

    def __init__(self):
        self.m = None
        self.draw_control = None

    def create_map(self):
        """Create the `leafmap.Map` and draw controls. Call from `server()`.

        Safe to call multiple times; will no-op if already created.
        """
        if self.m is not None:
            return

        # Import here to ensure ipywidgets are created within an active Shiny session
        import ipyleaflet as L
        from ipyleaflet import (
            DrawControl,
            LayersControl,
            Map,
            basemap_to_tiles,
            basemaps,
        )
        from ipywidgets import Layout

        # store types locally for callers that may want to check isinstance
        _lazy["ipyleaflet"] = L
        _lazy["LayersControl"] = LayersControl
        _lazy["DrawControl"] = DrawControl

        self.m = Map(
            center=(1.5, 20.0),  # Africa
            zoom=3,
            layout=Layout(width="100%", height="100%"),
        )

        self.m.scroll_wheel_zoom = True
        self.m.add_layer(basemap_to_tiles(basemaps.Esri.WorldImagery))
        self.m.add_control(LayersControl(position="topright"))

        self.draw_control = DrawControl(
            polyline={},
            polygon={},
            circle={},
            circlemarker={},
            marker={},
            rectangle={
                "shapeOptions": {"color": "red", "fillColor": "red", "fillOpacity": 0.2}
            },
            edit=False,
            remove=False,
        )
        self.m.add_control(self.draw_control)

    def fit_bounds(self, bounds):
        if self.m is None:
            return
        self.m.fit_bounds(bounds)


class MapEvents:
    """Encapsulate reactive handlers and draw events for the leaflet map.

    Call `register(input, ui, reactive, map_mgr, data_mgr)` to wire handlers.
    """

    def register(self, input, ui, reactive_module, map_mgr, data_mgr):
        # draw observer (traitlets)
        def on_draw_change(change) -> None:
            if change.get("new") and change["new"].get("geometry"):
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

                    map_mgr.draw_control.data = [geo_json]
                    data_mgr.drawn_shapes.set([rectangle_data])

                    data_mgr.updating_from_map.set(True)
                    ui.update_text(
                        "bounds_north", value=f"{rectangle_data['bounds']['north']:.4f}"
                    )
                    ui.update_text(
                        "bounds_south", value=f"{rectangle_data['bounds']['south']:.4f}"
                    )
                    ui.update_text(
                        "bounds_east", value=f"{rectangle_data['bounds']['east']:.4f}"
                    )
                    ui.update_text(
                        "bounds_west", value=f"{rectangle_data['bounds']['west']:.4f}"
                    )
                    data_mgr.updating_from_map.set(False)

        # draw_control is created in create_map(); ensure it exists before observing
        if map_mgr.draw_control is not None:
            map_mgr.draw_control.observe(on_draw_change, "last_draw")

        # Clear shapes handler
        def _clear_drawn_shapes():
            map_mgr.draw_control.data = []
            data_mgr.drawn_shapes.set([])

        reactive_module.effect(
            reactive_module.event(input.clear_shapes_btn)(_clear_drawn_shapes)
        )

        # Swap helper used by the auto-swap handlers
        def _swap_bounds_if_needed(val1_str, val2_str, id1, id2) -> None:
            if val1_str and val2_str:
                try:
                    val1 = float(val1_str)
                    val2 = float(val2_str)
                    if val1 > val2:
                        data_mgr.updating_from_map.set(True)
                        ui.update_text(id1, value=f"{val2:.4f}")
                        ui.update_text(id2, value=f"{val1:.4f}")
                        data_mgr.updating_from_map.set(False)
                except ValueError:
                    pass

        # Auto-swap west/east
        def _auto_swap_west_east() -> None:
            if not data_mgr.updating_from_map.get():
                _swap_bounds_if_needed(
                    input.bounds_west(),
                    input.bounds_east(),
                    "bounds_west",
                    "bounds_east",
                )

        reactive_module.effect(
            reactive_module.event(input.bounds_west, input.bounds_east)(
                _auto_swap_west_east
            )
        )

        # Auto-swap south/north
        def _auto_swap_south_north() -> None:
            if not data_mgr.updating_from_map.get():
                _swap_bounds_if_needed(
                    input.bounds_south(),
                    input.bounds_north(),
                    "bounds_south",
                    "bounds_north",
                )

        reactive_module.effect(
            reactive_module.event(input.bounds_south, input.bounds_north)(
                _auto_swap_south_north
            )
        )

        # Update rectangle on map when bounds inputs change
        def _update_rectangle_from_inputs() -> None:
            if data_mgr.updating_from_map.get():
                return
            try:
                north = float(input.bounds_north()) if input.bounds_north() else None
                south = float(input.bounds_south()) if input.bounds_south() else None
                east = float(input.bounds_east()) if input.bounds_east() else None
                west = float(input.bounds_west()) if input.bounds_west() else None
            except ValueError:
                return

            if all(v is not None for v in [north, south, east, west]):
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

                map_mgr.draw_control.data = [geo_json]
                rectangle_data = {
                    "type": "rectangle",
                    "geometry": geo_json["geometry"],
                    "bounds": {
                        "north": north,
                        "south": south,
                        "east": east,
                        "west": west,
                    },
                }
                data_mgr.drawn_shapes.set([rectangle_data])

        reactive_module.effect(
            reactive_module.event(
                input.bounds_north,
                input.bounds_south,
                input.bounds_east,
                input.bounds_west,
            )(_update_rectangle_from_inputs)
        )
