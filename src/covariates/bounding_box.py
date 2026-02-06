import numpy as np
import pandas as pd


class BoundingBox:
    """
    Bounding box for spatial queries.

    Can be initialized with four bounds or from coordinates.
    """

    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def __init__(self, *args, buffer: float = 0.15):
        """
        Initialize BoundingBox with flexible input.

        Args:
            *args: Either:
                - Four numbers: xmin, ymin, xmax, ymax
                - Single tuple/list of 4 bounds
                - Single numpy array or DataFrame with coordinates
            buffer: Buffer distance in degrees (only for coordinate inputs)
        """
        if len(args) == 4:
            # Four separate arguments: xmin, ymin, xmax, ymax
            self.xmin, self.ymin, self.xmax, self.ymax = args
        elif len(args) == 1:
            arg = args[0]
            if isinstance(arg, (tuple, list)) and len(arg) == 4:
                # Single tuple/list of 4 bounds
                self.xmin, self.ymin, self.xmax, self.ymax = arg
            elif isinstance(arg, (np.ndarray, pd.DataFrame)):
                # Coordinates - compute bounds with buffer
                if isinstance(arg, pd.DataFrame):
                    coords = arg.values
                else:
                    coords = arg

                if coords.shape[1] != 2:
                    raise ValueError(
                        "Coordinates must have exactly 2 columns (longitude, latitude)"
                    )

                self.xmin = coords[:, 0].min() - buffer
                self.ymin = coords[:, 1].min() - buffer
                self.xmax = coords[:, 0].max() + buffer
                self.ymax = coords[:, 1].max() + buffer
            else:
                raise ValueError(
                    "Single argument must be a tuple/list of 4 bounds or "
                    "a numpy array/pandas DataFrame with coordinates"
                )
        else:
            raise ValueError(
                "BoundingBox requires either 4 arguments (xmin, ymin, xmax, ymax) "
                "or 1 argument (bounds tuple/list or coordinates)"
            )

        # Validate bounds
        if self.xmin >= self.xmax:
            raise ValueError(f"xmin ({self.xmin}) must be less than xmax ({self.xmax})")
        if self.ymin >= self.ymax:
            raise ValueError(f"ymin ({self.ymin}) must be less than ymax ({self.ymax})")

    def __repr__(self):
        """String representation of BoundingBox."""
        return f"BoundingBox(xmin={self.xmin}, ymin={self.ymin}, xmax={self.xmax}, ymax={self.ymax})"

    def to_list(self) -> list:
        """Convert to list format [xmin, ymin, xmax, ymax]."""
        return [self.xmin, self.ymin, self.xmax, self.ymax]

    def to_tuple(self) -> tuple:
        """Convert to tuple format (xmin, ymin, xmax, ymax)."""
        return (self.xmin, self.ymin, self.xmax, self.ymax)
