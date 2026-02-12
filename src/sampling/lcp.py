"""
Stratified sampling with inhibitory distance constraints.

Translates R function for optimized sampling across strata in a raster map,
combining regular grid sampling with inhibitory close-pair sampling.
"""

from itertools import product

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial.distance import pdist, squareform


def lcp(
    map_data: xr.DataArray,
    delta: float,
    zeta: float,
    total: int = 30,
    grid: float = 0.7,
) -> pd.DataFrame:
    """
    Stratified sampling with inhibitory distance constraints.

    Samples locations from a classified raster map, combining regular grid
    sampling with inhibitory close-pair sampling to achieve spatial coverage
    while respecting minimum distances between samples.

    Parameters
    ----------
    map_data : xr.DataArray
        A classified raster (xarray DataArray) where each pixel value represents
        a strata/class. Should have 'x' and 'y' coordinates.
    delta : float
        Inhibition distance - minimum distance between any two locations in
        the preliminary sample.
    zeta : float
        Radius around existing sampling locations where to allocate close pairs.
        Must be >= delta.
    total : int, default=30
        Total number of locations to be optimized.
    grid : float, default=0.7
        Proportion of locations to allocate via grid sampling (0-1).
        The remaining (1-grid) will be allocated as inhibitory close pairs.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - 'x', 'y': spatial coordinates
        - 'class': class value from the input map
        - 'type': 'G' for grid-sampled, 'I' for inhibitory close-pair sampled
    """
    np.random.seed(1234)

    # Get raster values and coordinates
    values = map_data.values.flatten()
    valid_mask = ~np.isnan(values)
    valid_values = values[valid_mask]

    # Unique classes in the map
    unique_classes = np.sort(np.unique(valid_values[~np.isnan(valid_values)]))
    unique_classes = unique_classes[~np.isnan(unique_classes)]

    # Calculate sampling allocation per stratum
    grid_count = int(np.round(total * grid))
    class_proportions = np.array(
        [np.sum(valid_values == c) / len(valid_values) for c in unique_classes]
    )
    inhibitory_per_class = np.round(class_proportions * (total - grid_count)).astype(
        int
    )
    total_per_class = np.round(class_proportions * total).astype(int)

    # Handle classes with zero allocations
    zero_classes = np.where(total_per_class == 0)[0]
    if len(zero_classes) > 0:
        total -= len(zero_classes)
        grid_count = int(np.round(total * grid))
        non_zero_mask = np.ones(len(class_proportions), dtype=bool)
        non_zero_mask[zero_classes] = False
        inhibitory_per_class = np.round(
            class_proportions[non_zero_mask] * (total - grid_count)
        ).astype(int)
        # Reconstruct the full array with proper sizing
        inhibitory_temp = np.zeros(len(class_proportions), dtype=int)
        inhibitory_temp[non_zero_mask] = inhibitory_per_class
        inhibitory_per_class = inhibitory_temp
        total_per_class[zero_classes] = 1
        n_zero_classes = len(zero_classes)
    else:
        n_zero_classes = 0

    # Adjust if sum exceeds total
    if np.sum(total_per_class) > total:
        max_idx = np.argmax(total_per_class)
        total_per_class[max_idx] -= 1

    print("Sampling from each strata")
    print(total_per_class)

    # Regular grid sampling from all strata
    grid_samples = _regular_grid_sample(
        map_data, sum(total_per_class - inhibitory_per_class)
    )

    # Extract class values for grid samples
    if len(grid_samples) > 0:
        grid_samples["class"] = [
            map_data.sel(x=row["x"], y=row["y"], method="nearest").values.item()
            for _, row in grid_samples.iterrows()
        ]
    else:
        grid_samples["class"] = np.array([], dtype=int)

    # Count grid samples per class
    grid_counts = np.zeros(len(unique_classes), dtype=int)
    for i, c in enumerate(unique_classes):
        grid_counts[i] = np.sum(grid_samples["class"] == c)

    print("Obtained from grid")
    print(grid_counts)

    # Still needed per class
    still_needed = total_per_class - grid_counts
    print("Still needed")
    print(still_needed)
    print("Theoretical for closed-pairs")
    print(inhibitory_per_class)

    # Correct over-sampling from grid
    samples_to_remove = []
    for i, c in enumerate(unique_classes):
        if grid_counts[i] > inhibitory_per_class[i]:
            n_remove = grid_counts[i] - inhibitory_per_class[i]
            class_indices = grid_samples[grid_samples["class"] == c].index
            if len(class_indices) > 0:
                remove_idx = np.random.choice(
                    class_indices, min(n_remove, len(class_indices)), replace=False
                )
                samples_to_remove.extend(remove_idx)

    if samples_to_remove:
        grid_samples = grid_samples.drop(samples_to_remove).reset_index(drop=True)

    # Recalculate after correction
    grid_counts = np.zeros(len(unique_classes), dtype=int)
    for i, c in enumerate(unique_classes):
        grid_counts[i] = np.sum(grid_samples["class"] == c)

    print("Corrected")
    print(grid_counts)

    still_needed = total_per_class - grid_counts
    print("Still needed after correction")
    print(still_needed)

    # Generate candidate close-pair points around grid samples
    candidates = _generate_close_pair_candidates(grid_samples, delta, zeta, map_data)

    # Filter candidates: remove close pairs within delta distance
    if len(candidates) > 1:
        distances = squareform(pdist(candidates[["x", "y"]].values))
        np.fill_diagonal(distances, np.inf)

        remove_indices = set()
        for i in range(len(candidates)):
            if i in remove_indices:
                continue
            too_close = np.where(distances[i, :] <= delta)[0]
            remove_indices.update(too_close[1:])  # Keep first, remove others

        candidates = candidates.drop(list(remove_indices)).reset_index(drop=True)

    # Assign classes to candidates
    candidates["class"] = [
        map_data.sel(x=row["x"], y=row["y"], method="nearest").values.item()
        for _, row in candidates.iterrows()
    ]

    # Sample from candidates to fill remaining needs
    final_samples = []
    for i, c in enumerate(unique_classes):
        if still_needed[i] > 0:
            class_candidates = candidates[candidates["class"] == c]

            if len(class_candidates) >= still_needed[i]:
                # Sample from candidates
                sampled = class_candidates.sample(n=still_needed[i], random_state=None)
                final_samples.append(sampled[["x", "y", "class"]])
            else:
                # Use all candidates, fill rest from map
                if len(class_candidates) > 0:
                    final_samples.append(class_candidates[["x", "y", "class"]])

                remaining = still_needed[i] - len(class_candidates)
                if remaining > 0:
                    # Sample randomly from map
                    class_mask = map_data == c
                    class_cells = np.argwhere(class_mask.values)

                    if len(class_cells) >= remaining:
                        selected_cells = class_cells[
                            np.random.choice(len(class_cells), remaining, replace=False)
                        ]
                    else:
                        selected_cells = class_cells

                    # Convert cell indices to coordinates
                    x_coords = map_data.x.values[selected_cells[:, 1]]
                    y_coords = map_data.y.values[selected_cells[:, 0]]

                    random_samples = pd.DataFrame(
                        {
                            "x": x_coords,
                            "y": y_coords,
                            "class": np.full(len(selected_cells), c),
                        }
                    )
                    final_samples.append(random_samples)

    # Combine grid and close-pair samples
    inhibitory_samples = (
        pd.concat(final_samples, ignore_index=True)
        if final_samples
        else pd.DataFrame(columns=["x", "y", "class"])
    )

    grid_samples["type"] = "G"
    inhibitory_samples["type"] = "I"

    # Combine all samples
    result = pd.concat(
        [
            grid_samples[["x", "y", "class", "type"]],
            inhibitory_samples[["x", "y", "class", "type"]],
        ],
        ignore_index=True,
    )

    # Reorder columns
    result = result[["x", "y", "class", "type"]]

    if n_zero_classes > 0:
        print("Added inhibitory points to under-represented classes")

    return result


