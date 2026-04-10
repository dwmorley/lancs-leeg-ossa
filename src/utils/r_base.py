"""Base class for shared R computation logic across sampling routines."""

from abc import ABC, abstractmethod
from typing import Any, Callable

import pandas as pd
from rpy2.rinterface_lib import callbacks as rpy2_callbacks
from rpy2.rinterface_lib.embedded import RRuntimeError


class RComputationBase(ABC):
    """Base class for R-based computations with shared progress tracking."""

    def __init__(
        self,
        on_progress: Callable[[float, str, str], None] | None = None,
    ):
        """Initialise R computation base.

        Parameters
        ----------
        on_progress : callable, optional
            If provided, called as ``on_progress(value, message, detail)`` where
            *value* is a float in [0, 1] indicating overall progress, *message*
            is the current stage label, and *detail* is a live string from the R
            console. Useful for updating a progress bar in a UI such as Shiny.
        """
        self.on_progress = on_progress
        self._state: dict = {"value": 0.0, "message": "Starting..."}
        self._original_print = None
        self._original_warnerror = None

    def _setup_r_callbacks(self) -> None:
        """Install rpy2 console-write hooks so R verbose output is forwarded."""
        self._original_print = rpy2_callbacks.consolewrite_print
        self._original_warnerror = rpy2_callbacks.consolewrite_warnerror

        if self.on_progress is not None:

            def _consolewrite_hook(s: str) -> None:
                stripped = s.strip()
                if stripped:
                    self.on_progress(self._state["value"], self._state["message"], stripped)
                self._original_print(s)

            def _warnerror_hook(s: str) -> None:
                stripped = s.strip()
                if stripped:
                    self.on_progress(self._state["value"], self._state["message"], stripped)
                self._original_warnerror(s)

            rpy2_callbacks.consolewrite_print = _consolewrite_hook
            rpy2_callbacks.consolewrite_warnerror = _warnerror_hook

    def _restore_r_callbacks(self) -> None:
        """Restore original rpy2 callbacks."""
        if self._original_print is not None:
            rpy2_callbacks.consolewrite_print = self._original_print
        if self._original_warnerror is not None:
            rpy2_callbacks.consolewrite_warnerror = self._original_warnerror

    def _prog(self, value: float, message: str, detail: str = "") -> None:
        """Update shared state and fire the progress callback.

        Parameters
        ----------
        value : float
            Progress value in [0, 1]
        message : str
            Current stage label
        detail : str, optional
            Live output detail from R console
        """
        self._state["value"] = value
        self._state["message"] = message
        if self.on_progress is not None:
            self.on_progress(value, message, detail)

    @staticmethod
    def rename_lonlat_to_xy(df: pd.DataFrame) -> pd.DataFrame:
        """Rename longitude/latitude to x/y (case-insensitive) for R compatibility.

        Parameters
        ----------
        df : pd.DataFrame
            Input dataframe with longitude/latitude columns

        Returns
        -------
        pd.DataFrame
            Renamed dataframe
        """
        col_map = {}
        for col in df.columns:
            if col.lower() in ["longitude", "lng", "long"]:
                col_map[col] = "x"
            elif col.lower() in ["latitude", "lat", "ltd"]:
                col_map[col] = "y"
        return df.rename(columns=col_map)

    @abstractmethod
    def _compute(self) -> Any:
        """Perform the actual R computation. Must be implemented by subclasses."""
        pass

    def compute(self) -> Any:
        """Execute the R computation with proper callback management.

        Returns
        -------
        Any
            Result of the computation

        Raises
        ------
        RuntimeError
            If R computation fails
        """
        self._setup_r_callbacks()
        try:
            return self._compute()
        finally:
            self._restore_r_callbacks()

    def _handle_r_error(self, r_err: RRuntimeError) -> None:
        """Handle R runtime errors.

        Parameters
        ----------
        r_err : RRuntimeError
            The R runtime error

        Raises
        ------
        RuntimeError
            Wrapped error with context
        """
        msg = str(r_err)
        if self.on_progress is not None:
            self.on_progress(1.0, "R Error", msg)
        raise RuntimeError(f"R error during computation: {msg}") from r_err

    def _handle_python_error(self, e: Exception) -> None:
        """Handle Python errors during computation.

        Parameters
        ----------
        e : Exception
            The Python exception

        Raises
        ------
        Exception
            Re-raised after reporting progress
        """
        msg = str(e)
        if self.on_progress is not None:
            self.on_progress(1.0, "Python Error", msg)
        raise
