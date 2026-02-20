from runner_analysis import do_asd, do_qda
from runner_extract import run_extraction
from src.plotting.maps import dataarray_to_image_overlay, make_point_layer


class AnalysisManager:
    """Wrapper around the runner functions so server handlers are simpler."""

    def run_extraction(
        self,
        bbox,
        variables,
        date_range,
        sample_size,
        save_stack,
        save_csv,
        progress=None,
    ):
        return run_extraction(
            bbox=bbox,
            variables=variables,
            date_range=date_range,
            sample_size=sample_size,
            save_stack=save_stack,
            save_csv=save_csv,
            progress=progress,
        )

    def run_qda(self, extracted_df, nx, nn):
        return do_qda(extracted_df, nx, nn)

    def run_asd(self):
        return do_asd()

    def run_qda_and_update(self, data_mgr, map_mgr, nx, nn):
        results = do_qda(data_mgr.EXTRACTED_DF, nx, nn)

        map_mgr.draw_control.data = []
        data_mgr.drawn_shapes.set([])
        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(
            map_raster, categorical=True, name="LUQDA Classes"
        )
        lcp_df = results["lcp_sites"]
        points = make_point_layer(lcp_df, layer_name="LCP Sites")
        data_mgr.my_ossa_layers.set([overlay, points])

        return results

    def run_asd_and_update(self, map_mgr, data_mgr, target: str):
        results = do_asd()

        if target == "H":
            plot_title = "ASD Hotspot"
        else:
            plot_title = "ASD Uncertainty"

        map_raster = results["map_raster"]
        overlay = dataarray_to_image_overlay(
            map_raster, categorical=False, name=plot_title
        )
        lcp_df = results["asd_sites"]
        points = make_point_layer(lcp_df, layer_name="ASD Sites")
        data_mgr.my_ossa_layers.set([overlay, points])

        lats = map_raster.coords.get(
            "y", map_raster.coords.get("lat", map_raster.coords.get("latitude"))
        )
        lons = map_raster.coords.get(
            "x", map_raster.coords.get("lon", map_raster.coords.get("longitude"))
        )
        lat_min = float(lats.min())
        lat_max = float(lats.max())
        lon_min = float(lons.min())
        lon_max = float(lons.max())
        map_mgr.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])

        return results