def _regular_grid_sample(map_data: xr.DataArray, n_samples: int) -> pd.DataFrame:
    """
    Generate regularly spaced grid samples across the raster.

    Parameters
    ----------
    map_data : xr.DataArray
        Input raster map.
    n_samples : int
        Target number of samples.

    Returns
    -------
    pd.DataFrame
        DataFrame with 'x' and 'y' coordinates.
    """
    # Calculate grid spacing to achieve approximately n_samples
    y_vals = map_data.y.values
    x_vals = map_data.x.values

    n_y = len(y_vals)
    n_x = len(x_vals)
    total_cells = n_x * n_y

    # Spacing factor
    spacing = int(np.sqrt(total_cells / n_samples))
    spacing = max(spacing, 1)

    # Generate grid points
    y_indices = np.arange(0, n_y, spacing)
    x_indices = np.arange(0, n_x, spacing)

    grid_points = []
    for y_idx in y_indices:
        for x_idx in x_indices:
            y_coord = y_vals[y_idx]
            x_coord = x_vals[x_idx]

            # Check if point is valid (not NaN in map)
            val = map_data.sel(x=x_coord, y=y_coord, method="nearest").values
            if not np.isnan(val):
                grid_points.append({"x": float(x_coord), "y": float(y_coord)})

    return pd.DataFrame(grid_points)


