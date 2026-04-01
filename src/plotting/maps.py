"""Helpers to render xarray DataArrays and point DataFrames as ipyleaflet map layers."""

import base64
from io import BytesIO
from typing import Literal

import ipyleaflet as L
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from ipywidgets import HTML
from matplotlib.colors import BoundaryNorm


def dataarray_to_image_overlay(
    da: xr.DataArray, categorical: bool = True, name: str = "Raster"
) -> L.ImageOverlay:
    """Render a DataArray as a PNG image and return an ipyleaflet ImageOverlay.

    The function converts the DataArray values to an image (using a
    categorical colour map for discrete values or a continuous colour map
    otherwise), encodes the image in base64 and wraps it in an
    ipyleaflet.ImageOverlay using appropriate spatial bounds derived from
    the DataArray coordinates.

    Parameters
    ----------
    da : xarray.DataArray
        2-D DataArray with coordinates containing latitude-like ('y') and
        longitude-like ('x') values.
    categorical : bool, optional
        If True, use a categorical colormap (tab20) for discrete values;
        otherwise render as a continuous heatmap. Default: True.
    name : str, optional
        Name assigned to the returned ImageOverlay (used as a layer name).

    Returns
    -------
    ipyleaflet.ImageOverlay
        An overlay ready to be added to an ipyleaflet map.
    """
    data = da.values.astype(float)
    lats = np.array(da.coords.get("y", da.coords.get("lat", da.coords.get("latitude"))))
    lons = np.array(da.coords.get("x", da.coords.get("lon", da.coords.get("longitude"))))
    lat_res = np.abs(np.diff(lats)).mean() if len(lats) > 1 else 0.01
    lon_res = np.abs(np.diff(lons)).mean() if len(lons) > 1 else 0.01
    bounds = [
        [float(lats.min()) - 0.5 * lat_res, float(lons.min()) - 0.5 * lon_res],
        [float(lats.max()) + 0.5 * lat_res, float(lons.max()) + 0.5 * lon_res],
    ]

    origin: Literal["lower", "upper"] = "lower" if lats[0] < lats[-1] else "upper"
    extent = (
        (
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[0][0],
            bounds[1][0],  # lat_min_edge, lat_max_edge
        )
        if origin == "lower"
        else (
            bounds[0][1],
            bounds[1][1],  # lon_min_edge, lon_max_edge
            bounds[1][0],
            bounds[0][0],  # lat_max_edge, lat_min_edge
        )
    )

    fig, ax = plt.subplots(figsize=(6, 6), dpi=100)
    ax.axis("off")

    if categorical:
        cmap = plt.get_cmap("tab20") if np.unique(data).size <= 20 else plt.get_cmap("viridis")

        ax.imshow(data, cmap=cmap, origin=origin, extent=extent, interpolation="nearest")
    else:
        vmin, vmax = np.nanmin(data), np.nanmax(data)
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
    """Create an ipyleaflet LayerGroup of circle markers from a DataFrame.

    The function maps a named layer to a small set of marker styling rules
    and returns a LayerGroup containing CircleMarker objects for each row
    in `df`. The row is passed to the style lambda and expected to provide
    attributes `x`, `y` and optionally `type`.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing point rows. The function expects columns named
        'x' and 'y' which are used for marker locations.
    layer_name : str
        Name of the style group to render. Supported values include
        'LCP Sites' and 'ASD Sites'.

    Returns
    -------
    ipyleaflet.LayerGroup
        A LayerGroup containing CircleMarker layers representing the
        input points.
    """
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
        "ZSSA Sites": lambda row: dict(
            location=(row.latitude, row.longitude),
            radius=8,
            color="blue",
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
    """Return an HTML widget to use as a legend for a point layer.

    Parameters
    ----------
    name : str
        The layer name for which to create a legend (e.g. 'LCP Sites',
        'ASD Sites').

    Returns
    -------
    ipywidgets.HTML
        A small HTML widget describing the marker symbology for the
        requested layer.
    """
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
    elif name == "ZSSA Sites":
        return HTML(
            value="""
            <div style='background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px;'>
                <b>ZSSA Sites</b><br>
                  <svg width='18' height='18' style='vertical-align:middle;margin-right:4px;'><circle cx='9' cy='9' r='7' stroke='blue' stroke-width='3' fill='none'/></svg> Proposed<br>
            </div>
            """
        )
    else:
        return HTML(value=f"<div><b>{name}</b></div>")
