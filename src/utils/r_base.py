"""Base class for shared R computation logic across sampling routines."""

import re
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

    @staticmethod
    def extract_formula_variables(formula: str) -> list[str]:
        """Extract variable names from an R formula string.

        Parameters
        ----------
        formula : str
            R formula string (e.g., "y ~ x1 + x2 + x3")

        Returns
        -------
        list[str]
            List of variable names found in the formula
        """
        # Remove whitespace and operators
        # Match valid R variable names: alphanumeric, dots, underscores (not starting with digit)
        pattern = r"[a-zA-Z_.][a-zA-Z0-9_]*"
        matches = re.findall(pattern, formula)
        return matches

    @staticmethod
    def validate_formula_variables(
        formula: str, data: pd.DataFrame, formula_name: str = "formula"
    ) -> None:
        """Validate that all variables in a formula string are present in data.

        Parameters
        ----------
        formula : str
            R formula string (e.g., "y ~ x1 + x2 + x3")
        data : pd.DataFrame
            DataFrame with available columns
        formula_name : str, optional
            Name of the formula parameter for error messages

        Raises
        ------
        ValueError
            If any variables in the formula are not found in the data
        """
        # Extract variables from formula
        formula_vars = RComputationBase.extract_formula_variables(formula)

        # Get available columns (excluding x/y which are renamed from lng/lat)
        available_cols = set(data.columns)

        # Find missing variables
        missing_vars = set(formula_vars) - available_cols

        if missing_vars:
            available_list = ", ".join(sorted(available_cols))
            missing_list = ", ".join(sorted(missing_vars))
            raise ValueError(
                f"The following variables in {formula_name} are not found in data:\n"
                f"  Missing: {missing_list}\n"
                f"  Available columns: {available_list}"
            )

    @staticmethod
    def validate_random_formula_syntax(formula: str, formula_name: str = "formula") -> bool:
        """Validate R formula syntax for RANDOM effects.

        Parameters
        ----------
        formula : str
            R formula string
        formula_name : str, optional
            Name of the formula parameter for error messages

        Returns
        -------
        bool
            True if formula is valid, raises ValueError if not

        Raises
        ------
        ValueError
            If formula is empty, missing tilde, or has invalid structure
        """
        if not formula or not formula.strip():
            raise ValueError(
                f"{formula_name} cannot be empty. Please provide a valid R formula (e.g., ~ 1 | Group)."
            )

        if "~" not in formula:
            raise ValueError(
                f"{formula_name} must contain a tilde (~) separator. "
                f"Expected format, like: ~ 1 | Group, or 0 + var1 | var4"
            )

        parts = formula.split("~")
        if len(parts) != 2:
            raise ValueError(
                f"{formula_name} must have exactly one tilde (~) separator. "
                f"Expected format, like: ~ 1 | Group, or 0 + var1 | var4"
            )

        left_side = parts[0].strip()
        right_side = parts[1].strip()

        if left_side:
            raise ValueError(
                f"{formula_name} there should be nothing on the left side of the tilde (~)."
            )

        if not right_side:
            raise ValueError(
                f"{formula_name} must have predictor variables on the right side of the tilde (~)."
            )

        return True

    @staticmethod
    def validate_fixed_formula_syntax(formula: str, formula_name: str = "formula") -> bool:
        """Validate R formula syntax for FIXED effects.

        Parameters
        ----------
        formula : str
            R formula string
        formula_name : str, optional
            Name of the formula parameter for error messages

        Returns
        -------
        bool
            True if formula is valid, raises ValueError if not

        Raises
        ------
        ValueError
            If formula is empty, missing tilde, or has invalid structure
        """
        # Check if formula is empty or only whitespace
        if not formula or not formula.strip():
            raise ValueError(
                f"{formula_name} cannot be empty. Please provide a valid R formula (e.g., Response~Var1+Var2)."
            )

        # Check if formula contains the required tilde separator
        if "~" not in formula:
            raise ValueError(
                f"{formula_name} must contain a tilde (~) separator. "
                f"Expected format: Response~Predictors (e.g., AnGam~Week+Elev)"
            )

        # Check that there are variables on both sides of the tilde
        parts = formula.split("~")
        if len(parts) != 2:
            raise ValueError(
                f"{formula_name} must have exactly one tilde (~) separator. "
                f"Expected format: Response~Predictors"
            )

        left_side = parts[0].strip()
        right_side = parts[1].strip()

        if not left_side:
            raise ValueError(
                f"{formula_name} must have a response variable on the left side of the tilde (~)."
            )

        if not right_side:
            raise ValueError(
                f"{formula_name} must have predictor variables on the right side of the tilde (~)."
            )

        return True

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
