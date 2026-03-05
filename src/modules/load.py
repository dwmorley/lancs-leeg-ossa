"""Shiny UI/server module for loading CSV data into the app.

This module exposes a small Shiny module used by the application to allow
users to upload a CSV file. The server side reads the uploaded file,
extracts bounding coordinates (latitude/longitude), updates reactive
values used by the map and stores the parsed DataFrame in
`reactive_values['extracted_df']`.
"""

import pandas as pd
from shiny import module, reactive, ui


@module.ui
def load_ui():
    """Create the UI portion of the load-data module.

    Returns
    -------
    shiny.ui.Tag
        A UI fragment containing a file input control and a header used in
        the main application layout.
    """
    return ui.div(
        ui.tags.div(
            ui.input_file(
                "data_file",
                ui.h4("Import Data"),
                accept=[".csv"],
                multiple=False,
                width="100%",
                placeholder="Upload a previously saved CSV file",
            ),
            class_="input-section",
        ),
        class_="tab-content",
    )


@module.server
def load_server(input, output, session, reactive_values):
    """Server-side logic for the load-data module.

    This function registers a reactive effect that listens for changes to
    `input.data_file`. When a CSV file is uploaded it reads the file into a
    pandas DataFrame, extracts bounding box coordinates from `latitude` and
    `longitude` columns, updates UI text fields and stores the DataFrame in
    `reactive_values['extracted_df']`. It also generates a GeoJSON
    rectangle and sets `reactive_values['drawn_shapes']` so the map can
    render the bounding box.

    Parameters
    ----------
    input : shiny.Input
        The Shiny input object (provides access to `input.data_file`).
    output : shiny.Output
        The Shiny output object (unused by this module but required by the
        module server signature).
    session : shiny.Session
        The current session (used implicitly by UI update helpers).
    reactive_values : dict-like
        Shared reactive state used across modules (expects keys like
        'updating_from_map', 'drawn_shapes', 'extracted_df' and 'map_ref').
    """

    @reactive.effect
    @reactive.event(input.data_file)
    def _handle_data_file() -> None:

        updating_from_map = reactive_values["updating_from_map"]
        drawn_shapes = reactive_values["drawn_shapes"]
        extracted_df = reactive_values["extracted_df"]

        file_info = input.data_file()
        if not file_info:
            ui.notification_show("Please select a CSV file first.", type="warning")
            return

        try:
            # Read the uploaded CSV file
            extracted_df = pd.read_csv(file_info[0]["datapath"])

            # Get bounds from latitude and longitude columns
            north = extracted_df["latitude"].max()
            south = extracted_df["latitude"].min()
            east = extracted_df["longitude"].max()
            west = extracted_df["longitude"].min()

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

            # Update stored shapes
            rectangle_data = {
                "type": "rectangle",
                "geometry": geo_json["geometry"],
                "bounds": {"north": north, "south": south, "east": east, "west": west},
            }
            drawn_shapes.set([rectangle_data])

            try:
                map_ref = reactive_values.get("map_ref")
                if map_ref is not None:
                    m = map_ref.get("m")
                    if m is not None:
                        m.fit_bounds([[south, west], [north, east]])
            except Exception:
                pass

            reactive_values["extracted_df"] = extracted_df

            ui.notification_show(
                f"Successfully loaded {len(extracted_df)} rows from {file_info[0]['name']}",
                type="message",
                duration=3,
            )
        except Exception as e:
            ui.notification_show(f"Error reading CSV file: {str(e)}", type="error")
            reactive_values["extracted_df"] = None
