from shiny import module, ui

from constants import URLS


@module.ui
def header_ui():
    return ui.tags.div(
        ui.tags.div(
            ui.div("OSSA - Optimal Spatial Sampling Algorithm"), class_="app-title"
        ),
        ui.tags.div(
            ui.tags.a(
                ui.img(src="lulogo.png", class_="logo-img", alt="Logo 1"),
                href=URLS["lms"],
                target="_blank",
            ),
            class_="logo-container",
        ),
        class_="header-bar",
    )


@module.server
def header_server(input, output, session):
    pass
