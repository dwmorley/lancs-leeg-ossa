# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

shiny_datas, shiny_binaries, shiny_hiddenimports = collect_all("shiny")
faicons_datas, faicons_binaries, faicons_hiddenimports = collect_all("faicons")
matplotlib_datas, matplotlib_binaries, matplotlib_hiddenimports = collect_all("matplotlib")
folium_datas, folium_binaries, folium_hiddenimports = collect_all("folium")

# Get absolute paths for data directories
root_dir = os.path.dirname(os.path.abspath(__file__))
www_dir = os.path.join(root_dir, "www")
static_dir = os.path.join(root_dir, "static")

datas = shiny_datas + faicons_datas + matplotlib_datas + folium_datas + [
    (www_dir, "www"),
    (static_dir, "static"),
]

binaries = shiny_binaries + faicons_binaries + matplotlib_binaries + folium_binaries

hiddenimports = (
    shiny_hiddenimports
    + faicons_hiddenimports
    + matplotlib_hiddenimports
    + folium_hiddenimports
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
