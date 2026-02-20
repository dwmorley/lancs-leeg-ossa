import asyncio
import threading
import time

from shiny import ui


class ProgressManager:
    """Utility to manage UI progress indicators.

    - `create()` returns a `ui.Progress` context manager.
    - `start_auto_increment(progress, interval)` starts a background thread
      that increments the given progress object by +1 every `interval` seconds
      (wrapping at 100). Returns a `threading.Event` which can be set to stop
      the background incrementer.
    """

    def __init__(self):
        self._workers = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def create(self, min=0, max=100, message=""):
        # Capture the running event loop (if any) so background threads can
        # schedule UI updates safely using call_soon_threadsafe.
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop in this thread
            self._loop = None

        p = ui.Progress(min=min, max=max)
        if message:
            try:
                p.set(message=message)
            except Exception:
                # Setting message failed (session may be unavailable); ignore
                pass
        return p

    def start_auto_increment(self, progress, interval: float = 1.0, wrap: int = 100):
        stop_event = threading.Event()
        counter = {"v": 0}

        def _run():
            while not stop_event.is_set():
                counter["v"] = (counter["v"] + 1) % (wrap + 1)
                try:
                    if self._loop is not None:
                        # Schedule progress.set on the main event loop thread-safe
                        # to avoid calling async session methods from a background
                        # thread (which causes 'coroutine was never awaited').
                        self._loop.call_soon_threadsafe(
                            lambda v=counter["v"]: progress.set(value=v)
                        )
                    else:
                        # Fallback: call directly (may produce warnings if it
                        # requires awaiting internally).
                        progress.set(value=counter["v"])
                except Exception:
                    # UI update may fail if the session is closed; ignore and continue
                    pass
                time.sleep(interval)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        self._workers.append((t, stop_event))
        return stop_event
