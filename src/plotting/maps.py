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
        An overlay ready to be added to an ipyleaflet map. The overlay
        includes metadata for legend generation in its `_legend_info`
        attribute.
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

    # Store legend metadata
    legend_info = {
        "categorical": categorical,
        "cmap_name": None,
        "vmin": None,
        "vmax": None,
        "cuts": None,
    }

    if categorical:
        cmap = plt.get_cmap("tab20") if np.unique(data).size <= 20 else plt.get_cmap("viridis")
        legend_info["cmap_name"] = "tab20" if np.unique(data).size <= 20 else "viridis"  # type: ignore

        ax.imshow(data, cmap=cmap, origin=origin, extent=extent, interpolation="nearest")
    else:
        vmin, vmax = np.nanmin(data), np.nanmax(data)
        cuts = np.linspace(vmin, vmax, 12)
        cmap = plt.get_cmap("hot")
        norm = BoundaryNorm(cuts, cmap.N)

        legend_info["cmap_name"] = "hot"  # type: ignore
        legend_info["vmin"] = float(vmin)  # type: ignore
        legend_info["vmax"] = float(vmax)  # type: ignore
        legend_info["cuts"] = [float(c) for c in cuts]  # type: ignore

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
    overlay = L.ImageOverlay(url=url, bounds=bounds, opacity=0.7, name=name)
    # Attach legend metadata to the overlay for later use
    overlay._legend_info = legend_info
    return overlay


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
            location=(row.y, row.x),
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


def raster_layer_legend(name: str, legend_info: dict) -> HTML:
    """Return an HTML widget to use as a legend for a raster layer.

    Parameters
    ----------
    name : str
        The name of the raster layer (e.g., 'ASD Hotspot', 'ASD Uncertainty').
    legend_info : dict
        Dictionary containing legend metadata with keys:
        - categorical: bool indicating categorical vs continuous data
        - cmap_name: name of the colormap used
        - vmin: minimum value (for continuous)
        - vmax: maximum value (for continuous)
        - cuts: list of value boundaries (for continuous)

    Returns
    -------
    ipywidgets.HTML
        A small HTML widget showing the color ramp and value scale.
    """
    import matplotlib.pyplot as plt

    categorical = legend_info.get("categorical", False)
    cmap_name = legend_info.get("cmap_name", "viridis")

    try:
        if categorical:
            # For categorical data, show a simple colorbar with the colormap
            cmap = plt.get_cmap(cmap_name)
            html = f"""<div style="background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 12px; width: 150px; box-sizing: border-box;">
    <b>{name}</b><br>
    <span style="font-size: 11px; color: #666;">Categorical Classes</span><br>
    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px; margin-top: 4px;">"""

            for i in range(20):
                c = cmap(i / 19)
                hex_color = "#{:02x}{:02x}{:02x}".format(
                    int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
                )
                html += (
                    f"<div style='width: 20px; height: 20px; background-color: {hex_color};'></div>"
                )

            html += """</div>
</div>"""
        else:
            # For continuous data, show a gradient ramp with value labels
            vmin = legend_info.get("vmin", 0)
            vmax = legend_info.get("vmax", 1)
            cuts = legend_info.get("cuts", [vmin, vmax])

            cmap = plt.get_cmap(cmap_name)

            # Create color ramp HTML with individual color blocks
            num_steps = 50
            gradient_html = ""
            for i in range(num_steps):
                norm_val = i / (num_steps - 1) if num_steps > 1 else 0
                c = cmap(norm_val)
                hex_color = "#{:02x}{:02x}{:02x}".format(
                    int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
                )
                gradient_html += (
                    f"<div style='flex: 1; height: 20px; background-color: {hex_color};'></div>"
                )

            # Format tick labels
            tick_labels = []
            for cut in cuts:
                if cut == int(cut):
                    tick_labels.append(str(int(cut)))
                else:
                    tick_labels.append(f"{cut:.2f}")

            html = f"""<div style="background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 12px; width: 160px; box-sizing: border-box;">
    <b>{name}</b><br>
    <div style="display: flex; margin-top: 4px; margin-bottom: 2px; height: 20px;">
        {gradient_html}
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 10px; color: #666;">
        <span>{tick_labels[0]}</span>
        <span>{tick_labels[-1]}</span>
    </div>
</div>"""

        return HTML(value=html)

    except Exception:
        # Return a fallback legend if something goes wrong
        fallback_html = f"""<div style="background: white; padding: 8px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 12px;">
    <b>{name}</b><br>
    <span style="font-size: 11px; color: #999;">(Legend unavailable)</span>
</div>"""
        return HTML(value=fallback_html)


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
