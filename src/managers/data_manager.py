from shiny import reactive


class DataManager:
    """Holds reactive state for shapes, overlays and extracted dataframe."""

    def __init__(self, reactive_module: reactive):
        self.EXTRACTED_DF = None
        self.my_ossa_layers = reactive_module.Value([])
        self.drawn_shapes = reactive_module.Value([])
        self.updating_from_map = reactive_module.Value(False)

    def set_extracted(self, df):
        self.EXTRACTED_DF = df
