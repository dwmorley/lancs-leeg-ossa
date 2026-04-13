"""Routines for the LCP sampling design. Translated from Luigi's original R code."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial.distance import pdist, squareform


def lcp(map, delta, zeta, total=30, grid=0.7, progress=None):
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
    progress : optional
        Object with a ``set(value, message)`` method for progress reporting.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ['x', 'y', 'class', 'type'] where 'type' is
        'G' for grid points and 'I' for inhibitory points.
    """

    def _p(value, message):
        if progress is not None:
            progress.set(value=value, message=message)

    grid2 = grid
    grid = round(total * grid)

    _p(0, "Stratifying classes...")
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
    # Correct for rounding errors across strata to ensure exact total
    current_total = np.sum(v)
    if current_total != total:
        diff = total - current_total
        v[np.argmax(v)] += diff

    # Recalculate g proportionally to match corrected v
    current_grid = int(np.sum(g))
    if current_grid > np.sum(v):
        # Adjust g to match the corrected v
        for i in range(len(g)):
            g[i] = min(g[i], v[i] - 1) if v[i] > 0 else 0
    current_grid = int(np.sum(g))
    if current_grid > np.sum(v):
        g[np.argmax(g)] -= current_grid - np.sum(v)

    y_coords, x_coords = map.coords[map.dims[0]], map.coords[map.dims[1]]
    x_min, x_max = float(x_coords.min()), float(x_coords.max())
    y_min, y_max = float(y_coords.min()), float(y_coords.max())

    n_grid = int(np.sum(v - g))
    n_side = int(np.ceil(np.sqrt(n_grid)))
    x_grid = np.linspace(x_min, x_max, n_side)
    y_grid = np.linspace(y_min, y_max, n_side)
    xg, yg = np.meshgrid(x_grid, y_grid)
    grid_pts = np.column_stack([xg.ravel(), yg.ravel()])[:n_grid]

    _p(1, "Sampling grid points...")
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
    _p(2, "Generating close pairs...")
    for _, row in dataframe.iterrows():
        # Generate candidate points, clipping to raster bounds
        x_range = np.arange(row["x"] + delta, row["x"] + zeta - delta + delta, delta)
        y_range = np.arange(row["y"] + delta, row["y"] + zeta - delta + delta, delta)

        # Clip ranges to raster bounds
        x_range = x_range[(x_range >= x_min) & (x_range <= x_max)]
        y_range = y_range[(y_range >= y_min) & (y_range <= y_max)]

        if len(x_range) > 0 and len(y_range) > 0:
            xg, yg = np.meshgrid(x_range, y_range)
            dataframe2_list.append(np.column_stack([xg.ravel(), yg.ravel()]))

    dataframe2 = np.vstack(dataframe2_list) if dataframe2_list else np.empty((0, 2))

    if len(dataframe2) > 0:
        dists = squareform(pdist(dataframe2))
        mask = np.triu(dists <= delta, k=1)
        remove_idx = np.unique(np.where(mask)[1])
        dataframe2 = np.delete(dataframe2, remove_idx, axis=0)

    if len(dataframe2) > 0:
        # Use sel() with method="nearest" instead of interp() to stay within bounds
        # Also filter out any points where the nearest cell is NaN (outside valid data)
        classes2 = map.sel(
            x=xr.DataArray(dataframe2[:, 0], dims="points"),
            y=xr.DataArray(dataframe2[:, 1], dims="points"),
            method="nearest",
        ).values
        # Only keep points that have valid class values (not NaN)
        valid_idx = ~np.isnan(classes2)
        dataframe2 = pd.DataFrame(
            {"x": dataframe2[valid_idx, 0], "y": dataframe2[valid_idx, 1], "v": classes2[valid_idx]}
        )
    else:
        dataframe2 = pd.DataFrame(columns=["x", "y", "v"])

    bb = []
    _p(3, "Selecting inhibitory points...")
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

    # Ensure all points are within raster bounds
    final = final[
        (final["x"] >= x_min)
        & (final["x"] <= x_max)
        & (final["y"] >= y_min)
        & (final["y"] <= y_max)
    ].reset_index(drop=True)

    # Ensure final dataframe has exactly 'total' rows
    current_total = len(final)
    if current_total != total:
        if current_total > total:
            # Remove excess points from inhibitory (I) type, then grid (G) if needed
            excess = current_total - total
            i_indices = final[final["type"] == "I"].index.tolist()
            if len(i_indices) >= excess:
                remove_idx = np.random.choice(i_indices, excess, replace=False)
            else:
                remove_idx = i_indices
                remaining = excess - len(i_indices)
                g_indices = final[final["type"] == "G"].index.tolist()
                remove_idx = list(remove_idx) + list(
                    np.random.choice(g_indices, remaining, replace=False)
                )
            final = final.drop(remove_idx)
        else:
            # Undershoot: need to add more points
            deficit = total - current_total
            # Try to add more inhibitory points from dataframe2
            if len(dataframe2) > 0:
                available_idx = dataframe2.index.tolist()
                # Get indices of points not already in final
                taken_idx = []
                for idx in final[final["type"] == "I"].index:
                    for j, row in dataframe2.iterrows():
                        if final.loc[idx, "x"] == row["x"] and final.loc[idx, "y"] == row["y"]:
                            taken_idx.append(j)
                            break
                available_idx = [i for i in available_idx if i not in taken_idx]

                if len(available_idx) >= deficit:
                    sample_idx = np.random.choice(available_idx, deficit, replace=False)
                    extra_pts = dataframe2.loc[sample_idx, ["x", "y", "v"]].copy()
                    extra_pts.columns = ["x", "y", "class"]
                    extra_pts["type"] = "I"
                    final = pd.concat([final, extra_pts], ignore_index=True)
                else:
                    # Not enough in dataframe2, add remaining from random map locations
                    remaining = deficit - len(available_idx)
                    if len(available_idx) > 0:
                        sample_idx = np.random.choice(
                            available_idx, len(available_idx), replace=False
                        )
                        extra_pts = dataframe2.loc[sample_idx, ["x", "y", "v"]].copy()
                        extra_pts.columns = ["x", "y", "class"]
                        extra_pts["type"] = "I"
                        final = pd.concat([final, extra_pts], ignore_index=True)

                    # Add remaining from map
                    if remaining > 0:
                        y_idx, x_idx_arr = np.where(~np.isnan(map.values))
                        sample_idx = np.random.choice(len(y_idx), remaining, replace=False)
                        extra_rows = []
                        for idx in sample_idx:
                            extra_rows.append(
                                {
                                    "x": x_coords.values[x_idx_arr[idx]],
                                    "y": y_coords.values[y_idx[idx]],
                                    "class": map.values[y_idx[idx], x_idx_arr[idx]],
                                    "type": "I",
                                }
                            )
                        extra_pts = pd.DataFrame(extra_rows)
                        final = pd.concat([final, extra_pts], ignore_index=True)

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


if __name__ == "__main__":

    x = np.linspace(0, 100, 100)
    y = np.linspace(0, 100, 100)
    xx, yy = np.meshgrid(x, y)
    synthetic_map = xr.DataArray(
        (xx // 20 + yy // 20) % 5, coords={"y": y, "x": x}, dims=["y", "x"]
    )
    sampling_sites = lcp(synthetic_map, delta=5, zeta=15, total=50, grid=0.6)
    counts = sampling_sites["type"].value_counts().sort_index()
    print(counts)
    plot_lcp(synthetic_map, sampling_sites, n_classes=5)
