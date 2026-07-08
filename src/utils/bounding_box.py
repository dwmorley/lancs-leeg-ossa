"""Utilities to represent and manipulate bounding boxes for AOIs."""

import ast

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, Polygon


class BoundingBox:
    """Bounding box for spatial queries."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float
    utm_epsg: int
    resolution_m: float

    def __init__(self, *args, buffer: float = 0.15):
        """Initialize BoundingBox with flexible input.

        Parameters
        ----------
        *args : various
            Either four numbers (xmin, ymin, xmax, ymax) or a single iterable
            or JSON-like dict containing bounds.
        buffer : float, optional
            Buffer distance in degrees applied when computing bounds from
            coordinate collections (default: 0.15).
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
            elif isinstance(ast.literal_eval(str(arg[0])), dict):
                extents = ast.literal_eval(str(arg[0])).get("bounds", {})
                north = extents["north"]
                south = extents["south"]
                east = extents["east"]
                west = extents["west"]
                self.xmin = min(west, east)
                self.ymin = min(south, north)
                self.xmax = max(west, east)
                self.ymax = max(south, north)
            else:
                raise ValueError(
                    "Single argument must be a tuple/list of 4 bounds or "
                    "a numpy array/pandas DataFrame with coordinates"
                    "or a JSON-like dict with 'bounds' key containing north/south/east/west"
                )
        else:
            raise ValueError(
                "BoundingBox requires either 4 arguments (xmin, ymin, xmax, ymax) "
                "or 1 argument (bounds tuple/list or coordinates)"
                "or a JSON-like dict with 'bounds' key containing north/south/east/west"
            )

        # Validate bounds
        if self.xmin >= self.xmax:
            raise ValueError(f"xmin ({self.xmin}) must be less than xmax ({self.xmax})")
        if self.ymin >= self.ymax:
            raise ValueError(f"ymin ({self.ymin}) must be less than ymax ({self.ymax})")

        # Assign UTM EPSG code as a property
        self.utm_epsg = self.estimate_utm_epsg()

    def __repr__(self):
        """Return a concise string representation of the bounding box."""
        return (
            f"BoundingBox(xmin={self.xmin}, ymin={self.ymin}, xmax={self.xmax}, ymax={self.ymax})"
        )

    def estimate_utm_epsg(self) -> int:
        """Estimate the best UTM EPSG code for this bounding box (WGS84).

        Returns
        -------
        int
            EPSG code for the appropriate UTM zone (e.g., 32633).
        """
        center_lon = (self.xmin + self.xmax) / 2.0
        center_lat = (self.ymin + self.ymax) / 2.0
        utm_zone = int((center_lon + 180) / 6) + 1
        if center_lat >= 0:
            return 32600 + utm_zone  # Northern hemisphere
        else:
            return 32700 + utm_zone  # Southern hemisphere

    def to_soilgrids(self) -> tuple[float, float, float, float]:
        """Reproject bounding box to EPSG:152160 (Homolosine) for SoilGrids WCS.

        Returns
        -------
        tuple
            (west, south, east, north) in EPSG:152160 metres.
        """
        homolosine = "+proj=igh +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs"
        transformer = Transformer.from_crs("EPSG:4326", homolosine, always_xy=True)
        west, south = transformer.transform(self.xmin, self.ymin)
        east, north = transformer.transform(self.xmax, self.ymax)
        return west, south, east, north

    def to_list(self) -> list[float]:
        """Convert to list format [xmin, ymin, xmax, ymax]."""
        return [self.xmin, self.ymin, self.xmax, self.ymax]

    def to_tuple(self) -> tuple[float, float, float, float]:
        """Convert to tuple format (xmin, ymin, xmax, ymax)."""
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    def sampling_grid(self, n: int = 5000) -> np.ndarray:
        """Return an evenly spaced sampling grid of approximately n points.

        The function computes a spacing based on the requested number of points
        and returns a numpy array of point coordinates with shape (m, 2).
        """
        area = (self.xmax - self.xmin) * (self.ymax - self.ymin)
        point_density = n / area
        spacing = np.sqrt(1.0 / point_density)
        self.resolution_m = self.spacing_in_metres(spacing)
        x = np.arange(self.xmin, self.xmax + spacing, spacing)
        y = np.arange(self.ymin, self.ymax + spacing, spacing)
        x = x[x <= self.xmax]
        y = y[y <= self.ymax]
        X, Y = np.meshgrid(x, y)

        return np.column_stack([X.flatten(), Y.flatten()])

    def spacing_in_metres(self, spacing_deg: float) -> int:
        """Convert spacing in decimal degrees to metres at the bounding box center.

        Parameters
        ----------
        spacing_deg : float
            Spacing in decimal degrees.

        Returns
        -------
        int
            Spacing in metres at the center of the bounding box (rounded to nearest metre).
        """
        lon = (self.xmin + self.xmax) / 2
        lat = (self.ymin + self.ymax) / 2
        transformer = Transformer.from_crs(4326, self.utm_epsg, always_xy=True)
        x0, y0 = transformer.transform(lon, lat)
        x1, y1 = transformer.transform(lon + spacing_deg, lat)
        x2, y2 = transformer.transform(lon, lat + spacing_deg)
        # Use the average of x and y distances for a rough estimate
        dx = abs(x1 - x0)
        dy = abs(y2 - y0)

        # Round to the nearest whole metre and return as int
        return int(round((dx + dy) / 2))


def points_in_polygon(points: np.ndarray, polygon_coords: list[tuple[float, float]]) -> np.ndarray:
    """Filter points that fall within a polygon.

    Parameters
    ----------
    points : np.ndarray
        Array of points with shape (n, 2), where each row is [longitude, latitude].
    polygon_coords : list[tuple[float, float]]
        List of (longitude, latitude) tuples defining the polygon vertices.

    Returns
    -------
    np.ndarray
        Boolean array indicating which points are inside the polygon.
    """
    if not polygon_coords or len(polygon_coords) < 3:
        return np.ones(len(points), dtype=bool)

    polygon = Polygon(polygon_coords)
    mask = np.array([polygon.contains(Point(lon, lat)) for lon, lat in points])
    return mask


if __name__ == "__main__":
    bbox = BoundingBox([1.5, 6.0, 2.1, 7.0])
