"""Utilities for progress tracking with non-closeable notifications."""

from contextlib import contextmanager
from typing import Generator, Optional

from shiny import ui


@contextmanager
def non_closeable_progress(
    min: int = 0, max: int = 1, session: Optional[object] = None
) -> Generator:
    """Create a progress bar that cannot be closed by the user.

    This is a wrapper around ui.Progress that creates a non-closeable notification
    by overriding the close button functionality. During the context, the progress
    object can be updated using .set() method.

    Parameters
    ----------
    min : int
        The minimum value of the progress bar (default: 0).
    max : int
        The maximum value of the progress bar (default: 1).
    session : Optional
        The Shiny session (optional, inferred if not provided).

    Yields
    ------
    ProgressProxy
        A progress-like object that can be used to update the progress bar.
    """

    class ProgressProxy:
        """Proxy object to manage non-closeable progress."""

        def __init__(self):
            self.notification_id = None
            self.min = min
            self.max = max
            self.value = min
            self.message = "Processing..."
            self.detail = ""

        def set(
            self,
            value: Optional[int] = None,
            message: Optional[str] = None,
            detail: Optional[str] = None,
        ) -> None:
            """Update the progress bar.

            Parameters
            ----------
            value : Optional[int]
                The new value of the progress bar.
            message : Optional[str]
                The message to display.
            detail : Optional[str]
                The detail text to display below the message.
            """
            if value is not None:
                self.value = value
            if message is not None:
                self.message = message
            if detail is not None:
                self.detail = detail

            self._update_notification()

        def _update_notification(self) -> None:
            """Update the notification with current progress."""
            # Calculate progress percentage
            if self.max > self.min:
                percent = int((self.value - self.min) / (self.max - self.min) * 100)
            else:
                percent = 100

            # Create progress bar HTML
            progress_html = f"""
            <div style="margin-bottom: 10px;">
                <div style="font-weight: bold; margin-bottom: 5px;">{self.message}</div>
                {f'<div style="font-size: 0.9em; margin-bottom: 5px; color: #666;">{self.detail}</div>' if self.detail else ''}
                <div style="width: 100%; height: 20px; background-color: #e0e0e0; border-radius: 4px; overflow: hidden;">
                    <div style="height: 100%; background-color: #1f77b4; width: {percent}%; transition: width 0.3s ease;"></div>
                </div>
                <div style="font-size: 0.85em; margin-top: 5px; color: #666;">{self.value}/{self.max}</div>
            </div>
            """

            # Show or update notification
            if self.notification_id is None:
                self.notification_id = ui.notification_show(
                    ui.HTML(progress_html),
                    duration=None,
                    close_button=False,
                    type="default",
                )
            else:
                # Update existing notification
                self.notification_id = ui.notification_show(
                    ui.HTML(progress_html),
                    duration=None,
                    close_button=False,
                    type="default",
                    id=self.notification_id,
                )

    proxy = ProgressProxy()
    proxy._update_notification()

    try:
        yield proxy
    finally:
        # Remove the notification when done
        if proxy.notification_id:
            ui.notification_remove(proxy.notification_id)
