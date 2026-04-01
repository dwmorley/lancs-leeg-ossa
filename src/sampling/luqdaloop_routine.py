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
    progress=None,
) -> dict | str:
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
    test : int or None, Optional
        Optional indices reserved for testing/validation

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
    or str
        If an error occurs (e.g. invalid input), a descriptive error message

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
        return "nx must be larger than the number of classes in y"

    _step = 0

    def _progress(message):
        nonlocal _step
        if progress is not None:
            progress.set(value=_step, message=message)
        _step += 1

    # Track groups
    N2 = np.zeros(n)
    G2 = np.zeros(ng)
    L2 = []

    # Compute local priors based on neighbours if not provided
    if prior is None:
        prior = np.zeros((n, ng))
        chunk_size = max(1, n // 20)
        mask = np.zeros((n, n), dtype=bool)
        for start in range(0, n, chunk_size):
            end = min(start + chunk_size, n)
            diff = np.abs(grid[start:end, None, :] - grid[None, :, :])
            mask[start:end] = np.all(diff < nn, axis=2)
            _progress(f"Computing neighbourhood matrix ({end}/{n})...")

        for k, group in enumerate(g):
            _progress(f"Computing local priors (class {k + 1}/{ng})...")
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

        if test is not None:
            xx = list(np.random.choice(nkk, size=test, replace=False))
            L2.append(xx)

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
    _progress("Running initial LDA...")
    lda = ls_da(X=XX, y=yy, prior=prior_cleaned, test=test)
    if isinstance(lda, str):
        return lda
    all[f"{ng}cluster"] = lda
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
        try:
            a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"].values)) / tb2
            a = np.argsort(-a)
        except ValueError:
            return "Cannot perform LDA - possibly you have requested too many clusters (nx) for the number of observations in your data"

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

                counts_pd = pd.Series(y2).value_counts()
                print(counts_pd)

                _progress(f"Splitting classes ({ng2}/{nx})...")
                lda = ls_da(X=XX, y=y2, prior=prior2.values, test=test)
                if isinstance(lda, str):
                    return lda
                all[f"{ng2}cluster"] = lda
                tb2 = np.append(tb2, len(half_indices))
                tb2[a[i]] = tb2[a[i]] - len(half_indices)
                g2 = np.append(g2, u + str(g2[a[i]]))
                break
            if i == ng2 - 1:  # Equivalent to i>=ng2 in R's 1-indexed loop
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
        try:
            a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"].values)) / tb2
            a = np.argsort(-a)
        except ValueError:
            return "Cannot perform LDA - possibly you have requested too many clusters (nx) for the number of observations in your data"

        # Merge the two classes with the highest error rates
        y2[np.isin(y2, [g2[a[0]], g2[a[1]]])] = f"{u}{g2[a[0]]}.{g2[a[1]]}"
        prior2[:, a[0]] = prior2[:, a[0]] + prior2[:, a[1]]
        prior2 = np.delete(prior2, a[1], axis=1)
        ng2 -= 1

        counts_pd = pd.Series(y2).value_counts()
        print(counts_pd)

        _progress(f"Merging classes ({ng2})...")
        lda = ls_da(X=XX, y=y2, prior=prior2, test=test)
        if isinstance(lda, str):
            return lda
        all[f"{ng2}cluster"] = lda

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

    # ===== CREATE FINAL OUTPUT =====
    # Combine all data with final classifications

    # TODO: Add the test_indices as in the R code.

    bestdata = np.column_stack([grid, X, y, prior])
    all["NewData"] = pd.DataFrame(bestdata)
    all["NewData"].columns = (
        ["grid1", "grid2"]
        + [f"X{i}" for i in range(p)]
        + ["OriginalClass"]
        + [f"Prior{i}" for i in range(prior.shape[1])]
    )
    for key in [k for k in all if k.endswith("cluster") and k[:-7].isdigit()]:
        if all[key] is not None:
            if np.sum(N2) == 0:
                cls = all[key]["classification"]
            else:
                cls = np.zeros(len(N2)).astype(str)
                cls[N2 == 0] = all[key]["classification"]
                cls[N2 == 1] = y[N2 == 1]
            all["NewData"][key] = cls

    return all


def ls_da(
    X: np.ndarray, y: List[str], prior: np.ndarray, test: Union[int, None] = None
) -> dict | str:
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
        Cross Validation

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
    str
        Error message if LDA cannot be performed
    """
    if test is not None:
        rng = np.random.default_rng()
        test_indices = rng.choice(len(y), size=test, replace=False)
        train_indices = np.setdiff1d(np.arange(len(y)), test_indices)

        XV, yV = X[test_indices], y[test_indices]
        X, y = X[train_indices], y[train_indices]
        priorV = prior[test_indices] if prior is not None else None
        prior = prior[train_indices] if prior is not None else None

        # Compute group means for validation set
        # unique_yV = np.sort(np.unique(y))
        # gmv = [X[y == group].mean(axis=0) for group in unique_yV]
    else:
        XV, yV, priorV = None, None, None
        # gmv = None

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
            return f"Rank deficiency in group for ng = {k + 1}, cannot perform LDA - check nx and your data"

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

    if test is not None:
        ng = len(g)
        Disc2 = np.zeros((test, ng))
        for k in range(ng):
            Xk = np.tile(gm[k], (test, 1))
            dev = (XV - Xk) @ WMqr[k]
            Disc2[:, k] = 0.5 * np.sum(dev**2, axis=1) + 0.5 * ldet[k] - np.log(priorV[:, k])
        Disc2 = np.exp(-(Disc2 - np.min(Disc2, axis=1, keepdims=True)))
        pred = Disc2 / np.sum(Disc2, axis=1, keepdims=True)
        pred_class2 = g[np.argmax(pred, axis=1)]
        conf2 = pd.crosstab(
            pd.Categorical(yV, categories=g), pd.Categorical(pred_class2, categories=g)
        )
        err2 = 1 - np.trace(conf2.values) / np.sum(conf2.values)
        lambda2 = Wilks_test(XV, yV)
    else:
        Disc2, pred_class2, conf2, err2, lambda2 = None, None, None, None, None

    lambda_stat = Wilks_test(X, y)

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

    if test is not None:
        res.update(
            {
                "xscores": Disc2.copy(),
                "xclassification": pred_class2.copy(),
                "xconfusion": conf2.copy(),
                "xerror_rate": err2,
                "xWlambda": lambda2,
            }
        )

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


def make_qda_raster(class_analysis, n_classes: int, round_coords: int = 6) -> xr.DataArray:
    """Convert LUQDA 'NewData' DataFrame into a raster DataArray.

    Parameters
    ----------
    class_analysis : LUQDA output dict
        The dictionary returned by `luqdaloop` containing at least the 'NewData' DataFrame and the key for the best class assignment
    n_classes : int
        The number of classes in the best classification (used to identify the correct column in 'NewData').
    round_coords : int, optional
        Number of decimal places to round coordinates to when building the
        grid. Default is 6.

    Returns
    -------
    xarray.DataArray
        A 2-D DataArray indexed by 'y' and 'x' containing the rasterized
        'id' values.
    """
    best_key = f"{n_classes}cluster"

    new_data = class_analysis["NewData"][["grid1", "grid2", best_key]].rename(
        columns={"grid1": "x", "grid2": "y"}
    )

    unique_classes = new_data[best_key].unique()
    label_to_index = {cls: i for i, cls in enumerate(unique_classes)}
    new_data["id"] = new_data[best_key].map(label_to_index)

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

    df = pd.read_csv("/Users/david/Downloads/ossa_extracted_20260313_103021.csv")
    df = df[df["io_landcoverio"] != 5]

    X = df[
        [
            "cop_dem_30",
            "wp_1km",
            "grip_0_all",
            "sur_refl_b07_avg",
            "500m_16_days_EVI_avg",
            "500m_16_days_EVI_min",
            "500m_16_days_EVI_max",
            "500m_16_days_EVI_sd",
            "500m_16_days_EVI_ampl",
            "terraclimate_def",
            "sg_ocd",
            "ecmwf_potential_evaporation",
            "ecmwf_surface_pressure",
        ]
    ].values
    y = df["io_landcoverio"].values.astype(int)
    grid = df[["longitude", "latitude"]].values

    results = luqdaloop(X, y, grid, nx=8, test=None)

    b = 0
