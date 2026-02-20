URLS = {
    "lms": "https://www.lancaster.ac.uk/lms/",
}

EXPORT_RASTER = False
EXPORT_CSV = True

GRID_SAMPLE_SIZE = 500

COVARIATE_OPTIONS = {
    "landcover": "Land Cover",
    "dem": "Elevation",
    "slope": "Slope",
    "ndvi": "NDVI",
    "rainfall": "Rainfall",
    "roands": "Road Distance",
    "setnntlements": "Settlements",
    "rivner_dist": "River Distance",
    "aspenct": "Aspect",
    "curvnature": "Curvature",
    "twnni": "Topographic Wetness Index",
}

QDA_OPTIONS = {
    "nx": 10,
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
