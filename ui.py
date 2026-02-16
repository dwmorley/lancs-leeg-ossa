from faicons import icon_svg
from shiny import ui
from shinywidgets import output_widget

from constants import (
    ASD_OPTIONS,
    COVARIATE_OPTIONS,
    GRID_SAMPLE_SIZE,
    LCP_OPTIONS,
    QDA_OPTIONS,
    URLS,
)

app_ui = ui.page_fluid(
    ui.tags.head(ui.tags.link(rel="stylesheet", type="text/css", href="styles.css")),
    ui.div(
        {"class": "header-bar"},
        ui.div({"class": "app-title"}, "OSSA - Optimal Spatial Sampling Algorithm"),
        ui.div(
            {"class": "logo-container"},
            ui.tags.a(
                ui.img(src="lulogo.png", class_="logo-img", alt="Logo 1"),
                href=URLS["lms"],
                target="_blank",
            ),
        ),
    ),
    # Main content area with two columns
    ui.row(
        # Left column - divided into two cards
        ui.column(
            6,
            {"class": "left-column"},
            # Top card
            ui.div(
                {"class": "top-card"},
                ui.div(
                    {"class": "bounds-row"},
                    ui.div(
                        {"class": "bounds-cell"},
                        ui.input_text(
                            "bounds_north", "North", value="", placeholder="--"
                        ),
                    ),
                    ui.div(
                        {"class": "bounds-cell"},
                        ui.input_text(
                            "bounds_south", "South", value="", placeholder="--"
                        ),
                    ),
                    ui.div(
                        {"class": "bounds-cell"},
                        ui.input_text(
                            "bounds_east", "East", value="", placeholder="--"
                        ),
                    ),
                    ui.div(
                        {"class": "bounds-cell"},
                        ui.input_text(
                            "bounds_west", "West", value="", placeholder="--"
                        ),
                    ),
                ),
            ),
            # Middle card
            ui.div(
                {"class": "middle-card"},
                ui.card(
                    ui.navset_tab(
                        ui.nav_panel(
                            "Extract Data",
                            ui.div(
                                {
                                    "style": "display: flex; gap: 12px; height: 100%; padding: 12px;"
                                },
                                ui.div(
                                    {
                                        "style": "width: 50%; display: flex; flex-direction: column;"
                                    },
                                    ui.p(
                                        "Variables",
                                        {
                                            "style": "margin: 0 0 4px 0; font-size: 14px; font-weight: 500;"
                                        },
                                    ),
                                    ui.div(
                                        {"class": "checkbox-scroll"},
                                        ui.input_checkbox_group(
                                            "covariate_vars",
                                            None,
                                            COVARIATE_OPTIONS,
                                            selected="landcover",
                                        ),
                                    ),
                                ),
                                ui.div(
                                    {
                                        "style": "width: 50%; display: flex; flex-direction: column; justify-content: space-between;"
                                    },
                                    ui.div(
                                        ui.p(
                                            "Date Range",
                                            {
                                                "style": "margin: 0 0 4px 0; font-size: 14px; font-weight: 500;"
                                            },
                                        ),
                                        ui.input_date_range(
                                            "covariate_dates",
                                            "",
                                        ),
                                        ui.input_numeric(
                                            "sample_size",
                                            "Sample size",
                                            value=GRID_SAMPLE_SIZE,
                                            min=1,
                                            step=1,
                                        ),
                                        ui.input_checkbox(
                                            "export_rasters",
                                            "Export covariate rasters",
                                            value=False,
                                        ),
                                    ),
                                    ui.div(
                                        {
                                            "style": "display: flex; justify-content: flex-end;"
                                        },
                                        ui.input_action_button(
                                            "run_analysis",
                                            "Run",
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        ui.nav_panel(
                            "Load Data",
                            ui.div(
                                {"style": "padding: 12px;"},
                                ui.div(
                                    {
                                        "style": "display: flex; gap: 12px; align-items: flex-start;"
                                    },
                                    ui.div(
                                        {"style": "flex: 1;"},
                                        ui.input_file(
                                            "data_file",
                                            "Choose .tif file",
                                            accept=[".tif"],
                                            multiple=False,
                                        ),
                                    ),
                                    ui.div(
                                        {"style": "padding-top: 27px;"},
                                        ui.input_action_button(
                                            "import_data",
                                            "Import",
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            # Bottom card with tabs
            ui.div(
                {"class": "bottom-card"},
                ui.card(
                    ui.navset_tab(
                        ui.nav_panel(
                            "QDA",
                            ui.div(
                                {"style": "padding: 15px;"},
                                ui.h4("Qudradic Discriminant Analysis"),
                                ui.div(
                                    {
                                        "style": "display: flex; gap: 12px; align-items: flex-start;"
                                    },
                                    ui.div(
                                        ui.input_numeric(
                                            "qda_nx",
                                            "Maximum classes allowed (nx)",
                                            value=QDA_OPTIONS["nx"],
                                            min=1,
                                            step=1,
                                        ),
                                        ui.input_numeric(
                                            "qda_nn",
                                            "Local frequency prior distance (nn)",
                                            value=QDA_OPTIONS["nn"],
                                            step=0.1,
                                        ),
                                    ),
                                ),
                                ui.div(
                                    {
                                        "style": "margin-top: auto; display: flex; justify-content: flex-end;"
                                    },
                                    ui.input_action_button("run_qda", "Run"),
                                ),
                            ),
                        ),
                        ui.nav_panel(
                            "LCP",
                            ui.div(
                                {"style": "padding: 15px;"},
                                ui.h4("Lattice Close Pairs"),
                                ui.div(
                                    {
                                        "style": "display: flex; gap: 12px; align-items: flex-start;"
                                    },
                                    ui.div(
                                        ui.input_numeric(
                                            "lcp_delta",
                                            "Inhibition distance (delta)",
                                            value=LCP_OPTIONS["delta"],
                                            step=0.01,
                                        ),
                                        ui.input_numeric(
                                            "lcp_zeta",
                                            "Allocation radius (zeta)",
                                            value=LCP_OPTIONS["zeta"],
                                            step=0.1,
                                        ),
                                        ui.input_numeric(
                                            "lcp_total",
                                            "Number of locations to optimise",
                                            value=LCP_OPTIONS["total"],
                                            min=1,
                                            step=1,
                                        ),
                                        ui.input_numeric(
                                            "lcp_grid",
                                            "Proportion of grid locations (to close pairs)",
                                            value=LCP_OPTIONS["grid"],
                                            step=0.01,
                                        ),
                                    ),
                                ),
                                ui.div(
                                    {
                                        "style": "margin-top: auto; display: flex; justify-content: flex-end;"
                                    },
                                    ui.input_action_button("run_lcp", "Run"),
                                ),
                            ),
                        ),
                        ui.nav_panel(
                            "ASD",
                            ui.div(
                                {"style": "padding: 15px;"},
                                ui.h4("Adaptive Spatial Design"),
                                ui.div(
                                    ui.input_text(
                                        "asd_formulaf",
                                        "Fixed effects formula",
                                        value=ASD_OPTIONS["formulaf"],
                                        placeholder="e.g. AnGam~Week+Elev+Soil",
                                    ),
                                    ui.input_text(
                                        "asd_formular",
                                        "Random effects formula",
                                        value=ASD_OPTIONS["formular"],
                                        placeholder="e.g. ~1|LCD",
                                    ),
                                    ui.input_numeric(
                                        "asd_total",
                                        "Adaptive sampling locations to allocate",
                                        value=ASD_OPTIONS["total"],
                                        min=1,
                                        step=1,
                                    ),
                                    ui.input_numeric(
                                        "asd_delta",
                                        "Inhibition distance (delta)",
                                        value=ASD_OPTIONS["delta"],
                                        step=0.01,
                                    ),
                                    ui.div(
                                        {"style": "padding-top: 12px;"},
                                        ui.input_radio_buttons(
                                            "asd_target",
                                            None,
                                            choices={
                                                "H": "Targeting Hotspots",
                                                "U": "Targeting Uncertainty",
                                            },
                                            selected=ASD_OPTIONS["target"],
                                        ),
                                    ),
                                ),
                                ui.div(
                                    {
                                        "style": "margin-top: auto; display: flex; justify-content: flex-end;"
                                    },
                                    ui.input_action_button("run_asd", "Run"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        # Right column - leaflet map
        ui.column(
            6,
            {"class": "map-container"},
            ui.card(
                ui.card_body(
                    output_widget("map"),
                ),
                {"class": "map-card"},
            ),
        ),
    ),
    # Footer panel for attributions/logos
    ui.div(
        {"class": "footer-bar"},
        ui.div(
            {"class": "footer-text"},
            ui.span("Data sources: Etc. "),
            ui.br(),
            ui.span("Attribution text and project info can go here."),
        ),
        ui.div(
            {"class": "footer-logos"},
            ui.input_action_button(
                "help_btn",
                "",
                icon=icon_svg("circle-question", height="20px", width="20px"),
                class_="footer-icon footer-icon-button",
            ),
        ),
    ),
)
