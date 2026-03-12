"""Localised discriminant analysis utilities. Translated from Luigi's original R code."""

import warnings
from typing import List, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from scipy.linalg import LinAlgError, det, qr, solve_triangular


def luqdaloop(
    X: np.ndarray,
    y: np.ndarray,
    grid: np.ndarray,
    prior: Union[np.ndarray, None] = None,
    nn: float = 0.001,
    nx: int = 8,
    test: Union[int, None] = None,
):
    """Perform localised discriminant analysis with class splitting and merging.

    This function implements a localised discriminant analysis routine that
    mirrors Luigi's original R implementation. It computes local priors (if
    not provided) from spatial neighbours, performs an initial LDA, then
    iteratively attempts to split and merge classes to find an improved
    classification. The function returns a dictionary containing diagnostics
    for each explored number of clusters and a combined `NewData` DataFrame
    with the final class assignment for each observation.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix of shape (n_samples, n_features).
    y : np.ndarray
        Integer class labels for each sample (shape (n_samples,)).
    grid : np.ndarray
        Spatial coordinates array of shape (n_samples, 2) (e.g. longitude,
        latitude) used for local prior computation.
    prior : np.ndarray or None, optional
        Prior probability matrix with shape (n_samples, n_classes). If
        None, local priors are estimated from neighbours in `grid` within
        distance `nn`.
    nn : float, optional
        Neighborhood tolerance (in same units as `grid`) to define local
        neighbourhoods when computing priors. Default 0.001.
    nx : int, optional
        Maximum number of classes to explore when splitting. Must be larger
        than the number of unique classes in `y`.
    test : int or None, optional
        Optional indices reserved for testing/validation (currently
        preserved for API compatibility; internal validation handling is
        commented out in the current implementation).

    Returns
    -------
    dict
        Dictionary containing at least the following keys:
        - 'NewData': pandas.DataFrame containing original data and final
          class assignments (column 'BestClass').
        - 'WilksSummary': pandas.DataFrame summarising Wilks' Lambda and
          error rates for explored cluster counts.
        - '<k>cluster': for each tested cluster count k, a dict returned by
          `ls_da` with diagnostics for that clustering.
        - 'ExcludedClusters' (optional): array with information on any
          rank-deficient clusters that were excluded prior to analysis.

    Raises
    ------
    ValueError
        If `nx` equals the number of unique classes in `y` (must be larger),
        or if other invalid inputs are provided.
    """
    y = y.astype(int)
    n = X.shape[0]
    p = X.shape[1]
    g = np.sort(np.unique(y))
    ng = len(g)

    if nx == ng:
        raise ValueError("nx must be larger than the number of classes in y")

    # Track groups
    N2 = np.zeros(n)
    G2 = np.zeros(ng)
    # L2 = []  # Test indices for each group

    # Compute local priors based on neighbours if not provided
    if prior is None:
        prior = np.zeros((n, ng))
        diff = np.abs(grid[:, None, :] - grid[None, :, :])
        mask = np.all(diff < nn, axis=2)

        for k, group in enumerate(g):
            class_mask = y == group
            neighbor_counts = (mask & class_mask[None, :]).sum(axis=1)
            total_neighbors = mask.sum(axis=1) + ng
            prior[:, k] = (neighbor_counts + 1 - 1) / (total_neighbors - ng)

    # Check for rank deficiency in each group
    gm = [X[y == group].mean(axis=0) for group in g]

    for k in range(ng):
        nkk = np.where(y == g[k])[0]
        nk = len(nkk) - 1
        if nk != 0:
            Xcen = (X[y == g[k], :] - gm[k]) / np.sqrt(nk)
            Q, R = qr(Xcen)
            qx = R
            try:
                np.linalg.solve(qx[:p, :p], np.eye(p))
                success = True
            except np.linalg.LinAlgError:
                success = False
        else:
            success = False

        if not success:
            # print(f"rank deficiency in group {g[k]}, this group will stay unchanged")
            N2[nkk] = 1
            G2[k] = 1

    # Exclude rank-deficient groups
    if np.sum(N2) > 0:
        XX = X[N2 == 0, :]
        yy = y[N2 == 0]
        prior_cleaned = prior[N2 == 0, :][:, G2 == 0]
    else:
        XX = X.copy()
        yy = y.copy()
        prior_cleaned = prior.copy()

    p = XX.shape[1]
    g = np.sort(np.unique(yy.astype(int)))
    ng = len(g)

    if np.sum(N2) > 0:
        cluster_keys = [f"{i + int(np.sum(G2))}cluster" for i in range(2, nx + 1)]
        all = {
            key: None for key in ["WilksSummary"] + cluster_keys + ["ExcludedClusters", "NewData"]
        }
        all["ExcludedClusters"] = np.column_stack(
            [grid[N2 == 1, :], X[N2 == 1, :], y[N2 == 1], prior[N2 == 1, :][:, G2 == 1]]
        )
    else:
        cluster_keys = [f"{i}cluster" for i in range(2, nx + 1)]
        all = {key: None for key in ["WilksSummary"] + cluster_keys + ["NewData"]}

    # ===== INITIAL LDA =====
    all[f"{ng}cluster"] = ls_da(X=XX, y=yy, prior=prior_cleaned, test=test)
    tb = np.array([len(np.where(yy == g[i])[0]) for i in range(ng)])

    # ===== SPLITTING PHASE =====
    # Iteratively split the class with the highest misclassification rate

    yy = yy.copy().astype(str)
    ng2 = ng
    y2 = yy.copy()
    prior2 = pd.DataFrame(prior_cleaned.copy())
    tb2 = tb.copy()
    g2 = g.copy()
    split = False
    u = "S"

    while not split:
        u = u + "C"
        a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"].values)) / tb2
        a = np.argsort(-a)

        for i in range(ng2):
            half = round(tb2[a[i]] / 2)
            if half > (p * 3):
                # Get indices where y2 equals g2[a[i]], take first 'half' elements
                half_indices = np.where(y2 == g2[a[i]].astype(str))[0][:half]
                y2[half_indices] = u + str(g2[a[i]])
                prior2[u] = 0
                prior2[u] = prior2.iloc[:, a[i]] / 2
                prior2.iloc[:, a[i]] = prior2.iloc[:, a[i]] / 2
                ng2 = ng2 + 1

                # counts_pd = pd.Series(y2).value_counts()
                # print(counts_pd)

                all[f"{ng2}cluster"] = ls_da(X=XX, y=y2, prior=prior2.values, test=test)
                tb2 = np.append(tb2, len(half_indices))
                tb2[a[i]] = tb2[a[i]] - len(half_indices)
                g2 = np.append(g2, u + str(g2[a[i]]))
                break
            elif i >= ng2:
                split = True
        if ng2 >= nx:
            split = True

    # ===== MERGING PHASE =====
    ng2 = ng
    y2 = yy.copy()
    prior2 = prior_cleaned.copy()
    tb2 = tb.copy()
    g2 = g.copy().astype(str)
    merge = True if ng2 == 2 else False  # Cannot merge if only 2 classes left (?)
    u = "M"

    while not merge:
        u = u + "C"
        a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"].values)) / tb2
        a = np.argsort(-a)

        # Merge the two classes with the highest error rates
        y2[np.isin(y2, [g2[a[0]], g2[a[1]]])] = f"{u}{g2[a[0]]}.{g2[a[1]]}"
        prior2[:, a[0]] = prior2[:, a[0]] + prior2[:, a[1]]
        prior2 = np.delete(prior2, a[1], axis=1)
        ng2 -= 1

        # counts_pd = pd.Series(y2).value_counts()
        # print(counts_pd)

        all[f"{ng2}cluster"] = ls_da(X=XX, y=y2, prior=prior2, test=test)

        # Update tracking variables
        tb2[a[0]] = tb2[a[0]] + tb2[a[1]]
        tb2 = np.delete(tb2, a[1])
        g2[a[0]] = f"{u}{g2[a[0]]}.{g2[a[1]]}"
        g2 = np.delete(g2, a[1])

        if ng2 == 2:
            merge = True

    # ===== PERFORMANCE SUMMARY =====
    # Create summary matrix of Wilks' Lambda and error rates
    inx = np.zeros((4, nx))
    for i in range(2, nx + 1):
        key = f"{i}cluster"
        if all.get(key) is not None:
            inx[0, i - 1] = all[key]["Wlambda"]
            inx[1, i - 1] = all[key]["error_rate"]

            # if test is not None:
            #     inx[2, i - 1] = all[key].get("xWlambda", np.nan)
            #     inx[3, i - 1] = all[key].get("xerror_rate", np.nan)

    inx_df = pd.DataFrame(
        inx,
        index=["Wilks", "Error", "xWilks", "xError"],
        columns=[str(i) for i in range(1, nx + 1)],
    )
    all["WilksSummary"] = inx_df

    # ===== SELECT BEST NUMBER OF CLASSES =====
    # Choose number of classes that maximizes improvement in Wilks' Lambda
    wilks_values = inx_df.loc["Wilks"].values

    # Calculate differences between sequential values
    wilks_diff = wilks_values[1 : nx - 1] - wilks_values[2:nx]

    # Find index where the biggest change occurs
    best_idx = int(np.argmax(wilks_diff))
    best = best_idx + 3

    # ===== CREATE FINAL OUTPUT =====
    # Combine all data with final classifications
    best_key = f"{best}cluster"
    if np.sum(N2) == 0:
        cls = all[best_key]["classification"]
        bestdata = np.column_stack([grid, X, y, prior, cls])
        all["NewData"] = pd.DataFrame(bestdata)
        all["NewData"].columns = (
            ["grid1", "grid2"]
            + [f"X{i}" for i in range(p)]
            + ["OriginalClass"]
            + [f"Prior{i}" for i in range(prior.shape[1])]
            + ["BestClass"]
        )
    else:
        cls = np.zeros(len(N2)).astype(str)
        cls[N2 == 0] = all[best_key]["classification"]
        cls[N2 == 1] = y[N2 == 1]
        bestdata = np.column_stack([grid, X, y, prior, cls])
        all["NewData"] = pd.DataFrame(bestdata)
        all["NewData"].columns = (
            ["grid1", "grid2"]
            + [f"X{i}" for i in range(p)]
            + ["OriginalClass"]
            + [f"Prior{i}" for i in range(prior.shape[1])]
            + ["BestClass"]
        )

        # counts_pd = pd.Series(all["NewData"]["BestClass"]).value_counts()
        # print(counts_pd)

    return all


