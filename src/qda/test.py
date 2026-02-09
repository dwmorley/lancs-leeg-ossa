import warnings
from typing import Any
from typing import Dict
from typing import Union

import numpy as np
import pandas as pd
from scipy import linalg

"""
QUESTIONS:
- What is 'test' actually doing? test in not an int but should be a list?
- err2 = 1 - sum(diag(conf2)) ??
- Wilks, is R reporting where the largest drop is actually happening?

TODO:
- Maybe as a class, model.fit()
- Correctly name variables and functions
- 'all' is a strange global

"""


def luqdaloop(
    X: np.ndarray,
    y: np.ndarray,
    grid: np.ndarray,
    prior: Union[np.ndarray, None] = None,
    nn: float = 0.001,
    nx: int = 8,
    test: Union[int, None] = None,
):
    """
    Localised Discriminant Analysis with automatic class splitting and merging.
    (Python translation of R function with same name)

    Parameters:
    -----------
    X : array-like, shape (n_samples, n_features)
        Explanatory variables / feature matrix
    y : array-like, shape (n_samples,)
        Group vector / class labels
    grid : array-like, shape (n_samples, 2)
        Spatial coordinates for each sample (used for local prior calculation)
    prior : array-like, shape (n_samples, n_groups), optional
        Matrix of prior probabilities for each point. If None, will be computed
        using local frequency method (can be time-consuming)
    nn : float, default=0.001
        Distance threshold for "Local frequency prior" neighborhood
        Based on: Cutillo, Localised empirical discriminant analysis
    nx : int, default=8
        Maximum number of classes to explore
    test : int, optional
        Number of samples to hold out per class for validation

    Returns:
    --------
    all : dict
        Dictionary containing results for different numbers of classes:
        - Key 0: 'WilksSummary' - performance metrics across all class counts
        - Keys 2 to nx: results for each number of classes
        - 'ExcludedClusters': groups with rank deficiency (if any)
        - 'NewData': final classification results with spatial coordinates
    """

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
        Xcen = X[y == g[k], :] - gm[k]

        try:
            Q, R = linalg.qr(Xcen / np.sqrt(nk), mode="economic")
            linalg.solve_triangular(R[:p, :], np.eye(p))
        except (linalg.LinAlgError, ValueError):
            print(f"Rank deficiency in group {g[k]}, this group will stay unchanged")
            N2[nkk] = 1
            G2[k] = 1

    #     if test is not None:
    #         L2.append(np.random.choice(nkk, test, replace=False))
    #
    # if test is not None:
    #     test = np.concatenate(L2)

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
    g = np.sort(np.unique(yy))
    ng = len(g)

    print(f"Doing n classes {ng}")

    if np.sum(N2) > 0:
        cluster_keys = [f"{i + int(np.sum(G2))}cluster" for i in range(2, nx + 1)]
        all: Dict[str, Any] = {
            key: None
            for key in ["WilksSummary"] + cluster_keys + ["ExcludedClusters", "NewData"]
        }
        all["ExcludedClusters"] = np.column_stack(
            [grid[N2 == 1, :], X[N2 == 1, :], y[N2 == 1], prior[N2 == 1, :][:, G2 == 1]]
        )
    else:
        cluster_keys = [f"{i}cluster" for i in range(2, nx + 1)]
        all: Dict[str, Any] = {
            key: None for key in ["WilksSummary"] + cluster_keys + ["NewData"]
        }

    # ===== INITIAL LDA =====
    all[f"{ng}cluster"] = ls_da(X=XX, y=yy, prior=prior_cleaned, test=test)
    tb = np.array([np.sum(yy == group) for group in g])

    # ===== SPLITTING PHASE =====
    # Iteratively split the class with the highest misclassification rate
    print("Splitting")
    ng2 = ng
    y2 = yy.copy()
    prior2 = pd.DataFrame(prior_cleaned.copy())
    tb2 = tb.copy()
    g2 = g.copy()
    split = None
    u = "S"

    while split is None:
        u = u + "C"
        a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"])) / tb2
        a = np.argsort(a)[::-1]  # Sort in decreasing order and get indices

        for i in range(ng2):
            half = round(tb2[a[i]] / 2)
            if half > (p * 3):
                # Get indices where y2 equals g2[a[i]], take first 'half' elements
                half_indices = np.where(y2 == g2[a[i]])[0][:half]
                y2[half_indices] = u + str(g2[a[i]])
                prior2[u] = 0
                prior2[u] = prior2.iloc[:, a[i]] / 2
                prior2.iloc[:, a[i]] = prior2.iloc[:, a[i]] / 2
                ng2 = ng2 + 1
                all[f"{ng2}cluster"] = ls_da(
                    X=XX, y=y2, prior=prior2.values, test=test
                )  # CALL TO LSDA
                tb2 = np.append(tb2, len(half_indices))
                tb2[a[i]] = tb2[a[i]] - len(half_indices)
                g2 = np.append(g2, u + str(g2[a[i]]))
                break
            elif i >= ng2 - 1:
                split = 1

        if ng2 >= nx:
            split = 1

        print(f"Doing n classes {ng2}")

    # ===== MERGING PHASE =====
    print("Merging")
    ng2 = ng
    y2 = yy.copy()
    prior2 = prior_cleaned.copy()
    tb2 = tb.copy()
    g2 = g.copy()
    merge = None
    u = "M"

    while merge is None:
        u = u + "C"
        a = (tb2 - np.diag(all[f"{ng2}cluster"]["confusion"].values)) / tb2
        a = np.argsort(a)[::-1]  # Sort in decreasing order and get indices

        # Merge the two classes with the highest error rates
        y2[np.isin(y2, [g2[a[0]], g2[a[1]]])] = f"{u}{g2[a[0]]}.{g2[a[1]]}"

        # Combine prior probabilities
        prior2[:, a[0]] = prior2[:, a[0]] + prior2[:, a[1]]
        prior2 = np.delete(prior2, a[1], axis=1)

        ng2 -= 1
        all[f"{ng2}cluster"] = ls_da(X=XX, y=y2, prior=prior2, test=test)

        # Update tracking variables
        tb2[a[0]] = tb2[a[0]] + tb2[a[1]]
        tb2 = np.delete(tb2, a[1])
        g2[a[0]] = f"{u}{g2[a[0]]}.{g2[a[1]]}"
        g2 = np.delete(g2, a[1])

        if ng2 == 2:
            merge = 1

        print(f"Doing {ng2} classes")

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
    best = best_idx + 2

    if np.sum(N2) == 0:
        print(f"\nBest number of classes found: {best}")
    else:
        print(f"\nBest number of classes found: {best + int(np.sum(G2))})")

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
        cls = N2.copy().astype(object)
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

    return all


