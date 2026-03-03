This file explains how to build and run the project with Docker (macOS zsh).

Build (production image):

```bash
# Build the image (may take several minutes because of geospatial/R deps)
docker build -t lancs-leeg-ossa:latest .

# Run (production, no local mounts)
docker run --rm -p 8000:8000 -e PORT=8000 lancs-leeg-ossa:latest
```

Development with docker-compose (recommended while editing code):

```bash
# Build and run with local volume (fast iteration)
docker compose up --build

# Open the app in the default browser (macOS)
open http://localhost:8000/
```

Troubleshooting notes / gotchas
- This project uses geospatial libraries (GDAL, rasterio, rioxarray, geopandas) and `rpy2` which require system/R runtimes. The Dockerfile uses `micromamba` with conda-forge to install prebuilt binaries and R.
- If you run into import errors for GDAL/rasterio, try pinning versions in `requirements.txt` that match the conda GDAL version, or rebuild the image.
- Image build can be large; consider using a CI cache or smaller base images if size is a concern.

If you want a slimmer Debian-based Dockerfile (apt + pip), or a production-ready multi-stage image, tell me and I will add an alternative Dockerfile optimized for size.