def ls_da(X: np.ndarray, y: List[str], prior: np.ndarray, test: Union[int, None] = None) -> dict:
    """Run linear discriminant analysis with localized priors and return results.

    Performs LDA using QR decomposition and returns classification, scores,
    confusion matrix and other diagnostic outputs.

    Parameters
    ----------
    X : np.ndarray
        Feature matrix for the training data (n_samples, n_features).
    y : list-like
        Class labels corresponding to rows of `X`. Labels are treated as
        categorical and should be comparable (strings or integers).
    prior : np.ndarray
        Prior probability matrix with shape (n_samples, n_classes). Each
        row corresponds to sample-specific prior probabilities for each
        class.
    test : int or None, optional
        Reserved test/validation indices (currently not used in the
        computation; kept for API compatibility).

    Returns
    -------
    dict
        Dictionary containing keys including:
        - 'WMqr': list of matrices used for within-group transforms.
        - 'gm': group means.
        - 'ldet': log-determinant values for each group covariance.
        - 'prior': provided prior matrix.
        - 'scores': transformed discriminant scores (unnormalised).
        - 'classification': predicted class labels for each sample.
        - 'confusion': pandas.DataFrame confusion matrix between original
          and predicted classes.
        - 'error_rate': scalar error value (1 - trace(confusion)).
        - 'Wlambda': Wilks' Lambda statistic for the grouping provided.
        - 'Nclasses': pandas.Series counts per class.

    Raises
    ------
    ValueError
        If a group is rank-deficient and the internal linear algebra
        operations fail.
    """
    # Split into train/validation if test indices provided
    # if test is not None:
    #     XV = X[test, :]
    #     X = np.delete(X, test, axis=0)
    #
    #     priorV = prior[test, :]
    #     prior = np.delete(prior, test, axis=0)
    #
    #     V = len(test)
    #
    #     yV = y[test]
    #     y = np.delete(y, test)
    #
    #     # Compute group means for validation set
    #     unique_yV = np.sort(np.unique(yV))
    #     GMV = [XV[yV == g].mean(axis=0) for g in unique_yV]  # noqa: F841

    n = X.shape[0]
    p = X.shape[1]
    g = np.sort(np.unique(y))
    ng = len(g)

    # Compute group means for training set
    gm = [X[y == group].mean(axis=0) for group in g]

    # Compute within-group covariance matrices using QR decomposition
    WMqr = []
    ldet = np.zeros(ng)

    for k in range(ng):
        nk = np.sum(y == g[k]) - 1
        Xcen = X[y == g[k], :] - gm[k]
        Q, R = qr(Xcen / np.sqrt(nk), mode="economic")
        try:
            qx1 = solve_triangular(R[:p, :], np.eye(p))
            WMqr.append(qx1)
            ldet[k] = 2 * np.sum(np.log(np.abs(np.diag(R))))
        except LinAlgError:
            raise ValueError(f"Rank deficiency in group {g[k]}")

    # Compute discriminant scores for training set
    disc = np.zeros((n, ng))
    for k in range(ng):
        # Deviation from group mean
        Xk = np.tile(gm[k], (n, 1))
        dev = (X - Xk) @ WMqr[k]
        # Discriminant function: Mahalanobis distance + log determinant - log prior
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            disc[:, k] = 0.5 * np.sum(dev**2, axis=1) + 0.5 * ldet[k] - np.log(prior[:, k])

    # Convert to probabilities
    disc = np.exp(-(disc - np.min(disc, axis=1, keepdims=True)))
    pred = disc / np.sum(disc, axis=1, keepdims=True)
    pred_class = g[np.argmax(pred, axis=1)]

    # Confusion matrix and error rate
    classes = sorted(set(y) | set(pred_class))
    y_cat = pd.Categorical(y, categories=classes)
    pred_cat = pd.Categorical(pred_class, categories=classes)

    conf = pd.crosstab(y_cat, pred_cat, rownames=["original"], colnames=["predicted"], dropna=False)
    err = 1 - np.trace(conf.values)

    # Wilks' Lambda test statistic
    lambda_stat = Wilks_test(X, y)

    # Results dictionary for training set
    res = {
        "WMqr": [wm.copy() for wm in WMqr],
        "gm": [gm.copy() for gm in gm],
        "ldet": ldet.copy(),
        "prior": prior.copy(),
        "scores": disc.copy(),
        "classification": pred_class.copy(),
        "confusion": conf.copy(),
        "error_rate": err,
        "Wlambda": lambda_stat,
        "Nclasses": pd.Series(y).value_counts().sort_index(),
        "Classes": y.copy(),
    }

    return res


