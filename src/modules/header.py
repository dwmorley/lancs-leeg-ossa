from shiny import module, ui

from src.constants import URLS


@module.ui
def header_ui():
    return ui.tags.div(
        ui.tags.div(
            ui.tags.h1("OSSA - Optimal Spatial Sampling Algorithm", class_="header-title"),
        ),
        ui.tags.div(
            ui.tags.a(
                ui.img(src="lulogo.png", class_="logo-img", alt="Logo 1"),
                href=URLS["lms"],
                target="_blank",
            ),
            class_="logo-container",
        ),
        class_="app-header",
    )


@module.server
def header_server(input, output, session):
    pass
