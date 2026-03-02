import platform
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from faicons import icon_svg
from shiny import module, reactive, render, ui

from constants import COVARIATE_OPTIONS, GRID_SAMPLE_SIZE
from runner_extract import run_extraction
from src.gis.bounding_box import BoundingBox


@module.ui
def data_ui():
    return ui.tags.div(
        ui.tags.br(),
        [
            ui.tags.div(
                [
                    # Left column
                    ui.tags.div(
                        ui.tags.div(
                            ui.input_checkbox_group(
                                "covariate_vars",
                                "",
                                choices=COVARIATE_OPTIONS,
                                selected=["landcover"],
                            ),
                            class_="checkbox-wrapper",
                        ),
                        class_="column-content",
                    ),
                    # Right column
                    ui.tags.div(
                        [
                            ui.span("Date range"),
                            ui.input_date_range(
                                "covariate_dates",
                                "",
                                start=(datetime.now() - timedelta(days=183)).date(),
                                end=datetime.now().date(),
                            ),
                            ui.div(
                                {"style": "display: flex; gap: 10px; align-items: flex-end;"},
                                ui.input_numeric(
                                    "sample_size",
                                    ui.span("Sample size"),
                                    value=GRID_SAMPLE_SIZE,
                                    min=1,
                                    step=1,
                                    width="120px",
                                ),
                                ui.div(
                                    {
                                        "style": "display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-width: 90px;"
                                    },
                                    ui.span(
                                        "Grid resolution",
                                        class_="ui-span-grid-resolution",
                                    ),
                                    ui.output_text_verbatim(
                                        "sample_resolution",
                                    ),
                                ),
                            ),
                        ],
                        class_="column-content text-inputs-column",
                    ),
                ],
                class_="content-columns",
            ),
            ui.tags.div(
                [
                    ui.input_action_button(
                        "export_csv",
                        ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                    ui.input_action_button(
                        "run_extraction",
                        ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                        class_="action-button",
                    ),
                ],
                class_="button-container",
            ),
        ],
        class_="tab-content",
    )


@module.server
def data_server(input, output, session, reactive_values):

    drawn_shapes = reactive_values["drawn_shapes"]

    # Ensure landcover is always selected
    @reactive.effect
    @reactive.event(input.covariate_vars)
    def _keep_landcover_selected() -> None:
        current_vars = input.covariate_vars()
        if current_vars is None or "landcover" not in current_vars:
            # Re-add landcover if it was unchecked
            new_vars = list((current_vars or [])) + ["landcover"]
            ui.update_checkbox_group("covariate_vars", selected=new_vars)

    @render.text
    @reactive.event(drawn_shapes, input.sample_size)
    def sample_resolution() -> str:
        """
        This output is bound to `ui.output_text_verbatim('sample_resolution')`
        """
        sample_size = input.sample_size()
        shapes = drawn_shapes.get()
        if not shapes or not sample_size:
            return "--"
        try:
            extents = shapes[0]["bounds"]
            north = extents["north"]
            south = extents["south"]
            east = extents["east"]
            west = extents["west"]
            bbox = BoundingBox(
                [min(west, east), min(south, north), max(west, east), max(south, north)]
            )
            bbox.sampling_grid(n=sample_size)
            return f"{bbox.resolution_m}m"
        except Exception:
            return "--"

    @reactive.effect
    @reactive.event(input.run_extraction)
    def _handle_run_extraction() -> None:

        extracted_df = reactive_values.get("extracted_df")
        drawn_shapes = reactive_values["drawn_shapes"]

        # Get current bounds
        bounds = drawn_shapes.get()
        if not bounds:
            ui.notification_show("Please draw a rectangle on the map first.", type="warning")
            return

        extents = bounds[0]["bounds"]
        north = extents["north"]
        south = extents["south"]
        east = extents["east"]
        west = extents["west"]

        bbox = BoundingBox([min(west, east), min(south, north), max(west, east), max(south, north)])

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

            extracted_df = run_extraction(
                bbox=bbox,
                variables=selected_vars,
                date_range=input.covariate_dates(),
                sample_size=input.sample_size(),
                progress=p,
            )

        reactive_values["extracted_df"] = extracted_df

        try:
            map_ref = reactive_values.get("map_ref")
            if map_ref is not None:
                m = map_ref.get("m")
                if m is not None:
                    m.fit_bounds([[south, west], [north, east]])
        except Exception:
            pass

        ui.notification_show(
            "Data extraction complete!",
            type="message",
            duration=3,
        )

    def _export_with_notification(data, filename, export_func, empty_message):
        if data is None:
            ui.notification_show(
                empty_message,
                type="warning",
            )
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = get_downloads_folder() / filename.format(ts=ts)
        export_func(data, fn)
        ui.notification_show(
            "Data exported to your downloads folder",
            type="message",
            duration=5,
        )

    @reactive.effect
    @reactive.event(input.export_csv)
    def _handle_export_csv() -> None:
        _export_with_notification(
            reactive_values.get("extracted_df"),
            "ossa_extracted_{ts}.csv",
            lambda df, fn: df.to_csv(fn, index=False),
            "No data to export.",
        )


def get_downloads_folder():
    """Get the Downloads folder path for the current platform."""
    if platform.system() == "Windows":
        import winreg

        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return Path(location)
    else:
        # macOS and Linux
        return Path.home() / "Downloads"


def get_boundingbox(bounds: List[str]) -> BoundingBox:
    extents = bounds[0]["bounds"]
    north = extents["north"]
    south = extents["south"]
    east = extents["east"]
    west = extents["west"]
    return BoundingBox([min(west, east), min(south, north), max(west, east), max(south, north)])