def Wilks_test(X, y):
    """Compute Wilks' Lambda statistic for multivariate group differences.

    Wilks' Lambda is defined as the determinant of the within-group
    scatter matrix divided by the determinant of the total scatter matrix:

        Lambda = |W| / |T|

    where T = total scatter and W = within-group scatter. Smaller values
    indicate greater separation among group means.

    Parameters
    ----------
    X : array-like
        Feature matrix of shape (n_samples, n_features).
    y : array-like
        Group labels corresponding to rows of `X`.

    Returns
    -------
    float
        Wilks' Lambda statistic (or NaN if computation fails due to a
        singular matrix or other numerical issues).
    """
    groups = np.unique(y)
    grand_mean = X.mean(axis=0)

    # Total scatter matrix
    T = (X - grand_mean).T @ (X - grand_mean)

    # Within-group scatter matrix
    W = np.zeros((X.shape[1], X.shape[1]))
    for group in groups:
        X_group = X[y == group]
        group_mean = X_group.mean(axis=0)
        W += (X_group - group_mean).T @ (X_group - group_mean)

    # Wilks' Lambda = |W| / |T|
    try:
        lambda_stat = det(W) / det(T)
    except (LinAlgError, ZeroDivisionError, ValueError):
        lambda_stat = np.nan

    return lambda_stat


