# https://github.com/rstudio/shiny-gallery/blob/master/respiratory_disease_pyshiny/app.py
# https://github.com/posit-dev/py-shiny-templates/tree/main
# https://github.com/posit-dev/py-shiny-templates/tree/main/map-distance
# https://github.com/posit-dev/py-shiny/issues/464
# https://github.com/mattmajestic/shiny-py-docker
# https://hosting.analythium.io/containerizing-shiny-for-python-and-shinylive-applications/
# This migtht be how to deploy https://github.com/posit-dev/py-shinylive
# Can write a python script to download and launch the app locally
# PyInstaller desktop app (could do as github action) https://github.com/marketplace/actions/pyinstaller-action, Electron / Tauri wrapper (advanced)

import folium
import matplotlib.pyplot as plt
from shiny import App
from shiny import render
from shiny import ui

app_ui = ui.page_fluid(
    ui.h2("Hello Shiny!"),
    ui.input_slider("n", "N", 0, 100, 20),
    ui.output_text_verbatim("txt"),
    ui.output_plot("plot"),
    ui.output_ui("map"),
)


def server(input, output, session):
    @output
    @render.text
    def txt():
        return f"n*2 is {input.n() * 2}"

    @output
    @render.plot
    def plot():
        fig, ax = plt.subplots()
        ax.plot(range(input.n()))
        return fig

    @output
    @render.ui
    def map():
        # Create a map centered on London
        london_map = folium.Map(location=[51.5074, -0.1278], zoom_start=10)
        # Add a marker over London
        folium.Marker([51.5074, -0.1278], popup="London").add_to(london_map)
        # Return the HTML
        return ui.HTML(london_map._repr_html_())


app = App(app_ui, server)
