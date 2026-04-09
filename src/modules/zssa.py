"""UI header components for ZSSA models."""

from datetime import datetime

import geopandas as gpd
import pandas as pd
from faicons import icon_svg
from shiny import module, reactive, render, ui

from src.constants import ZSSA_OPTIONS
from src.plotting.maps import make_point_layer
from src.sampling.zssa_routine import zssa_via_rpy2
from src.utils.downloads import save_artifacts_zip


@module.ui
def zssa_ui():
    """Return UI components for the ZSSA panel."""
    return ui.div(
        ui.tags.div(
            [
                # Left column
                ui.tags.div(
                    [
                        ui.h4("ZSSA Analysis", class_="column-header"),
                        ui.input_numeric(
                            "zssa_iter",
                            "Iterations",
                            value=ZSSA_OPTIONS["iterations"],
                            min=10,
                            step=100,
                        ),
                        ui.input_numeric(
                            "zssa_init",
                            "Number of locations for validation",
                            value=ZSSA_OPTIONS["init"],
                            min=1,
                            step=10,
                        ),
                        ui.input_checkbox(
                            "kriging_checkbox",
                            "Enable Kriging",
                            value=ZSSA_OPTIONS["from_glm"],
                        ),
                        ui.output_ui("number_list_ui"),
                        ui.input_numeric(
                            "new_number",
                            "Add to list",
                            value=100,
                            step=10,
                            min=0,
                        ),
                        ui.tags.div(
                            [
                                ui.input_action_button(
                                    "add_number",
                                    ui.tags.span(
                                        [
                                            icon_svg("plus"),
                                            ui.tags.span(
                                                "Add",
                                                style="margin-left: 5px; margin-right: 5px; display: inline-block;",
                                            ),
                                        ],
                                        style="display: flex; align-items: center;",
                                    ),
                                ),
                                ui.input_action_button(
                                    "delete_number",
                                    ui.tags.span(
                                        [
                                            icon_svg("trash-can"),
                                            ui.tags.span(
                                                "Delete",
                                                style="margin-left: 5px; margin-right: 5px; display: inline-block;",
                                            ),
                                        ],
                                        style="display: flex; align-items: center;",
                                    ),
                                ),
                            ],
                            style="display: flex; gap: 10px; align-items: center;",
                        ),
                    ],
                    ui.tags.div(
                        ui.tooltip(
                            ui.input_action_button(
                                "show_zssa_stats",
                                ui.tags.span([icon_svg("table-list")], class_="icon-square-btn"),
                                class_="action-button",
                            ),
                            "Show summary statistics",
                            options={"delay": {"show": 1000, "hide": 0}},
                        ),
                        ui.tooltip(
                            ui.input_action_button(
                                "run_zssa",
                                ui.tags.span([icon_svg("play")], class_="icon-square-btn"),
                                class_="action-button",
                            ),
                            "Run ZSSA analysis",
                            options={"delay": {"show": 1000, "hide": 0}},
                        ),
                        style="margin-top: auto; align-self: flex-end;",
                    ),
                    class_="column-content text-inputs-column",
                ),
                # Right column
                ui.tags.div(
                    [
                        ui.h4("Display locations", class_="column-header"),
                        ui.input_select(
                            "zssa_selected_pnts",
                            "Number of proposed points",
                            choices=[],
                            selected="1",
                        ),
                        ui.tags.div(
                            ui.tooltip(
                                ui.input_action_button(
                                    "save_zssa",
                                    ui.tags.span([icon_svg("download")], class_="icon-square-btn"),
                                    class_="action-button",
                                ),
                                "Export ZSSA results",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            ui.tooltip(
                                ui.input_action_button(
                                    "show_zssa_points",
                                    ui.tags.span(
                                        [icon_svg("location-dot")], class_="icon-square-btn"
                                    ),
                                    class_="action-button",
                                ),
                                "Show ZSSA selection",
                                options={"delay": {"show": 1000, "hide": 0}},
                            ),
                            style="margin-top: auto; align-self: flex-end;",
                        ),
                    ],
                    class_="column-content text-inputs-column",
                ),
            ],
            class_="content-columns",
        ),
        class_="tab-content",
    )


@module.server
def zssa_server(input, output, session, reactive_values):
    """Server logic for the ZSSA panel."""
    number_list = reactive.Value(ZSSA_OPTIONS["add"])

    @reactive.Calc
    def number_list_choices():
        """Reactive value for the listbox choices."""
        return [str(num) for num in sorted(number_list())]

    @reactive.Effect
    @reactive.event(input.add_number)
    def _add_number():
        new_number = input.new_number()
        current_list = number_list()
        if new_number not in current_list:
            updated_list = sorted(current_list + [new_number])
            number_list.set(updated_list)

    @reactive.Effect
    @reactive.event(input.delete_number)
    def _delete_number():
        selected = input.number_list()  # Get selected items from the listbox
        if selected:
            current_list = number_list()
            # Convert selected strings back to integers and remove them
            selected_ints = [int(s) for s in selected]
            updated_list = [num for num in current_list if num not in selected_ints]
            number_list.set(updated_list)

    @output
    @render.ui
    def number_list_ui():
        """Dynamically render the listbox."""
        return ui.input_select(
            "number_list",
            "Number of locations to add",
            choices=number_list_choices(),
            multiple=True,
        )

    @reactive.effect
    @reactive.event(input.run_zssa)
    def _handle_run_zssa() -> None:

        extracted_df = reactive_values["extracted_df"]()

        if not validate_extracted_df(extracted_df):
            return

        ni = input.zssa_iter()
        add = number_list()
        from_glm = input.kriging_checkbox()
        init = input.zssa_init()

        if max(add) >= len(extracted_df):
            ui.notification_show(
                "Cannot add more points than available in the dataset. Please adjust the number of points to add or reduce the dataset size.",
                type="error",
            )
            return

        with ui.Progress(min=0, max=len(add * ni)) as p:
            p.set(message="Starting zssa...", value=0)

            summary, proposed = zssa_via_rpy2(
                data=extracted_df,
                nr_iterations=ni,
                init=init,
                add=add,
                from_glm=from_glm,
                progress=p,
            )

            reactive_values["zssa_results"].set(
                {
                    "summary": summary,
                    "proposed": proposed,
                }
            )

            ui.update_select(
                "zssa_selected_pnts", choices=[str(num) for num in add], selected=str(add[0])
            )

    @reactive.effect
    @reactive.event(input.show_zssa_stats)
    def _handle_show_zssa_stats() -> None:

        if not reactive_values["zssa_results"]():
            ui.notification_show(
                "Please run the ZSSA analysis first.",
                type="error",
            )
            return

        df = reactive_values["zssa_results"]()["summary"]

        header = ui.tags.thead(
            ui.tags.tr(
                ui.tags.th(""),
                *[ui.tags.th(col, style="text-align:right;") for col in df.columns],
            )
        )
        body = ui.tags.tbody(
            *[
                ui.tags.tr(
                    ui.tags.th(row, style="white-space:nowrap;"),
                    *[ui.tags.td(f"{val:.4f}", style="text-align:right;") for val in df.loc[row]],
                )
                for row in df.index
            ]
        )
        table = ui.tags.table(
            header,
            body,
            class_="table table-sm table-bordered",
        )

        ui.modal_show(
            ui.modal(
                ui.tags.h5("ZSSA Statistics", style="margin-bottom:10px;"),
                table,
                title=None,
                easy_close=True,
                footer=ui.modal_button("Close"),
                size="l",
            )
        )

    @reactive.effect
    @reactive.event(input.show_zssa_points)
    def _handle_show_zssa_points() -> None:
        if not reactive_values["zssa_results"]():
            ui.notification_show(
                "Please run the ZSSA analysis first.",
                type="error",
            )
            return

        npoints = input.zssa_selected_pnts()
        proposed = reactive_values["zssa_results"]()["proposed"][int(npoints)]
        proposed = proposed[proposed["proposed"] == 1]

        drawn_shapes = reactive_values["drawn_shapes"]
        my_ossa_layers = reactive_values["my_ossa_layers"]

        drawn_shapes.set([])
        points = make_point_layer(proposed, "ZSSA Sites")
        my_ossa_layers.set([points])

        lat_min = float(proposed.latitude.min())
        lat_max = float(proposed.latitude.max())
        lon_min = float(proposed.longitude.min())
        lon_max = float(proposed.longitude.max())

        map_ref = reactive_values.get("map_ref")
        if map_ref is not None:
            m = map_ref.get("m")
            if m is not None:
                try:
                    m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
                except Exception:
                    pass

    @reactive.effect
    @reactive.event(input.save_zssa)
    def _handle_save_zssa() -> None:
        if not reactive_values["zssa_results"]():
            ui.notification_show(
                "Nothing to export. Please run the ZSSA analysis first.",
                type="error",
            )
            return

        zssa_proposed = reactive_values["zssa_results"]()["proposed"]
        zssa_summary = reactive_values["zssa_results"]()["summary"]
        combined_df = zssa_proposed[next(iter(zssa_proposed))][["latitude", "longitude"]].copy()
        for k, v in zssa_proposed.items():
            combined_df[f"proposed_{k}"] = v["proposed"]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zssa_sites_gpkg = gpd.GeoDataFrame(
            combined_df,
            geometry=gpd.points_from_xy(combined_df.longitude, combined_df.latitude),
            crs="EPSG:4326",
        )

        zip_path = save_artifacts_zip(
            zip_name=f"asd_results_{timestamp}.zip",
            csv_artifacts={"zssa_sites.csv": combined_df, "zssa_stats.csv": zssa_summary},
            gpkg_artifacts={"asd_sites.gpkg": zssa_sites_gpkg},
        )

        ui.notification_show(
            f"Results saved to {zip_path}",
            type="message",
        )

    def validate_extracted_df(extracted_df: pd.DataFrame | None) -> bool:
        cols = [col.lower() for col in extracted_df.columns]
        if "longitude" not in cols or "latitude" not in cols:
            ui.notification_show(
                "Data must contain 'longitude' and 'latitude' columns for ZSSA analysis.",
                type="error",
            )
            return False

        if len(cols) > 5:
            ui.notification_show(
                "Data contains more columns than expected. We need just longitude, latitude, mean, sd and optionally time.",
                type="error",
            )
            return False

        if "sd" not in cols or "mean" not in cols:
            ui.notification_show(
                "Data must contain columns for ZSSA analysis: Mean & SD",
                type="error",
            )
            return False

        if len(cols) == 5:
            ui.notification_show(
                "TIME",
            )
            return True

        return True