def plot_wilks_lambda(wilks: pd.Series, opt_classes: int, deficient_classes: int = 0):
    """Plot Wilks' Lambda summary and highlight the selected class count.

    Parameters
    ----------
    wilks : pandas.Series
        Series of Wilks' Lambda values indexed by the number of classes
        (or with an implicit order matching class counts starting at 2).
    opt_classes : int
        The selected / optimal number of classes to highlight on the plot.
    deficient_classes : int, optional
        Number of rank-deficient classes excluded from the analysis (used
        to annotate the subtitle).

    Returns
    -------
    matplotlib.figure.Figure
        The created figure object (not shown). Caller can save or display
        it as needed.
    """
    # Plot Wilks' Lambda
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(
        np.arange(2, len(wilks) + 2),
        wilks.values,
        marker="o",
        linewidth=2,
        markersize=6,
    )

    subtitle = f"Selected classes (n={opt_classes})"
    if deficient_classes > 0:
        subtitle += f" | Excluded {deficient_classes} rank-deficient classes"

    ax.text(
        0.5,
        -0.12,
        subtitle,
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=10,
    )

    ax.axvline(
        x=opt_classes,
        color="red",
        linestyle="--",
        linewidth=2,
    )
    ax.set_title("Wilks' Lambda", fontsize=14, fontweight="bold")
    ax.set_ylabel("Lambda", fontsize=12)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    # plt.show()
    return fig


