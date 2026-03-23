"""UI header components for ZSSA models."""

from shiny import module, ui


@module.ui
def zssa_ui():
    """Return UI components for the ZSSA panel."""
    return ui.tags.div()


@module.server
def header_server(input, output, session):
    """Server logic for the ZSSA panel."""
    pass
