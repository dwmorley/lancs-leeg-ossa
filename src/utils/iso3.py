"""Utilities to determine ISO3 country codes covering a bounding box."""

import sys
from pathlib import Path
from typing import List

import geopandas as gpd
from shapely.geometry import box

from src.utils.bounding_box import BoundingBox


def get_iso3_codes(bbox: BoundingBox) -> List[str]:
    """Return list of ISO3 country codes intersecting the bounding box.

    Parameters
    ----------
    bbox : BoundingBox or sequence
        Bounding box to test (expects [xmin, ymin, xmax, ymax] or BoundingBox).

    Returns
    -------
    List[str]
        List of 3-letter ISO country codes covering the bbox.
    """
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    fn = base_path / "static" / "ne_50m_admin_0_countries.gpkg"

    world = gpd.read_file(fn)

    query_box = box(bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax)
    intersecting = world[world.geometry.intersects(query_box)]
    iso3_codes = intersecting["ADM0_A3"].tolist()

    return iso3_codes
