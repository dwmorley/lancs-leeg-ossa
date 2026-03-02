# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

shiny_datas, shiny_binaries, shiny_hiddenimports = collect_all("shiny")
faicons_datas, faicons_binaries, faicons_hiddenimports = collect_all("faicons")
matplotlib_datas, matplotlib_binaries, matplotlib_hiddenimports = collect_all("matplotlib")
folium_datas, folium_binaries, folium_hiddenimports = collect_all("folium")
ipyleaflet_datas, ipyleaflet_binaries, ipyleaflet_hiddenimports = collect_all("ipyleaflet")
rasterio_datas, rasterio_binaries, rasterio_hiddenimports = collect_all("rasterio")
rioxarray_datas, rioxarray_binaries, rioxarray_hiddenimports = collect_all("rioxarray")
xarray_datas, xarray_binaries, xarray_hiddenimports = collect_all("xarray")
pandas_datas, pandas_binaries, pandas_hiddenimports = collect_all("pandas")
scipy_datas, scipy_binaries, scipy_hiddenimports = collect_all("scipy")
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all("PIL")

# Try to find GDAL/PROJ data directories from installed packages
# This helps with rasterio/rioxarray on macOS
try:
    import rasterio
    import os.path as osp
    rasterio_path = osp.dirname(rasterio.__file__)
    gdal_data_candidates = [
        osp.join(rasterio_path, 'gdal_data'),
        osp.join(osp.dirname(rasterio_path), 'osgeo_data'),
    ]
except ImportError:
    gdal_data_candidates = []

# Get absolute paths for data directories
# This spec is run from the project root directory
root_dir = os.path.abspath(os.path.curdir)
www_dir = os.path.join(root_dir, "www")
static_dir = os.path.join(root_dir, "static")

# Add directories only if they exist
datas = (
    shiny_datas
    + faicons_datas
    + matplotlib_datas
    + folium_datas
    + ipyleaflet_datas
    + rasterio_datas
    + rioxarray_datas
    + xarray_datas
    + pandas_datas
    + scipy_datas
    + numpy_datas
    + pillow_datas
)
if os.path.exists(www_dir):
    datas.append((www_dir, "www"))
if os.path.exists(static_dir):
    datas.append((static_dir, "static"))

binaries = (
    shiny_binaries
    + faicons_binaries
    + matplotlib_binaries
    + folium_binaries
    + ipyleaflet_binaries
    + rasterio_binaries
    + rioxarray_binaries
    + xarray_binaries
    + pandas_binaries
    + scipy_binaries
    + numpy_binaries
    + pillow_binaries
)

hiddenimports = (
    shiny_hiddenimports
    + faicons_hiddenimports
    + matplotlib_hiddenimports
    + folium_hiddenimports
    + ipyleaflet_hiddenimports
    + rasterio_hiddenimports
    + rioxarray_hiddenimports
    + xarray_hiddenimports
    + pandas_hiddenimports
    + scipy_hiddenimports
    + numpy_hiddenimports
    + pillow_hiddenimports
    + [
        "rasterio.sample",
        "rasterio._io",
        "rasterio.dtypes",
        "rasterio.shutil",
        "rasterio.vrt",
        "rasterio.compat",
        "rasterio.crs",
        "rasterio.features",
        "scipy.optimize",
        "scipy.spatial",
        "scipy.stats",
        "scipy.linalg",
    ]
)



a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="lancs-leeg-ossa",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