def _generate_close_pair_candidates(
    grid_samples: pd.DataFrame,
    delta: float,
    zeta: float,
    map_data: xr.DataArray,
) -> pd.DataFrame:
    """
    Generate candidate close-pair locations around grid sample points.

    Parameters
    ----------
    grid_samples : pd.DataFrame
        DataFrame with 'x' and 'y' columns of grid sample locations.
    delta : float
        Inhibition distance (grid spacing for candidates).
    zeta : float
        Radius around each grid point.
    map_data : xr.DataArray
        Input raster map.

    Returns
    -------
    pd.DataFrame
        DataFrame with 'x' and 'y' coordinates of candidate points.
    """
    candidates = []

    for _, row in grid_samples.iterrows():
        x_center = row["x"]
        y_center = row["y"]

        # Generate grid of points within radius zeta
        x_range = np.arange(
            x_center + delta, x_center + zeta - delta + delta / 2, delta
        )
        y_range = np.arange(
            y_center + delta, y_center + zeta - delta + delta / 2, delta
        )

        for x, y in product(x_range, y_range):
            # Check if point is within map bounds and valid
            try:
                val = map_data.sel(x=x, y=y, method="nearest").values
                if not np.isnan(val):
                    candidates.append({"x": float(x), "y": float(y)})
            except (KeyError, IndexError):
                continue

    return pd.DataFrame(candidates) if candidates else pd.DataFrame(columns=["x", "y"])


# Example usage
if __name__ == "__main__":
    # Example: Create a simple test raster

    # Create sample data
    x = np.arange(0, 10, 0.5)
    y = np.arange(0, 10, 0.5)
    xx, yy = np.meshgrid(x, y)

    # Create classification based on spatial location
    classification = (xx // 3).astype(int) + (yy // 3).astype(int)

    # Create xarray DataArray
    map_da = xr.DataArray(classification, coords={"x": x, "y": y}, dims=["y", "x"])

    # Run sampling
    results = lcp(map_da, delta=1.0, zeta=2.0, total=30, grid=0.7)

    print("\nFinal sampling results:")
    print(results)

    # Optional visualization
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 8))
    plt.imshow(
        classification, extent=(x.min(), x.max(), y.min(), y.max()), origin="lower"
    )
    grid_samples = results[results["type"] == "G"]
    inhibitory_samples = results[results["type"] == "I"]
    plt.scatter(
        grid_samples["x"], grid_samples["y"], marker="+", c="red", s=100, label="Grid"
    )
    plt.scatter(
        inhibitory_samples["x"],
        inhibitory_samples["y"],
        marker="x",
        c="blue",
        s=100,
        label="Inhibitory",
    )
    plt.legend()
    plt.colorbar()
    plt.show()
