from shiny import reactive, render, ui
from shinywidgets import render_widget

from src.gis.bounding_box import BoundingBox
from src.managers import (
    AnalysisManager,
    DataManager,
    FileManager,
    MapEvents,
    MapManager,
    ProgressManager,
)
from src.plotting.maps import point_layer_legend


def server(input, output, session) -> None:

    data_mgr = DataManager(reactive)
    map_mgr = MapManager()
    map_mgr.create_map()
    analysis_mgr = AnalysisManager()
    progress_mgr = ProgressManager()
    file_mgr = FileManager()

    MapEvents().register(input, ui, reactive, map_mgr, data_mgr)

    @render_widget
    def map():
        return map_mgr.m

    @reactive.effect
    @reactive.event(input.run_analysis)
    def _handle_run_analysis() -> None:
        shapes = data_mgr.drawn_shapes.get()
        if not shapes:
            ui.notification_show(
                "Please draw a rectangle on the map first.", type="warning"
            )
            return

        bbox = BoundingBox(shapes)

        selected_vars = input.covariate_vars()
        if not selected_vars or len(selected_vars) <= 1:
            ui.notification_show(
                "Please select at least one additional variable to landcover.",
                type="warning",
            )
            return

        with progress_mgr.create(min=0, max=100, message="Starting extraction...") as p:
            p.set(value=0)
            stop_event = progress_mgr.start_auto_increment(p, interval=1.0)
            try:
                df = analysis_mgr.run_extraction(
                    bbox=bbox,
                    variables=selected_vars,
                    date_range=input.covariate_dates(),
                    sample_size=input.sample_size(),
                    save_stack=input.export_rasters(),
                    save_csv=input.export_csv(),
                    progress=p,
                )
            finally:
                stop_event.set()

        data_mgr.set_extracted(df)
        ui.notification_show("Data extraction complete!", type="message", duration=3)
        map_mgr.fit_bounds([[bbox.ymin, bbox.xmin], [bbox.ymax, bbox.xmax]])

    @reactive.effect
    @reactive.event(input.run_qda)
    def _handle_run_qda() -> None:
        if data_mgr.EXTRACTED_DF is None:
            ui.notification_show(
                "Please run the data extraction first, or load a csv", type="warning"
            )
            return

        analysis_mgr.run_qda_and_update(
            data_mgr, map_mgr, input.qda_nx(), input.qda_nn()
        )

    @reactive.effect
    @reactive.event(input.run_asd)
    def _handle_run_asd() -> None:
        ui.notification_show("Running Adaptive Sampling...", type="message")
        target = input.asd_target._value
        analysis_mgr.run_asd_and_update(map_mgr, data_mgr, target)

    @reactive.effect
    @reactive.event(input.data_file)
    def _handle_data_file() -> None:
        file_info = input.data_file()
        if not file_info:
            ui.notification_show("Please select a CSV file first.", type="warning")
            return

        try:
            df = file_mgr.parse_uploaded_csv(file_info)
            if df is None:
                ui.notification_show("Please select a CSV file first.", type="warning")
                return

            data_mgr.set_extracted(df)

            north, south, east, west = file_mgr.get_bounds_from_df(df)

            data_mgr.updating_from_map.set(True)
            ui.update_text("bounds_north", value=f"{north:.4f}")
            ui.update_text("bounds_south", value=f"{south:.4f}")
            ui.update_text("bounds_east", value=f"{east:.4f}")
            ui.update_text("bounds_west", value=f"{west:.4f}")
            data_mgr.updating_from_map.set(False)

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
                "bounds": {"north": north, "south": south, "east": east, "west": west},
            }
            data_mgr.drawn_shapes.set([rectangle_data])

            map_mgr.fit_bounds([[south, west], [north, east]])

            ui.notification_show(
                f"Successfully loaded {len(df)} rows from {file_info[0]['name']}",
                type="message",
                duration=3,
            )
        except Exception as e:
            ui.notification_show(f"Error reading CSV file: {str(e)}", type="error")
            data_mgr.set_extracted(None)

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
    def _update_map_layers() -> None:
        # Import ipyleaflet types here to ensure imports occur inside the
        # active Shiny session (after map_mgr.create_map()).
        import ipyleaflet as L
        from ipyleaflet import DrawControl, WidgetControl

        base_layers = [
            lyr
            for lyr in map_mgr.m.layers
            if isinstance(lyr, (L.TileLayer, L.LayersControl, DrawControl))
        ]

        to_render = []
        legend_needed = ""
        for layer in data_mgr.my_ossa_layers.get():
            to_render.append(layer)
            if isinstance(layer, L.LayerGroup):
                legend_needed = layer.name

        map_mgr.m.layers = tuple(base_layers + to_render)

        if legend_needed != "":
            legend_control = WidgetControl(
                widget=point_layer_legend(legend_needed), position="bottomright"
            )
            map_mgr.m.add_control(legend_control)

    @render.text
    @reactive.event(data_mgr.drawn_shapes, input.sample_size)
    def sample_resolution() -> str:
        shapes = data_mgr.drawn_shapes.get()
        sample_size = input.sample_size()
        if not shapes or not sample_size:
            return "--"
        try:
            bbox = BoundingBox(shapes)
            bbox.sampling_grid(n=sample_size)
            return f"{bbox.resolution_m}m"
        except Exception:
            return "--"

    # Ensure landcover is always selected
    @reactive.effect
    @reactive.event(input.covariate_vars)
    def _keep_landcover_selected() -> None:
        current_vars = input.covariate_vars()
        if current_vars is None or "landcover" not in current_vars:
            # Re-add landcover if it was unchecked
            new_vars = list((current_vars or [])) + ["landcover"]
            ui.update_checkbox_group("covariate_vars", selected=new_vars)
