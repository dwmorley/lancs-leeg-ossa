import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from src.utils.bounding_box import BoundingBox


def get_iso3_codes(bbox: BoundingBox) -> list[str]:

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    fn = base_path / "static" / "ne_50m_admin_0_countries.gpkg"

    world = gpd.read_file(fn)

    query_box = box(bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax)
    intersecting = world[world.geometry.intersects(query_box)]
    iso3_codes = intersecting["ISO_A3"].tolist()

    return iso3_codes
