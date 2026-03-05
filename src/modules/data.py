"""Data UI/server module for extracting and previewing covariates."""

from datetime import datetime
from typing import List

from faicons import icon_svg
from shiny import module, reactive, render, ui

from runner_extract import run_extraction
from src.constants import COVARIATE_OPTIONS, END_DATE, GRID_SAMPLE_SIZE, START_DATE
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
                                start=datetime.strptime(START_DATE, "%Y-%m-%d").date(),
                                end=datetime.strptime(END_DATE, "%Y-%m-%d").date(),
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
    """Server logic for data extraction UI, handling user inputs and running extraction."""
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

        extracted_df = reactive_values.get("extracted_df")
        drawn_shapes = reactive_values["drawn_shapes"]

        # Get selected variables and parameters
        selected_vars = input.covariate_vars()
        if len(selected_vars) <= 2:
            ui.notification_show(
                "Please select at least two additional variables to landcover.",
                type="warning",
            )
            return

        # Get current bounds
        bounds = drawn_shapes.get()
        if not bounds:
            ui.notification_show("Please draw a rectangle on the map first.", type="warning")
            return

        # Validate inputs before running extraction
        b_checked = extract_pre_checks(selected_vars, input.covariate_dates())
        if not b_checked:
            return

        extents = bounds[0]["bounds"]
        north = extents["north"]
        south = extents["south"]
        east = extents["east"]
        west = extents["west"]

        bbox = BoundingBox([min(west, east), min(south, north), max(west, east), max(south, north)])

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

    @reactive.effect
    @reactive.event(input.export_csv)
    def _handle_export_csv() -> None:
        df = reactive_values.get("extracted_df")
        if df is None:
            ui.notification_show("No data to export.", type="warning")
            return
        csv_name = f"ossa_extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = save_csv(csv_name=csv_name, dataframe=df)
        ui.notification_show(f"Data saved to {csv_path}", type="message")


def get_boundingbox(bounds: List[str]) -> BoundingBox:
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


def extract_pre_checks(selected_vars: List[str], date_range: tuple) -> bool:
    """Perform pre-checks before running extraction, such as validating inputs or checking data availability.

    Returns
    -------
    bool
        True if checks pass and extraction can proceed, False otherwise.
    """
    start_date = date_range[0]
    end_date = date_range[1]

    warnings = []

    if "landcover" in selected_vars:
        if end_date.year < 2017 or end_date.year > 2023:
            warnings.append(
                "Selected date range is outside the available for landcover data (2017-2023)."
            )

    if any("modis_" in var for var in selected_vars):
        if start_date.year < 2000:
            warnings.append("Selected start date is outside the available for MODIS data (>=2000).")

    if any("terraclimate_" in var for var in selected_vars):
        if start_date.year < 1950:
            warnings.append(
                "Selected start date is outside the available for Terraclimate data (>=1950)."
            )

    if any("wp_1km_unadj" in var for var in selected_vars):
        if start_date.year < 2000 or end_date.year > 2020:
            warnings.append(
                "Selected date range is outside the available for World Pop data (2000-2020)."
            )

    if warnings:
        message = ui.tags.div(
            ui.tags.strong("Could not run extraction due to the following issues:"),
            ui.tags.br(),
            ui.tags.br(),
            *[ui.tags.div(f"• {warning}", ui.tags.br()) for warning in warnings],
        )
        ui.notification_show(message, type="error")
        return False

    return True
