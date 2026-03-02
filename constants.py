URLS = {
    "lms": "https://www.lancaster.ac.uk/lms/",
}

GRID_SAMPLE_SIZE = 500


COVARIATE_OPTIONS = {
    "landcover": "Impact Observatory Land Cover",
    "dem": "Elevation",
    "wp_1km_unadj": "World Pop 1km Unadjusted",
    "grip0": "GRIP Road Density - All",
    "grip1": "GRIP Road Density - Highways",
    "grip2": "GRIP Road Density - Primary Roads",
    "grip3": "GRIP Road Density - Secondary Roads",
    "grip4": "GRIP Road Density - Tertiary Roads",
    "grip5": "GRIP Road Density - Local Roads",
    "ET_500m": "MODIS Yearly Evapotranspiration (500m)",
    "LST_Day_1KM": "MODIS Yearly LST Day (1km)",
    "terraclimate_aet": "TerraClimate Actual Evapotranspiration",
    "terraclimate_def": "TerraClimate Water Deficit",
    "terraclimate_pet": "TerraClimate Potential Evapotranspiration",
    "terraclimate_ppt": "TerraClimate Precipitation",
    "terraclimate_q": "TerraClimate Runoff",
    "terraclimate_soil": "TerraClimate Soil Moisture",
    "terraclimate_srad": "TerraClimate Shortwave Radiation",
    "terraclimate_swe": "TerraClimate Snow Water Equivalent",
    "terraclimate_tmax": "TerraClimate Max Temperature",
    "terraclimate_tmin": "TerraClimate Min Temperature",
    "terraclimate_vap": "TerraClimate Vapor Pressure",
    "terraclimate_vpd": "TerraClimate Vapor Pressure Deficit",
    "terraclimate_ws": "TerraClimate Wind Speed",
    "terraclimate_pdsi": "TerraClimate Palmer Drought Severity Index",
}

QDA_OPTIONS = {
    "nx": 8,
    "nn": 0.001,
}

LCP_OPTIONS = {
    "delta": 1.0,
    "zeta": 2.0,
    "total": 30,
    "grid": 0.7,
}

ASD_OPTIONS = {
    "formulaf": "",  # AnGam~Week+Elev+Soil
    "formular": "",  # ~1|LCD
    "target": "H",
    "total": 15,
    "delta": 0.01,
}
