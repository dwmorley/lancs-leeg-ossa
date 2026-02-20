from typing import Optional, Tuple

import pandas as pd


class FileManager:
    """Handles uploaded files and CSV parsing/validation."""

    def parse_uploaded_csv(self, file_info) -> Optional[pd.DataFrame]:
        """Read an uploaded CSV `file_info` as provided by Shiny `input.data_file()`.

        Returns a DataFrame or None if `file_info` is falsy. Raises on read errors.
        """
        if not file_info:
            return None
        path = file_info[0]["datapath"]
        return pd.read_csv(path)

    def validate_has_latlon(self, df: pd.DataFrame) -> None:
        """Raise ValueError if required columns are missing."""
        required = {"latitude", "longitude"}
        if not required.issubset(set(df.columns)):
            raise ValueError("CSV must contain 'latitude' and 'longitude' columns")

    def get_bounds_from_df(self, df: pd.DataFrame) -> Tuple[float, float, float, float]:
        """Return (north, south, east, west) from a DataFrame with lat/lon."""
        self.validate_has_latlon(df)
        north = float(df["latitude"].max())
        south = float(df["latitude"].min())
        east = float(df["longitude"].max())
        west = float(df["longitude"].min())
        return north, south, east, west
