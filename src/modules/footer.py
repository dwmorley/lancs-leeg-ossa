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
                ui.h4("Help"),
                ui.p("Add your help text or instructions here."),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.info_btn)
    def _show_info_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.h4("Information"),
                ui.p("Add your information text here."),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.github_btn)
    def _show_github_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.h4("GitHub Repository"),
                ui.p(
                    "Source code available at: ",
                    ui.a(URLS["github"], href=URLS["github"], target="_blank"),
                ),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.apikey_btn)
    def _show_apikey_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.input_text(
                    "ecmwf_key_input",
                    "ECMWF CDS API Key",
                    value=reactive_values["ecmwf_api_key"].get(),
                    placeholder="like this: a3f7c821-4d12-4b8e-b3e1-7f9d2c056a18",
                    width="100%",
                ),
                title="API Key Management",
                easy_close=True,
                footer=ui.modal_button("Save", class_="btn-primary"),
            )
        )

    @reactive.effect
    @reactive.event(input.ecmwf_key_input)
    def _save_apikey() -> None:
        reactive_values["ecmwf_api_key"].set(input.ecmwf_key_input())
