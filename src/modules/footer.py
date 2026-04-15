"""Footer UI components for the OSSA Shiny app."""

import tomllib
from pathlib import Path

from faicons import icon_svg
from shiny import module, reactive, ui

from src.constants import URLS


def get_version():
    """Read the version from pyproject.toml."""
    toml_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return data["tool"]["poetry"]["version"]


@module.ui
def footer_ui():
    """Return footer UI for the app."""
    return ui.tags.div(
        ui.tags.div(f"© 2026 Lancaster University | Version {get_version()}", class_="footer-left"),
        ui.tags.div(
            ui.tags.span(
                ui.input_action_button(
                    "help_btn",
                    "",
                    icon=icon_svg("circle-question", height="20px", width="20px"),
                    class_="footer-icon footer-icon-button",
                ),
            ),
            ui.tags.span(
                ui.input_action_button(
                    "info_btn",
                    "",
                    icon=icon_svg("circle-info", height="20px", width="20px"),
                    class_="footer-icon footer-icon-button",
                ),
            ),
            ui.tags.span(
                ui.input_action_button(
                    "github_btn",
                    "",
                    icon=icon_svg("github", height="20px", width="20px"),
                    class_="footer-icon footer-icon-button",
                ),
            ),
            ui.tags.span(
                ui.input_action_button(
                    "apikey_btn",
                    "",
                    icon=icon_svg("key", height="20px", width="20px"),
                    class_="footer-icon footer-icon-button",
                ),
            ),
        ),
        class_="app-footer",
    )


@module.server
def footer_server(input, output, session, reactive_values):
    """Server-side footer logic."""

    @reactive.effect
    @reactive.event(input.help_btn)
    def _show_help_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.tags.div(
                    ui.tags.div(
                        icon_svg("circle-question", height="28px", width="28px"),
                        ui.tags.h3(" How to use OSSA", style="margin:0;"),
                        style="display:flex; align-items:center; gap:10px; margin-bottom:15px;",
                    ),
                    ui.tags.hr(),
                    ui.tags.p(
                        "Please see the accompanying documentation for detailed instructions on how to use the application",
                        style="text-align:justify;",
                    ),
                    ui.tags.hr(),
                    ui.tags.p(
                        "For further guidance contact ",
                        ui.tags.a("Luigi Sedda", href=URLS["luigi_email"]),
                        ".",
                        style="font-size:0.85rem; color:#666;",
                    ),
                ),
                title=None,
                easy_close=True,
                footer=ui.modal_button("Close"),
                size="l",
            )
        )

    @reactive.effect
    @reactive.event(input.info_btn)
    def _show_info_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.tags.div(
                    ui.tags.div(
                        ui.tags.img(src="lulogo.png", height="50px", style="margin-right: 20px;"),
                        ui.tags.img(src="leegogo.webp", height="50px", style="margin-right: 20px;"),
                        ui.tags.img(
                            src="AnoSTEP logo.jpg", height="50px", style="margin-right: 20px;"
                        ),
                        ui.tags.img(src="ucsfn.jpg", height="50px"),
                        style="display:flex; align-items:center; justify-content:center; margin-bottom:20px;",
                    ),
                    ui.tags.h3(
                        "OSSA — Optimal Spatial Sampling Algorithm",
                        style="text-align:center; margin-bottom:5px;",
                    ),
                    ui.tags.p(
                        "Developed by the ",
                        ui.tags.a(
                            "Lancaster Ecology and Epidemiology Research Group (LEEG)",
                            href=URLS["leeg"],
                            target="_blank",
                        ),
                        " at Lancaster University.",
                        style="text-align:center; color:#666; margin-bottom:20px;",
                    ),
                    ui.tags.hr(),
                    ui.tags.p(
                        "OSSA is a set of algorithms developed for spatial sampling designs in absence of any prior "
                        "information about the process, such as species distribution or a disease prevalence (lattice "
                        "with close pairs) and for adaptive sampling designs (when prior information is available). "
                        "It also contains an algorithm for ecological area delineation.",
                        "The application supports multiple sampling frameworks including: "
                        "Clustering by Quadradic Discriminant Analysis (QDA) "
                        "Sample site selection by Lattice Close Pairs (LCP) or Adaptive Sampling Design (ASD) ",
                        style="text-align:justify;",
                    ),
                    ui.tags.p(
                        ui.tags.ul(
                            ui.tags.li(ui.tags.strong("Luigi Sedda"), " — PI, Algorithm design"),
                            ui.tags.li(
                                ui.tags.strong("David Morley"), " — Python/Shiny implementation"
                            ),
                        ),
                        style="text-align:justify;",
                    ),
                    ui.tags.hr(),
                    ui.tags.p(
                        ui.tags.strong("Version: "),
                        get_version(),
                        ui.tags.br(),
                        ui.tags.strong("Licence: "),
                        "???",
                        ui.tags.br(),
                        ui.tags.strong("Contact: "),
                        ui.tags.a("Luigi Sedda", href=URLS["luigi_email"], target="_blank"),
                        style="font-size:0.85rem; color:#666;",
                    ),
                ),
                title=None,
                easy_close=True,
                footer=ui.modal_button("Close"),
                size="l",
            )
        )

    @reactive.effect
    @reactive.event(input.github_btn)
    def _show_github_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.tags.div(
                    icon_svg("github", height="28px", width="28px"),
                    ui.tags.h3(" GitHub Repository", style="margin:0;"),
                    style="display:flex; align-items:center; gap:10px; margin-bottom:15px;",
                ),
                ui.p(
                    "Source code available at: ",
                    ui.a(URLS["github"], href=URLS["github"], target="_blank"),
                ),
                easy_close=True,
                footer=ui.modal_button("Close"),
            )
        )

    @reactive.effect
    @reactive.event(input.apikey_btn)
    def _show_apikey_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.tags.div(
                    icon_svg("key", height="28px", width="28px"),
                    ui.tags.h3(" API Key Management", style="margin:0;"),
                    style="display:flex; align-items:center; gap:10px; margin-bottom:15px;",
                ),
                ui.input_text(
                    "ecmwf_key_input",
                    "ECMWF CDS API Key",
                    value=reactive_values["ecmwf_api_key"].get(),
                    placeholder="something like this: du7mm2y-k8ey-4x8x-b3e1-f7ak2e056a18",
                    width="100%",
                ),
                easy_close=True,
                footer=ui.modal_button("Save", class_="btn-primary"),
            )
        )

    @reactive.effect
    @reactive.event(input.ecmwf_key_input)
    def _save_apikey() -> None:
        reactive_values["ecmwf_api_key"].set(input.ecmwf_key_input())