def newdata_to_raster(new_data: pd.DataFrame, round_coords: int = 6) -> xr.DataArray:
    """Convert LUQDA 'NewData' DataFrame into a raster DataArray.

    The function expects `new_data` to contain columns 'x', 'y' and 'id'
    (or equivalent column names), where 'id' is the class label or
    integer value to rasterize. Coordinates are rounded to `round_coords`
    decimal places to ensure a regular grid. The resulting xarray
    DataArray uses 'y' and 'x' as dimensions and writes an EPSG:4326 CRS
    on the returned DataArray if the rioxarray accessor is available.

    Parameters
    ----------
    new_data : pandas.DataFrame
        DataFrame with at least columns ['x', 'y', 'id']. Coordinates can
        be numeric strings or floats; they will be cast to float.
    round_coords : int, optional
        Number of decimal places to round coordinates to when building the
        grid. Default is 6.

    Returns
    -------
    xarray.DataArray
        A 2-D DataArray indexed by 'y' and 'x' containing the rasterized
        'id' values.
    """
    df = new_data[["x", "y", "id"]].copy()

    df["x"] = df["x"].astype(float)
    df["y"] = df["y"].astype(float)

    if round_coords is not None:
        df["x"] = df["x"].round(round_coords)
        df["y"] = df["y"].round(round_coords)

    xs = np.sort(df["x"].unique())
    ys = np.sort(df["y"].unique())
    dx = np.diff(xs).min()
    dy = np.diff(ys).min()
    n_x = round((xs.max() - xs.min()) / dx) + 1
    n_y = round((ys.max() - ys.min()) / dy) + 1
    xs_full = np.linspace(xs.min(), xs.max(), n_x).round(round_coords)
    ys_full = np.linspace(ys.min(), ys.max(), n_y).round(round_coords)

    pivoted = df.pivot(index="y", columns="x", values="id")
    pivoted.index = pivoted.index.round(round_coords)
    pivoted.columns = pivoted.columns.round(round_coords)
    pivoted = pivoted.reindex(index=ys_full, columns=xs_full, tolerance=1e-5, method="nearest")

    map_raster = xr.DataArray(
        pivoted.values,
        coords={"y": ys_full, "x": xs_full},
        dims=["y", "x"],
    )
    map_raster = map_raster.rio.write_crs("EPSG:4326")

    return map_raster


if __name__ == "__main__":

    df = pd.read_csv("/Users/david/Downloads/ossa_extracted_20260312_145912.csv")

    X = df[["cop_dem_30", "wp_1km_unadj", "grip_1_highway"]].values
    y = df["esa_ccilc"].values.astype(int)
    grid = df[["longitude", "latitude"]].values

    results = luqdaloop(X, y, grid, nx=8)

    new_data = results["NewData"][["grid1", "grid2", "BestClass"]].rename(
        columns={"grid1": "x", "grid2": "y"}
    )
    rank_deficient = results.get("ExcludedClusters")
    if rank_deficient is not None:
        indx = 2 + X.shape[1]
        n_excluded = len(np.unique(rank_deficient[:, indx]))
    else:
        n_excluded = 0

    unique_classes = new_data["BestClass"].unique()
    n_classes = len(unique_classes) - n_excluded

    wilks = results["WilksSummary"].loc["Wilks"][1::]
    plot_wilks_lambda(wilks, n_classes)
