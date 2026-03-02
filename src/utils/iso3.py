import geopandas as gpd
from shapely.geometry import box

from src.utils.bounding_box import BoundingBox


def get_iso3_codes(bbox: BoundingBox) -> list[str]:

    # fn = "static/ne_50m_admin_0_countries.gpkg"
    fn = "/Users/david/Documents/GitHub/lancs-leeg-ossa/static/ne_50m_admin_0_countries.gpkg"

    world = gpd.read_file(fn)

    query_box = box(bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax)
    intersecting = world[world.geometry.intersects(query_box)]
    iso3_codes = intersecting["ISO_A3"].tolist()

    return iso3_codes
