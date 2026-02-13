from pathlib import Path

import leafmap
from faicons import icon_svg
from ipyleaflet import DrawControl, LayersControl
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

COVARIATE_OPTIONS = {
    "landcover": "Land Cover",
    "elevation": "Elevation",
    "slope": "Slope",
    "ndvi": "NDVI",
    "rainfall": "Rainfall",
    "temperature": "Temperature",
    "soil_moisture": "Soil Moisture",
    "population": "Population",
    "roads": "Road Distance",
    "settlements": "Settlements",
    "river_dist": "River Distance",
    "aspect": "Aspect",
    "curvature": "Curvature",
    "twi": "Topographic Wetness Index",
}

app_ui = ui.page_fluid(
    ui.tags.style(
        """
        html, body {
            font-size: 14px;
        }
        .header-bar {
            background-color: #F5F5F5;
            color: white;
            padding: 15px 15px;
            margin: 15px -15px 15px -15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .app-title {
            font-size: 24px;
            font-weight: bold;
            color: #808080;
            margin: 0;
        }
        .logo-container {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        .logo-img {
            height: 40px;
            width: auto;
        }
        .footer-bar {
            background-color: #f5f7f9;
            color: #2c3e50;
            padding: 12px 20px;
            margin: 20px -15px -15px -15px;
            border-top: 1px solid #e1e6ea;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 15px;
            flex-wrap: wrap;
        }
        .footer-text {
            font-size: 13px;
            line-height: 1.4;
        }
        .footer-logos {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        .footer-logo {
            height: 28px;
            width: auto;
        }
        .footer-icon svg {
            height: 84px;
            width: 84px;
        }
        .footer-icon-button {
            background: transparent;
            border: none;
            padding: 0;
            margin: 0;
            line-height: 0;
        }
        .footer-icon-button:focus {
            outline: 2px solid #2c3e50;
            outline-offset: 2px;
        }
        #progress-bar {
            height: 3px;
            background-color: #0066cc;
            transition: width 0.3s ease;
            width: 100%;
            margin: 12px -15px -15px -15px;
            padding: 0 15px;
            box-sizing: border-box;
        }
        .card-custom {
            height: 100%;
            margin-bottom: 15px;
        }
        .left-column {
            height: 800px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .top-card {
            flex: 1 1 0;
            min-height: 0;
        }
        .middle-card {
            flex: 3 1 0;
            min-height: 0;
        }
        .bottom-card {
            flex: 4.2 1 0;
            min-height: 0;
        }
        .top-card .card,
        .middle-card .card,
        .bottom-card .card {
            height: 100%;
        }
        .top-card .card-body,
        .middle-card .card-body {
            height: 100%;
            overflow: auto;
        }
        .bottom-card .card-body {
            height: 100%;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .bottom-card .nav-tabs {
            flex: 0 0 auto;
        }
        .bottom-card .tab-content {
            flex: 1 1 auto;
            overflow: hidden;
        }
        .bottom-card .tab-pane {
            height: 100%;
            overflow: auto;
        }
        .map-container {
            height: 803px;
        }
        .map-card {
            height: 100%;
            display: flex;
            flex-direction: column;
        }
        .map-card .card-body {
            flex: 1;
            padding: 0 !important;
            overflow: hidden;
        }
        .bounds-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            width: 100%;
            margin: 10px 0 0 0;
        }
        .bounds-cell {
            background: #f5f7f9;
            border: 1px solid #e1e6ea;
            border-radius: 6px;
            padding: 6px 8px;
            text-align: center;
            font-size: 12px;
            line-height: 1.2;
            color: #2c3e50;
        }
        .checkbox-scroll {
            max-height: 220px;
            overflow: auto;
            border: 1px solid #e1e6ea;
            border-radius: 6px;
            padding: 8px 6px 4px 6px;
            background: #ffffff;
            width: 100%;
        }
        .checkbox-scroll .form-check {
            margin-bottom: 1px;
            padding-left: 16px;
        }
        .checkbox-scroll .form-check-input {
            margin-top: 1px;
            transform: scale(0.8);
            transform-origin: top left;
        }
        .checkbox-scroll .form-check-label {
            font-size: 10px;
            line-height: 0.95;
        }
        #map {
            height: 100% !important;
            width: 100% !important;
        }
        #map iframe {
            border: none;
            height: 100% !important;
            width: 100% !important;
        }
        iframe {
            border: none;
        }
    """
    ),
    ui.div(
        {"class": "header-bar"},
        ui.div({"class": "app-title"}, "OSSA - Optimal Spatial Sampling Algorithm"),
        ui.div(
            {"class": "logo-container"},
            ui.img(src="lulogo.png", class_="logo-img", alt="Logo 1"),
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
                ui.card(
                    ui.card_body(
                        ui.div(
                            {"class": "bounds-row"},
                            ui.div(
                                {"class": "bounds-cell"}, ui.output_text("bounds_west")
                            ),
                            ui.div(
                                {"class": "bounds-cell"}, ui.output_text("bounds_south")
                            ),
                            ui.div(
                                {"class": "bounds-cell"}, ui.output_text("bounds_north")
                            ),
                            ui.div(
                                {"class": "bounds-cell"}, ui.output_text("bounds_east")
                            ),
                        ),
                    ),
                ),
            ),
            # Middle card
            ui.div(
                {"class": "middle-card"},
                ui.card(
                    ui.card_body(
                        ui.div(
                            {"style": "display: flex; gap: 12px; height: 100%;"},
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
                                        value=5000,
                                        min=1,
                                        step=1,
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
                                ui.p("Qudradic Discriminant Analysis"),
                                ui.div(
                                    {
                                        "style": "display: flex; gap: 12px; align-items: flex-start;"
                                    },
                                    ui.div(
                                        ui.input_numeric(
                                            "qda_nx",
                                            "nx",
                                            value=10,
                                            min=1,
                                            step=1,
                                        ),
                                        ui.input_numeric(
                                            "qda_nn",
                                            "nn",
                                            value=0.5,
                                            step=0.1,
                                        ),
                                    ),
                                ),
                                ui.div(
                                    {"style": "margin-top: auto;"},
                                    ui.input_action_button("run_qda", "Run QDA"),
                                ),
                            ),
                        ),
                        ui.nav_panel(
                            "LCP",
                            ui.div(
                                {"style": "padding: 15px;"},
                                ui.p("Lattice Close Pairs"),
                                ui.output_text("tab2_output"),
                            ),
                        ),
                        ui.nav_panel(
                            "ASD",
                            ui.div(
                                {"style": "padding: 15px;"},
                                ui.p("Adaptive Sampling"),
                                ui.output_text("tab3_output"),
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
    # Progress bar above footer
    ui.div({"id": "progress-bar"}),
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


# Define the server logic
def server(input, output, session):

    # Store drawn rectangles
    drawn_shapes = reactive.Value([])

    # Create the map once using leafmap
    m = leafmap.Map(
        center=(1.5, 20.0),
        zoom=3,
        height="800px",
        width="100%",
        draw_control=False,
        toolbar_control=False,
    )

    # Add basemap layers
    m.add_basemap("Esri.WorldImagery")

    # Add layer control for toggling basemaps
    m.add(LayersControl(position="topright"))

    # Create drawing control
    draw_control = DrawControl(
        polyline={},
        polygon={},
        circle={},
        circlemarker={},
        marker={},
        rectangle={
            "shapeOptions": {"color": "red", "fillColor": "red", "fillOpacity": 0.2}
        },
        edit=False,
        remove=False,
    )

    # Add to map
    m.add(draw_control)

    # Use traitlets observe to capture draw events
    def on_draw_change(change):
        if change["new"] and change["new"].get("geometry"):
            geo_json = change["new"]
            if geo_json.get("geometry", {}).get("type") == "Polygon":
                coords = geo_json["geometry"]["coordinates"][0]
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]

                rectangle_data = {
                    "type": "rectangle",
                    "geometry": geo_json["geometry"],
                    "bounds": {
                        "north": max(lats),
                        "south": min(lats),
                        "east": max(lons),
                        "west": min(lons),
                    },
                }

                # Keep only the latest rectangle
                draw_control.data = [geo_json]
                drawn_shapes.set([rectangle_data])

    # Observe changes to last_draw trait
    draw_control.observe(on_draw_change, "last_draw")

    # Ensure landcover is always selected
    @reactive.effect
    @reactive.event(input.covariate_vars)
    def _keep_landcover_selected():
        current_vars = input.covariate_vars()
        if current_vars is None or "landcover" not in current_vars:
            # Re-add landcover if it was unchecked
            new_vars = list((current_vars or [])) + ["landcover"]
            ui.update_checkbox_group("covariate_vars", selected=new_vars)

    @render.text
    def summary_text():
        return "Dynamic summary information will appear here."

    def _latest_bounds():
        shapes = drawn_shapes.get()
        if not shapes:
            return None
        return shapes[-1]["bounds"]

    @render.text
    def bounds_north():
        bounds = _latest_bounds()
        if not bounds:
            return "North: --"
        return f"North: {bounds['north']:.6f}"

    @render.text
    def bounds_south():
        bounds = _latest_bounds()
        if not bounds:
            return "South: --"
        return f"South: {bounds['south']:.6f}"

    @render.text
    def bounds_east():
        bounds = _latest_bounds()
        if not bounds:
            return "East: --"
        return f"East: {bounds['east']:.6f}"

    @render.text
    def bounds_west():
        bounds = _latest_bounds()
        if not bounds:
            return "West: --"
        return f"West: {bounds['west']:.6f}"

    @render.text
    def tab1_output():
        return "This is dynamic content for Tab 1."

    @render.text
    def tab2_output():
        return "This is dynamic content for Tab 2."

    @render.text
    def tab3_output():
        return "This is dynamic content for Tab 3."

    @reactive.effect
    @reactive.event(input.help_btn)
    def _show_help_modal():
        ui.modal_show(
            ui.modal(
                ui.h4("Help"),
                ui.p("Add your help text or instructions here."),
                easy_close=True,
                footer=None,
            )
        )

    @render_widget
    def map():
        return m


# Create the Shiny app
app = App(app_ui, server, static_assets=Path(__file__).parent / "www")
