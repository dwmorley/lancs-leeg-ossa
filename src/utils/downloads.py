import os
import platform
import tempfile
import zipfile
from pathlib import Path


def get_downloads_folder():
    """Get the Downloads folder path for the current platform.

    Respects the DOWNLOAD_DIR environment variable when set (e.g. in Docker).
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


def save_artifacts_zip(
    zip_name: str,
    csv_artifacts: dict,
    raster_artifacts: dict,
    figure_artifacts: dict | None = None,
) -> Path:
    """Save dataframe/raster/figure artifacts to a single zip in Downloads."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for filename, dataframe in csv_artifacts.items():
            dataframe.to_csv(temp_path / filename, index=False)

        for filename, raster in raster_artifacts.items():
            raster.rio.to_raster(temp_path / filename)

        if figure_artifacts:
            for filename, figure in figure_artifacts.items():
                figure.savefig(temp_path / filename, dpi=150, bbox_inches="tight")

        zip_path = get_downloads_folder() / zip_name
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in [
                *csv_artifacts.keys(),
                *raster_artifacts.keys(),
                *(figure_artifacts.keys() if figure_artifacts else []),
            ]:
                zf.write(temp_path / filename, arcname=filename)

    return zip_path
