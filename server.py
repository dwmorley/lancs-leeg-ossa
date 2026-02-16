import leafmap
from ipyleaflet import DrawControl, LayersControl
from shiny import reactive, render, ui
from shinywidgets import render_widget

from runner_extract import run_extraction


def server(input, output, session):

    # Store drawn rectangles
    drawn_shapes = reactive.Value([])

    # Flag to prevent infinite loops when updating bounds
    updating_from_map = reactive.Value(False)

    # Create the map once using leafmap
    m = leafmap.Map(
        center=(1.5, 20.0),  # Africa
        zoom=3,
        height="800px",
        width="100%",
        draw_control=False,
        toolbar_control=False,
    )

    # Add basemap layers
    m.add_basemap("Esri.WorldImagery")

    # Add layer control for toggling basemaps
    m.add(LayersControl(position="topright"))

    # Create drawing control
    draw_control = DrawControl(
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

    # Add to map
    m.add(draw_control)

    # Use traitlets observe to capture draw events
    def on_draw_change(change):
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

                # Update the input fields
                updating_from_map.set(True)
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
                updating_from_map.set(False)

    # Observe changes to last_draw trait
    draw_control.observe(on_draw_change, "last_draw")

    # Ensure landcover is always selected
    @reactive.effect
    @reactive.event(input.covariate_vars)
    def _keep_landcover_selected():
        current_vars = input.covariate_vars()
        if current_vars is None or "landcover" not in current_vars:
            # Re-add landcover if it was unchecked
            new_vars = list((current_vars or [])) + ["landcover"]
            ui.update_checkbox_group("covariate_vars", selected=new_vars)

    @render.text
    def summary_text():
        return "Dynamic summary information will appear here."

    # Auto-swap bounds when they cross
    def _swap_bounds_if_needed(val1_str, val2_str, id1, id2):
        """Swap two bound values if val1 > val2"""
        if val1_str and val2_str:
            try:
                val1 = float(val1_str)
                val2 = float(val2_str)
                if val1 > val2:
                    updating_from_map.set(True)
                    ui.update_text(id1, value=f"{val2:.4f}")
                    ui.update_text(id2, value=f"{val1:.4f}")
                    updating_from_map.set(False)
            except ValueError:
                pass

    @reactive.effect
    @reactive.event(input.bounds_west, input.bounds_east)
    def _auto_swap_west_east():
        if not updating_from_map.get():
            _swap_bounds_if_needed(
                input.bounds_west(), input.bounds_east(), "bounds_west", "bounds_east"
            )

    @reactive.effect
    @reactive.event(input.bounds_south, input.bounds_north)
    def _auto_swap_south_north():
        if not updating_from_map.get():
            _swap_bounds_if_needed(
                input.bounds_south(),
                input.bounds_north(),
                "bounds_south",
                "bounds_north",
            )

    # Update rectangle on map when bounds inputs change
    @reactive.effect
    @reactive.event(
        input.bounds_north, input.bounds_south, input.bounds_east, input.bounds_west
    )
    def _update_rectangle_from_inputs():
        # Skip if we're updating from a map draw event
        if updating_from_map.get():
            return

        # Skip if invalid numeric input
        try:
            north = float(input.bounds_north()) if input.bounds_north() else None
            south = float(input.bounds_south()) if input.bounds_south() else None
            east = float(input.bounds_east()) if input.bounds_east() else None
            west = float(input.bounds_west()) if input.bounds_west() else None
        except ValueError:
            return

        # Only update if all bounds are set
        if all(v is not None for v in [north, south, east, west]):
            # Create GeoJSON for the rectangle
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

            # Update the draw control data
            draw_control.data = [geo_json]

            # Update stored shapes
            rectangle_data = {
                "type": "rectangle",
                "geometry": geo_json["geometry"],
                "bounds": {"north": north, "south": south, "east": east, "west": west},
            }
            drawn_shapes.set([rectangle_data])

    @reactive.effect
    @reactive.event(input.run_analysis)
    def _handle_run_analysis():
        # Get current bounds
        bounds = drawn_shapes.get()
        if not bounds:
            ui.notification_show(
                "Please draw a rectangle on the map first.", type="warning"
            )
            return

        # Extract extents from rectangle
        extents = bounds[0]["bounds"]
        north = extents["north"]
        south = extents["south"]
        east = extents["east"]
        west = extents["west"]
        bbox = [min(west, east), min(south, north), max(west, east), max(south, north)]

        # Get selected variables and parameters
        selected_vars = input.covariate_vars()
        if len(selected_vars) <= 1:
            ui.notification_show(
                "Please select at least one additional variable to landcover.",
                type="warning",
            )
            return

        date_range = input.covariate_dates()
        sample_size = input.sample_size()
        save_stack = input.export_rasters()

        with ui.Progress(min=0, max=100) as p:
            p.set(message="Starting extraction...", value=0)

            df = run_extraction(
                bbox=bbox,
                variables=selected_vars,
                date_range=date_range,
                sample_size=sample_size,
                save_stack=save_stack,
                progress=p,
            )
            print(df)

        ui.notification_show(
            f"Processing complete! Extracted {len(selected_vars)} variables.",
            type="message",
            duration=None,
        )

        # TODO: TUESDAY Plot up the points, FIX THE PROGRESS BAR

        # Zoom map to fit the bounds
        m.fit_bounds([[south, west], [north, east]])

    @reactive.effect
    @reactive.event(input.help_btn)
    def _show_help_modal():
        ui.modal_show(
            ui.modal(
                ui.h4("Help"),
                ui.p("Add your help text or instructions here."),
                easy_close=True,
                footer=None,
            )
        )

    @render_widget
    def map():
        return m
