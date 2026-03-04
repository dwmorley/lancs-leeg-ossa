"""Footer UI components for the OSSA Shiny app."""

from faicons import icon_svg
from shiny import module, reactive, ui


@module.ui
def footer_ui():
    """Return footer UI for the app."""
    return ui.tags.div(
        ui.tags.div("© 2026 Lancaster University | Version 0.0.0", class_="footer-left"),
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
def footer_server(input, output, session):
    """Server-side footer logic (no-op)."""

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
                ui.p("Add your information text here."),
                easy_close=True,
                footer=None,
            )
        )

    @reactive.effect
    @reactive.event(input.apikey_btn)
    def _show_apikey_modal() -> None:
        ui.modal_show(
            ui.modal(
                ui.h4("API Key Management"),
                ui.p("Add your API key management instructions here."),
                easy_close=True,
                footer=None,
            )
        )
