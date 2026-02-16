from pathlib import Path

from shiny import App

from server import server
from ui import app_ui

# Create the Shiny app
app = App(app_ui, server, static_assets=Path(__file__).parent / "www")
