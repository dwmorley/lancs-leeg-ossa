"""Shiny UI/server module for loading CSV data into the app."""

import pandas as pd
from shiny import module, reactive, render, ui


@module.ui
def load_ui():
    """Create the UI portion of the load-data module."""
    return ui.div(
        ui.tags.div(
            [
                ui.output_ui("file_input_training_container"),
                ui.output_ui("file_input_prediction_container"),
            ],
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

    def check_for_nan_values(df):
        """Check for NaN-like values (both actual NaN and string patterns) in the dataframe.

        Parameters
        ----------
        df : pd.DataFrame
            The dataframe to check.

        Returns
        -------
        tuple
            (has_nan_values, error_message) where has_nan_values is a bool
            and error_message is a string describing found NaN-like values.
        """
        nan_patterns = {
            "NA",
            "N/A",
            "N/a",
            "na",
            "n/a",
            "NaN",
            "NAN",
            "nan",
            "null",
            "NULL",
            "Null",
            "none",
            "None",
            "NONE",
            "#N/A",
        }

        nan_locations = []
        for col in df.columns:
            for idx, val in enumerate(df[col]):
                # Check for actual NaN/NaT values
                if pd.isna(val):
                    nan_locations.append({"row": idx, "column": col, "value": "NaN"})
                    continue

                # Check string representation of values for NaN-like patterns
                str_val = str(val).strip()
                if str_val in nan_patterns:
                    nan_locations.append({"row": idx, "column": col, "value": str_val})

        if nan_locations:
            # Format error message with details
            error_lines = ["Found NaN-like values in the data:"]
            for i, loc in enumerate(nan_locations[:10]):  # Show first 10 occurrences
                error_lines.append(
                    f"  Row {loc['row']}, Column '{loc['column']}': '{loc['value']}'"
                )
            if len(nan_locations) > 10:
                error_lines.append(f"  ... and {len(nan_locations) - 10} more occurrences")

            return True, "\n".join(error_lines)

        return False, ""

    def normalize_lat_lon_columns(df):
        # Candidates for latitude and longitude (case-insensitive)
        lat_candidates = {"y", "lat", "ltd", "latitude"}
        lon_candidates = {"x", "long", "lng", "longitude"}
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in lat_candidates:
                col_map[col] = "latitude"
            elif col_lower in lon_candidates:
                col_map[col] = "longitude"
        return df.rename(columns=col_map)

    @render.ui
    def file_input_training_container():
        _reset_counter()
        return ui.input_file(
            "data_training_file",
            ui.h4("Import Training Data"),
            accept=[".csv"],
            multiple=False,
            width="100%",
            placeholder="Upload a previously saved CSV file",
        )

    @render.ui
    def file_input_prediction_container():
        _reset_counter()
        return ui.input_file(
            "data_prediction_file",
            ui.h4("Import Prediction Data"),
            accept=[".csv"],
            multiple=False,
            width="100%",
            placeholder="Upload a previously saved CSV file",
        )

    @reactive.effect
    @reactive.event(input.data_training_file)
    def _handle_data_training_file() -> None:

        updating_from_map = reactive_values["updating_from_map"]
        drawn_shapes = reactive_values["drawn_shapes"]

        file_info = input.data_training_file()
        if not file_info:
            return

        def _fail(msg: str) -> None:
            ui.notification_show(msg, type="error")
            reactive_values["extracted_df"].set(None)
            _reset_counter.set(_reset_counter() + 1)

        try:
            # Read the uploaded CSV file
            extracted_df = pd.read_csv(file_info[0]["datapath"])

            # Check for NaN-like values
            has_nan, nan_error = check_for_nan_values(extracted_df)
            if has_nan:
                _fail(f"Cannot load data: {nan_error}")
                return

            extracted_df = normalize_lat_lon_columns(extracted_df)

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

    @reactive.effect
    @reactive.event(input.data_prediction_file)
    def _handle_data_prediction_file() -> None:
        file_info = input.data_prediction_file()
        if not file_info:
            return

        def _fail(msg: str) -> None:
            ui.notification_show(msg, type="error")
            reactive_values["prediction_df"].set(None)
            _reset_counter.set(_reset_counter() + 1)

        try:
            # Read the uploaded CSV file
            prediction_df = pd.read_csv(file_info[0]["datapath"])

            # Check for NaN-like values
            has_nan, nan_error = check_for_nan_values(prediction_df)
            if has_nan:
                _fail(f"Cannot load data: {nan_error}")
                return

            prediction_df = normalize_lat_lon_columns(prediction_df)

            reactive_values["prediction_df"].set(prediction_df)

            ui.notification_show(
                f"Successfully loaded {len(prediction_df)} rows from {file_info[0]['name']}",
                type="message",
                duration=3,
            )
        except Exception as e:
            _fail(f"Error reading CSV file: {str(e)}")
