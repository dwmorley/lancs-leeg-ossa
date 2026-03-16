"""Shared validation utilities for OSSA analysis modules."""

import numpy as np
import pandas as pd
from shiny import ui

from src.constants import RESPONSE_OPTIONS


def validate_extracted_df(extracted_df: pd.DataFrame | None) -> bool:
    """Validate extracted DataFrame before running analysis.

    Checks that:
    - ``extracted_df`` is not None
    - it contains exactly one recognised response variable
    - it has no constant (zero-variance) columns
    - it contains 'longitude' and 'latitude' columns
    - it contains more than one covariate column (i.e. more than 4 columns total)

    Shows a Shiny error/warning notification for each failing check and returns
    ``False`` so the caller can bail out early.  Returns ``True`` when all
    checks pass.
    """
    if extracted_df is None:
        ui.notification_show("Please run the data extraction first, or upload a csv", type="error")
        return False

    response = [k for k in RESPONSE_OPTIONS.keys() if k in extracted_df.columns]
    if len(response) != 1:
        ui.notification_show(
            f"DataFrame must contain exactly one response variable from: {RESPONSE_OPTIONS.values()}.",
            type="error",
        )
        return False

    constant_cols = extracted_df.columns[np.where(extracted_df.std(axis=0) == 0)[0]].tolist()
    if len(constant_cols) > 0:
        ui.notification_show(f"Data contains constant columns: {constant_cols}", type="error")
        return False

    if "longitude" not in extracted_df.columns or "latitude" not in extracted_df.columns:
        ui.notification_show(
            "Data table must contain 'longitude' and 'latitude' columns.", type="error"
        )
        return False

    if len(extracted_df.columns) <= 4:
        ui.notification_show(
            "DataFrame must contain more than one covariate column for analysis.",
            type="error",
        )
        return False

    return True
