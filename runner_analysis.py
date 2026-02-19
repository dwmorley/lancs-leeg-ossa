import pandas as pd

from src.sampling.lcp import lcp, plot_lcp
from src.sampling.luqdaloop import plot_wilks_lambda  # noqa: F401
from src.sampling.luqdaloop import luqdaloop, newdata_to_raster


def do_qda(df: pd.DataFrame, nx: int, nn: float):

    X = df.drop(columns=["longitude", "latitude", "landcover"]).values
    y = df["landcover"].values.astype(int).astype(str)
    grid = df[["longitude", "latitude"]].values

    # Do QDA
    class_analysis = luqdaloop(X=X, y=y, grid=grid, nn=nn, nx=nx)

    best_n_classes = class_analysis["NewData"]["BestClass"].nunique()
    new_data = class_analysis["NewData"][["grid1", "grid2", "BestClass"]].rename(
        columns={"grid1": "x", "grid2": "y"}
    )
    unique_classes = new_data["BestClass"].unique()
    n_classes = len(unique_classes)
    new_data["id"] = new_data["BestClass"].map(
        {cls: i + 1 for i, cls in enumerate(sorted(unique_classes))}
    )

    print(f"QDA complete. Found {best_n_classes} classes.")

    # wilks = class_analysis["WilksSummary"].loc["Wilks"][1::]
    # fig = plot_wilks_lambda(wilks, best_n_classes)
    fig = None
    map_raster = newdata_to_raster(new_data)

    # Generate LCP sites
    sites = lcp(map_raster, delta=1.0, zeta=2.0, total=30, grid=0.7)

    # Plot the map_raster with the sites (G and I)
    plot_lcp(
        map_raster=map_raster,
        sites=sites,
        n_classes=n_classes,
    )

    return {
        "new_data": new_data,
        "best_n_classes": best_n_classes,
        "wilks_plot": fig,
        "class_analysis": class_analysis,
        "map_raster": map_raster,
        "lcp_sites": sites,
    }
