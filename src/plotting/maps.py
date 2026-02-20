import base64
from io import BytesIO

import ipyleaflet as L
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from ipywidgets import HTML
from matplotlib import cm
from matplotlib.colors import BoundaryNorm


def dataarray_to_image_overlay(
    da: xr.DataArray, categorical: bool = True, name: str = "Raster"
) -> L.ImageOverlay:

    data = da.values.astype(float)
    lats = np.array(da.coords.get("y", da.coords.get("lat", da.coords.get("latitude"))))
    lons = np.array(
        da.coords.get("x", da.coords.get("lon", da.coords.get("longitude")))
    )
    lat_res = np.abs(np.diff(lats)).mean() if len(lats) > 1 else 0.01
    lon_res = np.abs(np.diff(lons)).mean() if len(lons) > 1 else 0.01
    bounds = [
        [float(lats.min()) - 0.5 * lat_res, float(lons.min()) - 0.5 * lon_res],
        [float(lats.max()) + 0.5 * lat_res, float(lons.max()) + 0.5 * lon_res],
    ]

    origin = "lower" if lats[0] < lats[-1] else "upper"
    extent = (
        [
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[0][0],
            bounds[1][0],  # lat_min_edge, lat_max_edge
        ]
        if origin == "lower"
        else [
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[1][0],
            bounds[0][0],  # lat_max_edge, lat_min_edge
        ]
    )

    fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
    ax.axis("off")

    if categorical:
        cmap = cm.tab20 if np.unique(data).size <= 20 else cm.viridis

        ax.imshow(
            data, cmap=cmap, origin=origin, extent=extent, interpolation="nearest"
        )
    else:
        vmin, vmax = data.min(), data.max()
        cuts = np.linspace(vmin, vmax, 12)
        cmap = plt.get_cmap("hot")
        norm = BoundaryNorm(cuts, cmap.N)

        ax.imshow(
            data,
            extent=extent,
            origin="lower",
            cmap="hot",
            norm=norm,
        )

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    return L.ImageOverlay(url=url, bounds=bounds, opacity=0.7, name=name)


def make_point_layer(
    df: pd.DataFrame,
    layer_name: str,
) -> L.LayerGroup:

    # Define marker style config for each layer
    marker_config = {
        "LCP Sites": lambda row: dict(
            location=(row.y, row.x),
            radius=8,
            color="green" if getattr(row, "type", None) == "G" else "blue",
            fill=False,
            fill_opacity=0.7,
        ),
        "ASD Sites": lambda row: dict(
            location=(row.y, row.x),
            radius=8,
            color="gray",
            fill=False,
            fill_opacity=0.7,
        ),
    }

    if layer_name not in marker_config:
        raise ValueError(f"Unknown layer name: {layer_name}")

    style_fn = marker_config[layer_name]
    markers = [L.CircleMarker(**style_fn(row)) for row in df.itertuples()]
    return L.LayerGroup(layers=markers, name=layer_name)


def point_layer_legend(name: str) -> HTML:
    if name == "LCP Sites":
        return HTML(
            value="""
            <div style='background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px;'>
                <b>LCP Sites</b><br>
                <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='green' stroke-width='3' fill='none'/></svg> Grid<br>
                <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='blue' stroke-width='3' fill='none'/></svg> Inhibitory<br>
            </div>
            """
        )
    elif name == "ASD Sites":
        return HTML(
            value="""
            <div style='background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px;'>
                <b>ASD Sites</b><br>
                <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='gray' stroke-width='3' fill='none'/></svg> Sample Point<br>
            </div>
            """
        )
    else:
        return HTML(value=f"<div><b>{name}</b></div>")
