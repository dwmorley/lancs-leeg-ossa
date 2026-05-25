"""Small helpers for saving downloads and writing CSV output."""

import os
import platform
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd


def get_downloads_folder():
    """Get the Downloads folder path for the current platform.

    Respects the DOWNLOAD_DIR environment variable when set (e.g. in Docker).

    When running in Docker:
    - The DOWNLOAD_DIR should be set to /app/output
    - Files will be saved to the volume mounted on the host (e.g., ./output)
    - This provides a clean, simple path instead of complex WSL overlay paths

    Returns:
        Path: The directory where files should be downloaded/saved to.
    """
    env_dir = os.environ.get("DOWNLOAD_DIR")
    if env_dir:
        return Path(env_dir)
    if platform.system() == "Windows":
        import winreg

        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return Path(location)
    else:
        # macOS and Linux
        return Path.home() / "Downloads"


def save_csv(csv_name: str, dataframe) -> Path:
    """Save a single dataframe as a CSV to the downloads folder."""
    csv_path = get_downloads_folder() / csv_name
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(csv_path, index=False)
    return csv_path


def write_kml(gdf: gpd.GeoDataFrame, fn: str):
    """Write GeoDataFrame geometries to a KML."""
    kml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    kml_content += '<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n'

    if "lcp_sites" in str(fn):

        color_map = {
            "G": "FF0000FF",  # Red
            "I": "FF00FF00",  # Green
        }
        for type_name, color in color_map.items():
            kml_content += f"""<Style id="style_{type_name}">
                <IconStyle>
                    <Icon>
                        <href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href>
                    </Icon>
                    <color>{color}</color>
                    <scale>1.2</scale>
                </IconStyle>
            </Style>\n"""

        kml_content += "<Folder>\n"
        for idx, row in gdf.iterrows():
            coords = f"{row.geometry.x},{row.geometry.y}"
            style_id = f"style_{row['type']}"
            description = f"<![CDATA[<b>Class:</b> {row['class']}<br/><b>Type:</b> {row['type']}<br/><b>Coordinates:</b> {row.geometry.y}, {row.geometry.x}]]>"
            kml_content += f"""<Placemark>
                    <name>{row['type']}</name>
                    <description>{description}</description>
                    <styleUrl>#{style_id}</styleUrl>
                    <Point><coordinates>{coords}</coordinates></Point>
                </Placemark>\n"""
        kml_content += "</Folder>\n</Document>\n</kml>"

    elif "sc-asd_sites" in str(fn):

        kml_content += "<Folder>\n"
        for idx, row in gdf.iterrows():
            coords = f"{row.geometry.x},{row.geometry.y}"
            if "Fit" in gdf.columns:
                description = f"<![CDATA[<b>Uncertainty:</b> {row['Uncertainty']}<br/><b>Fit:</b> {row['Fit']}<br/><b>Coordinates:</b> {row.geometry.y}, {row.geometry.x}]]>"
            else:
                description = f"<![CDATA[<b>Uncertainty:</b> {row['Uncertainty']}<br/>{row.geometry.y}, {row.geometry.x}]]>"

            kml_content += f"""<Placemark>
                    <name>{idx}</name>
                    <description>{description}</description>
                    <Point><coordinates>{coords}</coordinates></Point>
                </Placemark>\n"""
        kml_content += "</Folder>\n</Document>\n</kml>"

    elif "zssa_proposed_" in str(fn):

        kml_content += "<Folder>\n"
        name = [col for col in gdf.columns if "proposed" in col][0]
        for idx, row in gdf.iterrows():
            coords = f"{row.x},{row.y}"
            description = f"""<![CDATA[<b>{name}:</b> {row[name]}<br/><b>Coordinates:</b> {row.y}, {row.x}]]>"""

            kml_content += f"""<Placemark>
                    <name>{idx}</name>
                    <description>{description}</description>
                    <Point><coordinates>{coords}</coordinates></Point>
                </Placemark>\n"""
        kml_content += "</Folder>\n</Document>\n</kml>"

    with open(fn, "w") as f:
        f.write(kml_content)


def save_artifacts_zip(
    zip_name: str,
    csv_artifacts: dict | None = None,
    gpkg_artifacts: dict | None = None,
    kml_artifacts: dict | None = None,
    raster_artifacts: dict | None = None,
    figure_artifacts: dict | None = None,
) -> Path:
    """Save dataframe/raster/figure artifacts to a single zip in Downloads."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        if csv_artifacts:
            for filename, dataframe in csv_artifacts.items():
                dataframe.to_csv(temp_path / filename, index=False)

        if raster_artifacts:
            for filename, raster in raster_artifacts.items():
                raster.rio.to_raster(temp_path / filename)

        if gpkg_artifacts:
            for filename, gpkg in gpkg_artifacts.items():
                gpkg.to_file(temp_path / filename, driver="GPKG")

        if kml_artifacts:
            for filename, kml in kml_artifacts.items():
                write_kml(kml, temp_path / filename)

        if figure_artifacts:
            for filename, figure in figure_artifacts.items():
                figure.savefig(temp_path / filename, dpi=150, bbox_inches="tight")

        zip_path = get_downloads_folder() / zip_name
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in [
                *(csv_artifacts.keys() if csv_artifacts else []),
                *(raster_artifacts.keys() if raster_artifacts else []),
                *(gpkg_artifacts.keys() if gpkg_artifacts else []),
                *(kml_artifacts.keys() if kml_artifacts else []),
                *(figure_artifacts.keys() if figure_artifacts else []),
            ]:
                zf.write(temp_path / filename, arcname=filename)

    return zip_path
