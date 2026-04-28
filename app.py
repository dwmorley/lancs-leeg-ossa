"""Application entry point for the OSSA sampling UI and data pipeline."""

import os
from pathlib import Path

from shiny import App, reactive, run_app, ui

from src.modules import aoi, asd, data, footer, header, load, map, qda, sdmtmb, zssa

page_dependencies = ui.tags.head(
    ui.tags.link(rel="stylesheet", type="text/css", href="styles.css"),
    ui.tags.link(
        rel="stylesheet",
        href="https://cdn.jsdelivr.net/gh/devicons/devicon@v2.15.1/devicon.min.css",
    ),
)

page_header = header.header_ui("my_header")
data_ui = data.data_ui("my_data")
leaflet_map = map.map_ui("my_map")
extent_boxes = aoi.aoi_ui("my_aoi")
qda_ui = qda.qda_ui("my_qda")
asd_ui = asd.asd_ui("my_asd")
zssa_ui = zssa.zssa_ui("my_zssa")
sdmtmb_ui = sdmtmb.sdmtmb_ui("my_sdmtmb")
page_footer = footer.footer_ui("my_footer")
load_csv = load.load_ui("my_load")

app_ui = ui.page_fluid(
    ui.tags.div(
        page_dependencies,
        page_header,
        # Main Content
        ui.tags.div(
            # Left Card
            ui.tags.div(
                ui.tags.div(
                    ui.tags.div("Settings Panel", class_="nav-header"),
                    ui.navset_tab(
                        ui.nav_panel(
                            "Extract Data",
                            extent_boxes,
                            data_ui,
                        ),
                        ui.nav_panel(
                            "Load Data",
                            load_csv,
                        ),
                        ui.nav_panel(
                            "Stratification",
                            qda_ui,
                        ),
                        ui.nav_panel(
                            "ST Model",
                            sdmtmb_ui,
                        ),
                        ui.nav_panel(
                            "Adaptive-Single",
                            asd_ui,
                        ),
                        ui.nav_panel(
                            "Adaptive-Multi",
                            zssa_ui,
                        ),
                        id="nav_tabs",
                    ),
                    class_="nav-container",
                ),
                class_="card left-card",
            ),
            # Right Card
            ui.tags.div(
                ui.tags.div(leaflet_map, class_="right-card-content"),
                class_="card right-card",
            ),
            class_="main-content",
        ),
        # Footer
        page_footer,
        class_="page-wrapper",
    )
)


def server(input, output, session):
    """Shiny Server."""
    reactive_values = {
        "extracted_df": reactive.Value(None),
        "prediction_df": reactive.Value(None),
        "my_ossa_layers": reactive.Value([]),
        "drawn_shapes": reactive.Value([]),
        "updating_from_map": reactive.Value(False),
        "qda_results": reactive.Value([]),
        "lcp_results": reactive.Value([]),
        "sc-asd_results": reactive.Value([]),
        "mc-asd_results": reactive.Value([]),
        "sdmtmb_results": reactive.Value([]),
        "ecmwf_api_key": reactive.Value(""),
    }

    map.map_server("my_map", reactive_values)
    data.data_server("my_data", reactive_values)
    aoi.aoi_server("my_aoi", reactive_values)
    load.load_server("my_load", reactive_values)
    qda.qda_server("my_qda", reactive_values)
    asd.asd_server("my_asd", reactive_values)
    zssa.zssa_server("my_zssa", reactive_values)
    sdmtmb.sdmtmb_server("my_sdmtmb", reactive_values)
    footer.footer_server("my_footer", reactive_values)


www_dir = Path(__file__).parent / "www"
app = App(app_ui, server, static_assets=www_dir)

# DEBUG
if __name__ == "__main__":
    # When running in Docker, bind to 0.0.0.0 and read PORT from env.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    run_app(app, host=host, port=port)