def ls_da(
    X: np.ndarray, y: np.ndarray, prior: np.ndarray, test: Union[int, None] = None
) -> dict:
    """
    Linear discriminant analysis with localized priors.

    Performs LDA using QR decomposition and computes classification scores
    based on Mahalanobis distances with local prior probabilities.
    """

    # TODO: Clarify what test iis doing
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
        Q, R = linalg.qr(Xcen / np.sqrt(nk), mode="economic")
        try:
            qx1 = linalg.solve_triangular(R[:p, :], np.eye(p))
            WMqr.append(qx1)
            ldet[k] = 2 * np.sum(np.log(np.abs(np.diag(R))))
        except linalg.LinAlgError:
            raise ValueError(f"Rank deficiency in group {g[k]}")

    # Compute discriminant scores for training set
    Disc = np.zeros((n, ng))
    for k in range(ng):
        # Deviation from group mean
        Xk = np.tile(gm[k], (n, 1))
        dev = (X - Xk) @ WMqr[k]
        # Discriminant function: Mahalanobis distance + log determinant - log prior
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            Disc[:, k] = (
                0.5 * np.sum(dev**2, axis=1) + 0.5 * ldet[k] - np.log(prior[:, k])
            )

    # Convert to probabilities
    Disc = np.exp(-(Disc - np.min(Disc, axis=1, keepdims=True)))
    pred = Disc / np.sum(Disc, axis=1, keepdims=True)
    pred_class = g[np.argmax(pred, axis=1)]

    # Confusion matrix and error rate
    conf = pd.crosstab(y, pred_class, rownames=["original"], colnames=["predicted"])
    err = 1 - np.trace(conf.values)

    # Wilks' Lambda test statistic
    lambda_stat = Wilks_test(X, y)

    # Results dictionary for training set
    res = {
        "WMqr": [wm.copy() for wm in WMqr],
        "gm": [gm.copy() for gm in gm],
        "ldet": ldet.copy(),
        "prior": prior.copy(),
        "scores": Disc.copy(),
        "classification": pred_class.copy(),
        "confusion": conf.copy(),
        "error_rate": err,
        "Wlambda": lambda_stat,
        "Nclasses": pd.Series(y).value_counts().sort_index(),
        "Classes": y.copy(),
    }

    # If validation set exists, compute scores for it
    # if test is not None:
    #     Disc2 = np.zeros((V, ng))
    #     for k in range(ng):
    #         Xk = np.tile(gm[k], (V, 1))
    #         dev = (XV - Xk) @ WMqr[k]
    #         with warnings.catch_warnings():
    #             warnings.filterwarnings("ignore", category=RuntimeWarning)
    #             Disc2[:, k] = (
    #                 0.5 * np.sum(dev**2, axis=1)
    #                 + 0.5 * ldet[k]
    #                 - np.log(priorV[:, k])
    #             )
    #
    #     # Convert to probabilities
    #     Disc2 = np.exp(-(Disc2 - np.min(Disc2, axis=1, keepdims=True)))
    #     pred = Disc2 / np.sum(Disc2, axis=1, keepdims=True)
    #     pred_class2 = g[np.argmax(pred, axis=1)]
    #
    #     # Validation confusion matrix and error rate
    #     conf2 = pd.crosstab(
    #         yV, pred_class2, rownames=["original"], colnames=["predicted"]
    #     )
    #     err2 = 1 - np.trace(conf2.values) / V
    #     lambda2 = Wilks_test(XV, yV)
    #
    #     # Add validation results
    #     res.update(
    #         {
    #             "xscores": Disc2.copy(),
    #             "xclassification": pred_class2.copy(),
    #             "xconfusion": conf2.copy(),
    #             "xerror_rate": err2,
    #             "xWlambda": lambda2,
    #         }
    #     )

    return res


