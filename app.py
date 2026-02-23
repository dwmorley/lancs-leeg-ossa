from pathlib import Path

from shiny import App, reactive, ui

from src.modules import aoi, asd, footer, header, load, map, qda  # data

page_dependencies = ui.tags.head(
    ui.tags.link(rel="stylesheet", type="text/css", href="styles.css"),
)

page_header = header.header_ui("my_header")
leaflet_map = map.map_ui("my_map")
extent_boxes = aoi.aoi_ui("my_aoi")
qda_ui = qda.qda_ui("my_qda")
asd_ui = asd.asd_ui("my_asd")
page_footer = footer.footer_ui("my_footer")
load_csv = load.load_ui("my_load")


app_ui = ui.page_fillable(
    map.SIZE_JS,
    page_dependencies,
    page_header,
    ui.layout_columns(
        ui.card(
            ui.navset_tab(
                ui.nav_panel(
                    "Extract Data",
                    extent_boxes,
                    ui.tags.hr(),
                ),
                ui.nav_panel(
                    "Load Data",
                    load_csv,
                ),
                ui.nav_panel(
                    "QDA, LCP",
                    qda_ui,
                ),
                ui.nav_panel(
                    "ASD",
                    asd_ui,
                ),
            ),
            class_="left-card",
        ),
        ui.card(
            ui.div(leaflet_map, id="map-container"),
            class_="right-card",
        ),
        col_widths=[6, 6],
    ),
    page_footer,
    title="OSSA - Optimal Spatial Sampling Algorithm",
)


def server(input, output, session):

    reactive_values = {
        "extracted_df": None,
        "my_ossa_layers": reactive.Value([]),
        "drawn_shapes": reactive.Value([]),
        "updating_from_map": reactive.Value(False),
    }

    map.map_server("my_map", reactive_values)
    aoi.aoi_server("my_aoi", reactive_values)
    load.load_server("my_load", reactive_values)
    qda.qda_server("my_qda", reactive_values)
    asd.asd_server("my_asd", reactive_values)
    footer.footer_server("my_footer")


www_dir = Path(__file__).parent / "www"
app = App(app_ui, server, static_assets=www_dir)
