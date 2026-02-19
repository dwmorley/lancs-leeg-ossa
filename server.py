import base64
from io import BytesIO
from typing import List

import ipyleaflet as L
import leafmap
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from ipyleaflet import DrawControl, LayersControl, WidgetControl
from ipywidgets import HTML
from shiny import reactive, render, ui
from shinywidgets import render_widget

from runner_analysis import do_qda
from runner_extract import run_extraction
from src.gis.bounding_box import BoundingBox

# TODO: Refactor out the map module


def server(input, output, session) -> None:

    EXTRACTED_DF = None

    # created overlays
    my_ossa_layers = reactive.Value([])

    # Store drawn rectangles
    drawn_shapes = reactive.Value([])

    # Flag to prevent infinite loops when updating bounds
    updating_from_map = reactive.Value(False)

    # Create the map once using leafmap
    m = leafmap.Map(
        center=(1.5, 20.0),  # Africa
        zoom=3,
        height="750px",
        width="100%",
        draw_control=False,
        toolbar_control=False,
    )

    # Add basemap layers
    m.add_basemap("Esri.WorldImagery")

    # # Add layer control for toggling basemaps
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

    @reactive.effect
    @reactive.event(input.clear_shapes_btn)
    def _clear_drawn_shapes():
        draw_control.data = []
        drawn_shapes.set([])

    # Ensure landcover is always selected
    @reactive.effect
    @reactive.event(input.covariate_vars)
    def _keep_landcover_selected() -> None:
        current_vars = input.covariate_vars()
        if current_vars is None or "landcover" not in current_vars:
            # Re-add landcover if it was unchecked
            new_vars = list((current_vars or [])) + ["landcover"]
            ui.update_checkbox_group("covariate_vars", selected=new_vars)

    # Auto-swap bounds when they cross
    def _swap_bounds_if_needed(val1_str, val2_str, id1, id2) -> None:
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
    def _auto_swap_west_east() -> None:
        if not updating_from_map.get():
            _swap_bounds_if_needed(
                input.bounds_west(), input.bounds_east(), "bounds_west", "bounds_east"
            )

    @reactive.effect
    @reactive.event(input.bounds_south, input.bounds_north)
    def _auto_swap_south_north() -> None:
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
    def _update_rectangle_from_inputs() -> None:
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
    def _handle_run_analysis() -> None:

        nonlocal EXTRACTED_DF

        # Get current bounds
        bounds = drawn_shapes.get()
        if not bounds:
            ui.notification_show(
                "Please draw a rectangle on the map first.", type="warning"
            )
            return

        bbox = get_boundingbox(bounds)

        # Get selected variables and parameters
        selected_vars = input.covariate_vars()
        if len(selected_vars) <= 1:
            ui.notification_show(
                "Please select at least one additional variable to landcover.",
                type="warning",
            )
            return

        with ui.Progress(min=0, max=100) as p:
            p.set(message="Starting extraction...", value=0)

            EXTRACTED_DF = run_extraction(
                bbox=bbox,
                variables=selected_vars,
                date_range=input.covariate_dates(),
                sample_size=input.sample_size(),
                save_stack=input.export_rasters(),
                save_csv=input.export_csv(),
                progress=p,
            )

        ui.notification_show(
            "Data extraction complete!",
            type="message",
            duration=3,
        )

        m.fit_bounds([[bbox.ymin, bbox.xmin], [bbox.ymax, bbox.xmax]])

    @reactive.effect
    @reactive.event(input.run_qda)
    def _handle_run_qda() -> None:
        if EXTRACTED_DF is None:
            ui.notification_show(
                "Please run the data extraction first, or load a csv", type="warning"
            )
            return

        # Run QDA analysis
        results = do_qda(EXTRACTED_DF, input.qda_nx(), input.qda_nn())

        # Remove drawn bbox from the map and add LCP overlays
        draw_control.data = []
        drawn_shapes.set([])
        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(map_raster)
        lcp_df = results["lcp_sites"]
        points = make_point_layer(lcp_df)
        my_ossa_layers.set([overlay, points])

        # Show Wilks plot in modal
        # fig = results["wilks_plot"]
        # buf = BytesIO()
        # fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        # buf.seek(0)
        # img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        # plt.close(fig)
        # ui.modal_show(
        #     ui.modal(
        #         ui.h4("Wilks' Lambda Analysis"),
        #         ui.HTML(f'<img src="data:image/png;base64,{img_base64}" style="width:100%; max-width:800px;">'),
        #         ui.p(f"Found {results['best_n_classes']} optimal classes"),
        #         easy_close=True,
        #         size="l",
        #         footer=None,
        #     )
        # )

    @reactive.effect
    @reactive.event(input.data_file)
    def _handle_data_file() -> None:
        nonlocal EXTRACTED_DF

        file_info = input.data_file()
        if not file_info:
            ui.notification_show("Please select a CSV file first.", type="warning")
            return

        try:
            # Read the uploaded CSV file
            EXTRACTED_DF = pd.read_csv(file_info[0]["datapath"])

            # Get bounds from latitude and longitude columns
            north = EXTRACTED_DF["latitude"].max()
            south = EXTRACTED_DF["latitude"].min()
            east = EXTRACTED_DF["longitude"].max()
            west = EXTRACTED_DF["longitude"].min()

            # Update the input fields
            updating_from_map.set(True)
            ui.update_text("bounds_north", value=f"{north:.4f}")
            ui.update_text("bounds_south", value=f"{south:.4f}")
            ui.update_text("bounds_east", value=f"{east:.4f}")
            ui.update_text("bounds_west", value=f"{west:.4f}")
            updating_from_map.set(False)

            # Draw rectangle on map
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

            # Zoom map to fit the bounds
            m.fit_bounds([[south, west], [north, east]])

            ui.notification_show(
                f"Successfully loaded {len(EXTRACTED_DF)} rows from {file_info[0]['name']}",
                type="message",
                duration=3,
            )
        except Exception as e:
            ui.notification_show(f"Error reading CSV file: {str(e)}", type="error")
            EXTRACTED_DF = None

    @reactive.effect
    @reactive.event(input.help_btn)
    def _show_help_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.h4("Help"),
                ui.p("Add your help text or instructions here."),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.reset_btn)
    def _handle_reset() -> None:
        ui.modal_show(
            ui.modal(
                ui.h4("Reset"),
                ui.p("Are you sure you want to reset the application?"),
                ui.div(
                    {"class": "modal-buttons"},
                    ui.input_action_button(
                        "confirm_reset", "Confirm Reset", class_="btn-danger"
                    ),
                    ui.input_action_button(
                        "cancel_reset", "Cancel Reset", class_="btn-secondary"
                    ),
                ),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.confirm_reset)
    async def _():
        await session.send_custom_message("refresh", "")

    @reactive.effect
    @reactive.event(input.cancel_reset)
    def _close_reset_modal() -> None:
        ui.modal_remove()

    @reactive.effect
    def _() -> None:
        base_layers = [
            lyr
            for lyr in m.layers
            if isinstance(lyr, (L.TileLayer, L.LayersControl, DrawControl))
        ]
        to_render = []
        for layer in my_ossa_layers.get():
            to_render.append(layer)

        legend_control = WidgetControl(
            widget=point_layer_legend(), position="bottomright"
        )
        m.add_control(legend_control)

        m.layers = tuple(base_layers + to_render)

    @render_widget
    def map() -> L.Map:
        return m

    @render.text
    @reactive.event(drawn_shapes, input.sample_size)
    def sample_resolution() -> str:
        """
        This output is bound to `ui.output_text_verbatim('sample_resolution')`
        """
        shapes = drawn_shapes.get()
        sample_size = input.sample_size()
        if not shapes or not sample_size:
            return "--"
        try:
            bbox = get_boundingbox(shapes)
            bbox.sampling_grid(n=sample_size)
            return f"{bbox.resolution_m}m"
        except Exception:
            return "--"


def get_boundingbox(bounds: List[str]) -> BoundingBox:
    extents = bounds[0]["bounds"]
    north = extents["north"]
    south = extents["south"]
    east = extents["east"]
    west = extents["west"]
    return BoundingBox(
        [min(west, east), min(south, north), max(west, east), max(south, north)]
    )


def dataarray_to_image_overlay(da: xr.DataArray) -> L.ImageOverlay:

    data = da.values.astype(float)
    lats = np.array(da.coords.get("y", da.coords.get("lat", da.coords.get("latitude"))))
    lons = np.array(
        da.coords.get("x", da.coords.get("lon", da.coords.get("longitude")))
    )
    lat_res = np.abs(np.diff(lats)).mean() if len(lats) > 1 else 0.01
    lon_res = np.abs(np.diff(lons)).mean() if len(lons) > 1 else 0.01
    bounds = [
        [float(lats.min()) - 0.5 * lat_res, float(lons.min()) - 0.5 * lon_res],
        [float(lats.max()) + 0.5 * lat_res, float(lons.max()) + 0.5 * lon_res],
    ]

    fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
    ax.axis("off")
    cmap = cm.tab20 if np.unique(data).size <= 20 else cm.viridis
    origin = "lower" if lats[0] < lats[-1] else "upper"
    extent = (
        [
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[0][0],
            bounds[1][0],  # lat_min_edge, lat_max_edge
        ]
        if origin == "lower"
        else [
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[1][0],
            bounds[0][0],  # lat_max_edge, lat_min_edge
        ]
    )
    ax.imshow(data, cmap=cmap, origin=origin, extent=extent, interpolation="nearest")

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    return L.ImageOverlay(url=url, bounds=bounds, opacity=0.7, name="QDA Classes")


def make_point_layer(
    df,
) -> L.LayerGroup:
    markers = []
    for row in df.itertuples():
        marker = L.CircleMarker(
            location=(row.y, row.x),
            radius=8,
            color="green" if row.type == "G" else "blue",
            fill=False,
            fill_opacity=0.7,
        )
        markers.append(marker)

    return L.LayerGroup(layers=markers, name="LCP Sites")


def point_layer_legend() -> HTML:
    return HTML(
        value="""
        <div style='background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px;'>
            <b>LCP Sites</b><br>
            <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='green' stroke-width='3' fill='none'/></svg> Grid<br>
            <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='blue' stroke-width='3' fill='none'/></svg> Inhibitory<br>
        </div>
        """
    )