def Wilks_test(X, y):
    """
    Compute Wilks' Lambda statistic for multivariate group differences.

    Wilks' Lambda = |W| / |T| where W is within-group scatter and T is total scatter.
    Values close to 0 indicate strong group separation.
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
        lambda_stat = linalg.det(W) / linalg.det(T)
    except (linalg.LinAlgError, ZeroDivisionError, ValueError):
        lambda_stat = np.nan

    return lambda_stat


# Example usage
if __name__ == "__main__":
    # Generate sample data
    # np.random.seed(42)
    # n_samples = 4900
    # n_features = 6
    #
    # X = np.random.randn(n_samples, n_features)
    # y = np.random.choice(['A', 'B', 'C', 'D'], n_samples)
    # grid = np.random.rand(n_samples, 2)
    #
    # df_grid = pd.DataFrame(grid, columns=['x', 'y'])
    # df_grid.to_csv("grid.csv")
    #
    # df_X = pd.DataFrame(X)
    # df_X.to_csv("X.csv")
    #
    # df_y = pd.DataFrame(y)
    # df_y.to_csv("y.csv")

    X = pd.read_csv("X.csv", index_col=0).values
    y = pd.read_csv("y.csv", index_col=0).values.flatten()
    grid = pd.read_csv("grid.csv", index_col=0).values

    # Run analysis
    results = luqdaloop(X, y, grid)
