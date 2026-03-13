"""Routines for the LCP sampling design. Translated from Luigi's original R code."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial.distance import pdist, squareform


def lcp(map, delta, zeta, total=30, grid=0.7):
    """Generate LCP sampling sites from an ecological classification map.

    Generate a sampling design combining grid and inhibitory (closed-pair)
    samples stratified by class from a raster-like classification map.

    Parameters
    ----------
    map : xarray.DataArray
        Raster-like DataArray containing class IDs (no-data assumed NaN).
    delta : float
        Minimum separation distance for inhibitory points (metres or CRS units).
    zeta : float
        Maximum distance used when creating closed pairs (metres or CRS units).
    total : int, optional
        Target total number of sample points (default is 30).
    grid : float or int, optional
        Fraction or number of grid points to include in the design (default is 0.7).

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ['x', 'y', 'class', 'type'] where 'type' is
        'G' for grid points and 'I' for inhibitory points.
    """
    np.random.seed(1234)
    grid2 = grid
    grid = round(total * grid)

    vv = map.values.flatten()
    xx = np.sort(np.unique(vv[~np.isnan(vv)]))
    n_valid = np.sum(~np.isnan(vv))

    counts = np.array([np.sum(vv == val) for val in xx])
    g = np.round((counts / n_valid) * (total - grid)).astype(int)
    v = np.round((counts / n_valid) * total).astype(int)

    yy = np.where(v == 0)[0]
    if len(yy) > 0:
        total2 = total - len(yy)
        grid = round(total2 * grid2)
        g = np.round((counts / n_valid) * (total2 - grid)).astype(int)
        v[yy] = 1

    # Sampling from each strata
    if np.sum(v) > total:
        v[np.argmax(v)] = np.max(v) - 1

    y_coords, x_coords = map.coords[map.dims[0]], map.coords[map.dims[1]]
    x_min, x_max = float(x_coords.min()), float(x_coords.max())
    y_min, y_max = float(y_coords.min()), float(y_coords.max())

    n_grid = int(np.sum(v - g))
    n_side = int(np.ceil(np.sqrt(n_grid)))
    x_grid = np.linspace(x_min, x_max, n_side)
    y_grid = np.linspace(y_min, y_max, n_side)
    xg, yg = np.meshgrid(x_grid, y_grid)
    grid_pts = np.column_stack([xg.ravel(), yg.ravel()])[:n_grid]

    classes = map.sel(
        x=xr.DataArray(grid_pts[:, 0], dims="points"),
        y=xr.DataArray(grid_pts[:, 1], dims="points"),
        method="nearest",
    ).values

    dataframe = pd.DataFrame({"x": grid_pts[:, 0], "y": grid_pts[:, 1], "class": classes})
    dataframe = dataframe.dropna()

    t = np.array([np.sum(dataframe["class"] == val) for val in xx])  # Obtained from grid
    b = v - t  # Still needed

    for i, val in enumerate(xx):
        if b[i] < g[i]:
            bb = g[i] - b[i]
            if bb >= 1:
                idx = dataframe[dataframe["class"] == val].index
                drop_idx = np.random.choice(idx, int(bb), replace=False)
                dataframe = dataframe.drop(drop_idx)

    t = np.array([np.sum(dataframe["class"] == val) for val in xx])  # Corrected
    v = v - t  # still needed after correction

    dataframe2_list = []
    for _, row in dataframe.iterrows():
        x_range = np.arange(row["x"] + delta, row["x"] + zeta - delta + delta, delta)
        y_range = np.arange(row["y"] + delta, row["y"] + zeta - delta + delta, delta)
        xg, yg = np.meshgrid(x_range, y_range)
        dataframe2_list.append(np.column_stack([xg.ravel(), yg.ravel()]))

    dataframe2 = np.vstack(dataframe2_list) if dataframe2_list else np.empty((0, 2))

    if len(dataframe2) > 0:
        dists = squareform(pdist(dataframe2))
        mask = np.triu(dists <= delta, k=1)
        remove_idx = np.unique(np.where(mask)[1])
        dataframe2 = np.delete(dataframe2, remove_idx, axis=0)

    if len(dataframe2) > 0:
        classes2 = map.interp(
            x=xr.DataArray(dataframe2[:, 0], dims="points"),
            y=xr.DataArray(dataframe2[:, 1], dims="points"),
            method="nearest",
        ).values
        dataframe2 = pd.DataFrame({"x": dataframe2[:, 0], "y": dataframe2[:, 1], "v": classes2})
    else:
        dataframe2 = pd.DataFrame(columns=["x", "y", "v"])

    bb = []
    for i, val in enumerate(xx):
        if v[i] > 0:
            x_idx = dataframe2[dataframe2["v"] == val].index.tolist()
            if len(x_idx) == 0:
                y_idx, x_idx2 = np.where(map.values == val)
                n_pts = min(int(v[i]), len(y_idx))
                sample_idx = np.random.choice(len(y_idx), n_pts, replace=False)
                pts = np.column_stack(
                    [
                        x_coords.values[x_idx2[sample_idx]],
                        y_coords.values[y_idx[sample_idx]],
                        [val] * n_pts,
                    ]
                )
                bb.append(pts)
            else:
                sample_idx = np.random.choice(x_idx, min(int(v[i]), len(x_idx)), replace=False)
                bb.append(dataframe2.loc[sample_idx, ["x", "y", "v"]].values)

    bb = np.vstack(bb) if bb else np.empty((0, 3))
    bb = pd.DataFrame(bb, columns=["x", "y", "class"])

    final = pd.concat([dataframe, bb], ignore_index=True)
    final["type"] = ["G"] * len(dataframe) + ["I"] * len(bb)

    return final


def plot_lcp(map_raster: xr.DataArray, sites: pd.DataFrame, n_classes: int) -> None:
    """Plot an ecological classification raster and overlay sampling sites.

    Parameters
    ----------
    map_raster : xarray.DataArray
        Raster of class IDs used as the background.
    sites : pandas.DataFrame
        DataFrame produced by :func:`lcp` containing columns ['x', 'y', 'class', 'type'].
    n_classes : int
        Number of distinct classes (used to set the colormap).

    Returns
    -------
    None
        Displays the plot using matplotlib and returns None.
    """
    cmap = plt.get_cmap("tab20", n_classes)
    fig, ax = plt.subplots(figsize=(6, 6))
    map_raster.plot(ax=ax, cmap=cmap, cbar_kwargs={"label": "Class ID"})

    sites_G = sites[sites["type"] == "G"]
    sites_I = sites[sites["type"] == "I"]
    ax.scatter(
        sites_G["x"],
        sites_G["y"],
        marker="o",
        color="blue",
        s=50,
        label="Grid (G)",
        zorder=5,
        edgecolors="black",
        linewidth=0.5,
    )
    ax.scatter(
        sites_I["x"],
        sites_I["y"],
        marker="x",
        color="red",
        s=100,
        label="Inhibitory (I)",
        zorder=5,
        linewidth=2,
    )

    ax.set_title("Ecological Classification with Sampling Sites", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=11)
    plt.tight_layout()
    plt.show()
