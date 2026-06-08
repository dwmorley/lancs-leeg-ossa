"""UI header components for the OSSA Shiny app."""

from shiny import module, ui

from src.constants import URLS


@module.ui
def header_ui():
    """Return the header UI components for the app."""
    return ui.tags.div(
        ui.tags.a(
            ui.img(src="ossa_logo2.png", class_="logo-img", alt="OSSA logo"),
            href=URLS["ossa"],
            target="_blank",
            class_="header-left-logo",
        ),
        ui.tags.h1("Optimal Spatial Sampling Algorithm", class_="header-title"),
        ui.tags.a(
            ui.img(src="lulogo.png", class_="logo-img", alt="LU logo"),
            href=URLS["lms"],
            target="_blank",
            class_="header-right-logo",
        ),
        class_="app-header",
    )


@module.server
def header_server(input, output, session):
    """Server-side header logic."""
    pass
