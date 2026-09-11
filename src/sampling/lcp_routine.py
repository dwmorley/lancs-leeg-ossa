"""Routines for the LCP sampling design. Faithful Python port of Luigi's R code."""

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial.distance import pdist, squareform


def lcp(map, delta, zeta, total=30, grid=0.7, seed=None, progress=None):
    """Generate LCP sampling sites from an ecological classification map.

    Combines a spatially-regular grid sample with inhibitory close-pair
    samples, stratified by class, from a raster-like classification map.
    This mirrors the R implementation's logic exactly, with its accidental
    bugs fixed rather than translated (see module docstring).

    Parameters
    ----------
    map : xarray.DataArray
        Raster-like DataArray containing class IDs (no-data assumed NaN).
    delta : float
        Minimum separation distance for inhibitory points (CRS units).
    zeta : float
        Maximum distance used when creating close pairs (CRS units).
    total : int, optional
        Target total number of sample points (default 30).
    grid : float, optional
        Proportion of points allocated to the regular grid; the remainder
        (1-grid) is allocated as inhibitory close pairs (default 0.7).
    seed : int, optional
        Random seed, for reproducibility (R used `set.seed(1234)`).
    progress : optional
        Object with a ``set(value, message)`` method for progress reporting.

    Returns
    -------
    pandas.DataFrame
        Columns ['x', 'y', 'class', 'type'], 'type' is 'G' (grid) or 'I'
        (inhibitory).
    """
    if seed is not None:
        np.random.seed(seed)

    def _p(value, message):
        if progress is not None:
            progress.set(value=value, message=message)

    # ---- 1. Stratify classes and compute per-class target counts -------
    _p(0, "Stratifying classes...")
    grid2 = grid
    grid_n = round(total * grid)

    vv = map.values.flatten()
    valid = vv[~np.isnan(vv)]
    xx = np.sort(np.unique(valid))
    n_valid = valid.size

    counts = np.array([np.sum(valid == val) for val in xx], dtype=float)
    props = counts / n_valid

    g = np.round(props * (total - grid_n)).astype(int)
    v = np.round(props * total).astype(int)

    # Under-represented classes get at least 1 point
    yy = np.where(v == 0)[0]
    n_added_underrepresented = 0
    if len(yy) > 0:
        total2 = total - len(yy)
        grid_n = round(total2 * grid2)
        g = np.round(props * (total2 - grid_n)).astype(int)
        v[yy] = 1
        n_added_underrepresented = len(yy)

    # Reconcile sum(v) to total exactly (fixes R's 1-off, ties-buggy version)
    diff = total - int(np.sum(v))
    if diff != 0:
        v[np.argmax(v)] += diff

    # Keep g consistent with the (possibly corrected) v
    g = np.minimum(g, np.maximum(v - 1, 0))

    _p(0.1, "Target counts per stratum computed")

    # ---- 2. Regular grid sample over the valid (non-NaN) area ----------
    _p(0.2, "Building regular grid...")
    y_coords, x_coords = map.coords[map.dims[0]], map.coords[map.dims[1]]
    x_min, x_max = float(x_coords.min()), float(x_coords.max())
    y_min, y_max = float(y_coords.min()), float(y_coords.max())

    n_grid = int(np.sum(v - g))
    valid_fraction = max(n_valid / vv.size, 1e-6)

    grid_pts = np.empty((0, 2))
    n_side = int(np.ceil(np.sqrt(n_grid / valid_fraction))) if n_grid > 0 else 0
    max_tries = 8
    for _try in range(max_tries):
        if n_grid <= 0 or n_side <= 0:
            break
        x_lat = np.linspace(x_min, x_max, n_side)
        y_lat = np.linspace(y_min, y_max, n_side)
        xg, yg = np.meshgrid(x_lat, y_lat)
        lattice = np.column_stack([xg.ravel(), yg.ravel()])

        cls_at_lattice = map.sel(
            x=xr.DataArray(lattice[:, 0], dims="points"),
            y=xr.DataArray(lattice[:, 1], dims="points"),
            method="nearest",
        ).values
        mask = ~np.isnan(cls_at_lattice)
        masked = lattice[mask]

        if len(masked) >= n_grid:
            # Evenly-spaced subset across the whole masked lattice, so
            # coverage stays spread out instead of clustering near one edge.
            idx = np.linspace(0, len(masked) - 1, n_grid).round().astype(int)
            idx = np.unique(idx)
            # linspace+unique can yield slightly fewer than n_grid if
            # len(masked) is small; pad by taking any remaining points.
            if len(idx) < n_grid:
                remaining = np.setdiff1d(np.arange(len(masked)), idx)
                extra = remaining[: n_grid - len(idx)]
                idx = np.concatenate([idx, extra])
            grid_pts = masked[idx[:n_grid]]
            break
        n_side = int(np.ceil(n_side * 1.5)) + 1
    else:
        grid_pts = masked if len(masked) else np.empty((0, 2))

    _p(1, "Sampling grid points...")
    classes = (
        map.sel(
            x=xr.DataArray(grid_pts[:, 0], dims="points"),
            y=xr.DataArray(grid_pts[:, 1], dims="points"),
            method="nearest",
        ).values
        if len(grid_pts)
        else np.empty((0,))
    )

    dataframe = pd.DataFrame(
        {
            "x": grid_pts[:, 0] if len(grid_pts) else [],
            "y": grid_pts[:, 1] if len(grid_pts) else [],
            "class": classes,
        }
    ).dropna()

    # ---- 3. Drop excess grid points where a class is over-supplied -----
    t = np.array([np.sum(dataframe["class"] == val) for val in xx])  # from grid
    b = v - t  # still needed

    for i, val in enumerate(xx):
        if b[i] < g[i]:
            bb = g[i] - b[i]
            if bb >= 1:  # R's evidently-intended condition (dead in R itself)
                idx = dataframe[dataframe["class"] == val].index
                n_drop = min(int(bb), len(idx))
                if n_drop > 0:
                    drop_idx = np.random.choice(idx, n_drop, replace=False)
                    dataframe = dataframe.drop(drop_idx)

    t = np.array([np.sum(dataframe["class"] == val) for val in xx])  # corrected
    v = v - t  # still needed after correction

    # ---- 4. Generate close-pair candidates around each grid point ------
    _p(2, "Generating close pairs...")
    dataframe2_list = []
    for _, row in dataframe.iterrows():
        x_range = np.arange(row["x"] + delta, row["x"] + zeta - delta + delta, delta)
        y_range = np.arange(row["y"] + delta, row["y"] + zeta - delta + delta, delta)
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
        classes2 = map.sel(
            x=xr.DataArray(dataframe2[:, 0], dims="points"),
            y=xr.DataArray(dataframe2[:, 1], dims="points"),
            method="nearest",
        ).values
        valid_idx = ~np.isnan(classes2)
        dataframe2 = pd.DataFrame(
            {"x": dataframe2[valid_idx, 0], "y": dataframe2[valid_idx, 1], "v": classes2[valid_idx]}
        )
    else:
        dataframe2 = pd.DataFrame(columns=["x", "y", "v"])

    # ---- 5. Select inhibitory points per stratum ------------------------
    _p(3, "Selecting inhibitory points...")
    bb = []
    for i, val in enumerate(xx):
        if v[i] > 0:
            x_idx = dataframe2[dataframe2["v"] == val].index.tolist()
            if len(x_idx) == 0:
                y_idx, x_idx2 = np.where(map.values == val)
                n_pts = min(int(v[i]), len(y_idx))
                if n_pts > 0:
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
                n_pts = min(int(v[i]), len(x_idx))
                sample_idx = np.random.choice(x_idx, n_pts, replace=False)
                bb.append(dataframe2.loc[sample_idx, ["x", "y", "v"]].values)

    bb = np.vstack(bb) if bb else np.empty((0, 3))
    bb = pd.DataFrame(bb, columns=["x", "y", "class"])

    # ---- 6. Combine grid + inhibitory points ----------------------------
    final = pd.concat([dataframe, bb], ignore_index=True)
    final["type"] = ["G"] * len(dataframe) + ["I"] * len(bb)

    if n_added_underrepresented > 0:
        _p(
            1.0,
            f"Added inhibitory points to {n_added_underrepresented} under-represented class(es)",
        )

    return final


if __name__ == "__main__":

    x = np.linspace(0, 100, 100)
    y = np.linspace(0, 100, 100)
    xx, yy = np.meshgrid(x, y)
    synthetic_map = xr.DataArray(
        (xx // 20 + yy // 20) % 5, coords={"y": y, "x": x}, dims=["y", "x"]
    )
    sampling_sites = lcp(synthetic_map, delta=5, zeta=15, total=50, grid=0.6, seed=1234)
    counts = sampling_sites["type"].value_counts().sort_index()
    print(counts)
    print(f"Total points: {len(sampling_sites)} (target was 50)")
