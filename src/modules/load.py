"""Shiny UI/server module for loading CSV data into the app."""

import pandas as pd
from shiny import module, reactive, render, ui


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
            ui.output_ui("file_input_container"),
            class_="input-section",
        ),
        class_="tab-content",
    )


@module.server
def load_server(input, output, session, reactive_values):
    """Server-side logic for the load-data module.

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
    _reset_counter = reactive.Value(0)

    @render.ui
    def file_input_container():
        _reset_counter()  # take dependency so re-render is triggered on reset
        return ui.input_file(
            "data_file",
            ui.h4("Import Data"),
            accept=[".csv"],
            multiple=False,
            width="100%",
            placeholder="Upload a previously saved CSV file",
        )

    @reactive.effect
    @reactive.event(input.data_file)
    def _handle_data_file() -> None:

        updating_from_map = reactive_values["updating_from_map"]
        drawn_shapes = reactive_values["drawn_shapes"]

        file_info = input.data_file()
        if not file_info:
            return

        def _fail(msg: str) -> None:
            ui.notification_show(msg, type="error")
            reactive_values["extracted_df"].set(None)
            _reset_counter.set(_reset_counter() + 1)

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

            reactive_values["extracted_df"].set(extracted_df)

            ui.notification_show(
                f"Successfully loaded {len(extracted_df)} rows from {file_info[0]['name']}",
                type="message",
                duration=3,
            )
        except Exception as e:
            _fail(f"Error reading CSV file: {str(e)}")
