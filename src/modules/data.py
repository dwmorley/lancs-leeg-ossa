"""Data UI/server module for extracting and previewing covariates."""

from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from faicons import icon_svg
from shiny import module, reactive, render, ui

from src.constants import (
    COVARIATE_OPTIONS,
    END_DATE,
    GRID_SAMPLE_SIZE,
    RESPONSE_OPTIONS,
    START_DATE,
)
from src.covariates.runner_extract import run_extraction
from src.utils.bounding_box import BoundingBox
from src.utils.downloads import save_csv


@module.ui
def data_ui():
    """Return the UI components for the data extraction panel."""
    return ui.tags.div(
        ui.tags.br(),
        [
            ui.tags.div(
                [
                    # Left column
                    ui.tags.div(
                        ui.span("Land Cover variable"),
                        ui.tags.div(
                            ui.input_checkbox_group(
                                "response_vars",
                                "",
                                choices=RESPONSE_OPTIONS,
                                selected=["io_landcoverio"],
                            ),
                            class_="checkbox-wrapper",
                            style="flex: 0.5;",
                        ),
                        ui.span("Covariate variables"),
                        ui.tags.div(
                            ui.input_checkbox_group(
                                "covariate_vars",
                                "",
                                choices=COVARIATE_OPTIONS,
                            ),
                            class_="checkbox-wrapper",
                            style="flex: 3.5;",
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
                                start=datetime.strptime(START_DATE, "%Y-%m-%d").date(),
                                end=datetime.strptime(END_DATE, "%Y-%m-%d").date(),
                            ),
                            ui.div(
                                {"style": "display: flex; gap: 10px; align-items: flex-end;"},
                                ui.input_numeric(
                                    "sample_size",
                                    ui.span("Sample size"),
                                    value=GRID_SAMPLE_SIZE,
                                    step=10,
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
                    ui.tooltip(
                        ui.input_action_button(
                            "export_csv",
                            ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                            class_="action-button",
                        ),
                        "Export extracted data as CSV",
                        options={"delay": {"show": 1000, "hide": 0}},
                    ),
                    ui.tooltip(
                        ui.input_action_button(
                            "run_extraction",
                            ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                            class_="action-button",
                        ),
                        "Run data extraction",
                        options={"delay": {"show": 1000, "hide": 0}},
                    ),
                ],
                class_="button-container",
            ),
        ],
        class_="tab-content",
    )


@module.server
def data_server(input, output, session, reactive_values):
    """Server logic for data extraction UI, handling user inputs and running extraction."""
    drawn_shapes = reactive_values["drawn_shapes"]
    _prev_response_var = reactive.Value("io_landcoverio")

    # Enforce single-select behaviour on response_vars
    @reactive.effect
    @reactive.event(input.response_vars)
    def _keep_response_single() -> None:
        current = list(input.response_vars() or [])
        prev = _prev_response_var.get()
        if len(current) == 0:
            # Nothing selected — restore previous
            ui.update_checkbox_group("response_vars", selected=[prev])
        elif len(current) > 1:
            # More than one selected — keep only the newly added item
            new = next((v for v in current if v != prev), current[-1])
            _prev_response_var.set(new)
            ui.update_checkbox_group("response_vars", selected=[new])
        else:
            _prev_response_var.set(current[0])

    @reactive.effect
    @reactive.event(input.sample_size)
    def _clamp_sample_size() -> None:
        val = input.sample_size()
        if val is not None and val < 1:
            ui.update_numeric("sample_size", value=1)

    @render.text
    @reactive.event(drawn_shapes, input.sample_size)
    def sample_resolution() -> str:
        """Return the sampling resolution as a short string."""
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

        api_keys = {}
        drawn_shapes = reactive_values["drawn_shapes"]
        api_keys["ecmwf_api_key"] = reactive_values["ecmwf_api_key"].get()

        # Get selected variables and parameters
        selected_vars = list(input.covariate_vars())
        if len(selected_vars) < 2:
            ui.notification_show(
                "Please select at least two additional variables to landcover.",
                type="warning",
            )
            return
        selected_vars.append(input.response_vars()[0])

        # Get current bounds
        bounds = drawn_shapes.get()
        if not bounds:
            ui.notification_show("Please define a rectangle on the map first.", type="warning")
            return

        # Check API keys for selected variables
        if "ecmwf_" in "".join(selected_vars) and not api_keys.get("ecmwf_api_key"):
            ui.notification_show(
                "ECMWF data selected but no API key found. Please enter your ECMWF API key in the footer.",
                type="error",
            )
            return

        # Validate inputs before running extraction
        b_checked = extract_pre_checks(selected_vars, input.covariate_dates())
        if not b_checked:
            return

        if any(var in ("wp_1km_unadj", "wp_1km") for var in selected_vars):
            end_date = input.covariate_dates()[1]
            input.covariate_dates()
            if end_date.year > 2020:
                ui.notification_show(
                    f"Specified year ({end_date.year}) is outside the available range for WorldPop data (2000-2020). Taking 2020 data for the end year.",
                    type="warning",
                    duration=None,
                )

        extents = bounds[0]["bounds"]
        north = extents["north"]
        south = extents["south"]
        east = extents["east"]
        west = extents["west"]

        width_deg = abs(east - west)
        height_deg = abs(north - south)
        if width_deg * height_deg > 700:
            ui.notification_show(
                ui.HTML(
                    "The selected area is quite large. Extraction may take a long time or fail due to memory limits.<br><br>It might work but take ages - However, consider reducing the area"
                ),
                type="warning",
                duration=None,
            )

        bbox = BoundingBox([min(west, east), min(south, north), max(west, east), max(south, north)])

        _date_range = input.covariate_dates()
        _sample_size = input.sample_size()

        extracted_df, timeseries_df = run_extraction(
            bbox=bbox,
            variables=selected_vars,
            date_range=_date_range,
            sample_size=_sample_size,
            api_keys=api_keys,
        )

        reactive_values["extracted_df"].set(extracted_df)
        reactive_values["timeseries_df"].set(timeseries_df)

        try:
            map_ref = reactive_values.get("map_ref")
            if map_ref is not None:
                m = map_ref.get("m")
                if m is not None:
                    m.fit_bounds([[south, west], [north, east]])
        except Exception:
            pass

    @reactive.effect
    @reactive.event(input.export_csv)
    def _handle_export_csv() -> None:
        df = reactive_values["extracted_df"]()
        df_timeseries = reactive_values.get("timeseries_df", reactive.Value(None))()

        if df is None:
            ui.notification_show("No data to export. Run the extraction first.", type="warning")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save aggregated CSV
        csv_name = f"ossa_extracted_{timestamp}.csv"
        csv_path = save_csv(csv_name=csv_name, dataframe=df)

        # Save timeseries CSV if available
        if df_timeseries is not None:
            csv_name_ts = f"ossa_extracted_timeseries_{timestamp}.csv"
            csv_path_ts = save_csv(csv_name=csv_name_ts, dataframe=df_timeseries)
            ui.notification_show(
                f"Data saved:\n  Aggregated: {csv_path}\n  Timeseries: {csv_path_ts}",
                type="message",
            )
        else:
            ui.notification_show(f"Data saved to {csv_path}", type="message")


def get_boundingbox(bounds: List[Dict[str, Any]]) -> BoundingBox:
    """Convert a Shiny drawn shapes event into a BoundingBox.

    Parameters
    ----------
    bounds : List[str]
        Shiny drawn shapes payload (list containing a dict with 'bounds').

    Returns
    -------
    BoundingBox
        BoundingBox instance constructed from the drawn shape.
    """
    extents = bounds[0]["bounds"]
    north = extents["north"]
    south = extents["south"]
    east = extents["east"]
    west = extents["west"]
    return BoundingBox([min(west, east), min(south, north), max(west, east), max(south, north)])


def extract_pre_checks(selected_vars: List[str], date_range: Tuple[date, date]) -> bool:
    """Perform pre-checks before running extraction, such as validating inputs or checking data availability.

    Returns
    -------
    bool
        True if checks pass and extraction can proceed, False otherwise.
    """
    start_date = date_range[0]
    end_date = date_range[1]

    warnings = []

    if "io_landcoverio" in selected_vars:
        if end_date.year < 2017 or end_date.year > 2023:
            warnings.append(
                "Selected date range is outside the available for landcover data (2017-2023)."
            )

    if "modis_Gpp_500m" in selected_vars:
        modis_start = datetime.strptime("2000-02-18", "%Y-%m-%d").date()
        modis_end = datetime.strptime("2023-02-17", "%Y-%m-%d").date()
        if start_date < modis_start or end_date > modis_end:
            warnings.append(
                "Selected date range is outside the available range for MODIS GPP data (2000-02-18 to 2023-02-17)."
            )

    if any("modis_" in var for var in selected_vars):
        if start_date.year < 2000:
            warnings.append("Selected start date is outside the available for MODIS data (>=2000).")

    if any("terraclimate_" in var for var in selected_vars):
        if start_date.year < 1950:
            warnings.append(
                "Selected start date is outside the available for Terraclimate data (>=1950)."
            )

    if warnings:
        message = ui.tags.div(
            ui.tags.strong("Could not run extraction due to the following issues:"),
            ui.tags.br(),
            ui.tags.br(),
            *[ui.tags.div(f"• {warning}", ui.tags.br()) for warning in warnings],
        )
        ui.notification_show(message, type="error", duration=None)
        return False

    return True
