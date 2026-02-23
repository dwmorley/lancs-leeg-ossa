from faicons import icon_svg
from shiny import module, reactive, ui


@module.ui
def footer_ui():
    return ui.tags.div(
        ui.div(
            ui.span("Data sources: Etc. "),
            ui.br(),
            ui.span("Attribution text and project info can go here."),
            class_="footer-text",
        ),
        ui.div(
            ui.input_action_button(
                "help_btn",
                "",
                icon=icon_svg("circle-question", height="20px", width="20px"),
                class_="footer-icon footer-icon-button",
            ),
            class_="footer-logos",
        ),
        class_="footer-bar",
    )


@module.server
def footer_server(input, output, session):

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
