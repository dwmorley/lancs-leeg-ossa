import pandas as pd
from shiny import module, reactive, ui


@module.ui
def load_ui():
    return ui.div(
        ui.input_file(
            "data_file",
            "Choose .csv file",
            accept=[".csv"],
            multiple=False,
            width="100%",
        ),
        class_="input-section",
    )


@module.server
def load_server(input, output, session, reactive_values):

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

            # Zoom map to fit the bounds by calling the exposed map reference
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
