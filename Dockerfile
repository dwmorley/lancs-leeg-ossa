# Stage 1: build with micromamba (conda-forge) to get compiled geospatial and R packages
FROM mambaorg/micromamba:1.4.0 AS builder

WORKDIR /app

# Copy requirements early for cache
COPY requirements.txt /app/

# Install Python and heavy deps from conda-forge
RUN micromamba install -y -n base -c conda-forge \
    python=3.13 \
    r-base \
    rpy2 \
    gdal \
    rasterio \
    rioxarray \
    xarray \
    geopandas \
    pandas \
    matplotlib \
    folium \
    pyproj \
    shapely \
    netcdf4 \
    dask \
    gunicorn \
    uvicorn \
    && micromamba clean -a -y

# Ensure conda-installed Python/pip are on PATH in the builder stage
ENV PATH=/opt/conda/bin:$PATH

# Upgrade pip and install remaining Python-only requirements using micromamba run
RUN micromamba run -n base pip install --no-cache-dir --upgrade pip setuptools wheel
RUN micromamba run -n base pip install --no-cache-dir -r /app/requirements.txt

# Copy project
COPY . /app
RUN chmod +x /app/scripts/entrypoint.sh || true

# Stage 2: runtime image (use same micromamba base but smaller final image)
FROM mambaorg/micromamba:1.4.0
WORKDIR /app

# Copy installed packages and app from builder
COPY --from=builder /opt/conda /opt/conda
ENV PATH=/opt/conda/bin:$PATH
COPY --from=builder /app /app

EXPOSE 8000
ENV PORT=8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD [""]

# Healthcheck: query /health for fast readiness
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys;\ntry:\n r=urllib.request.urlopen('http://localhost:8000/health');\n code = getattr(r, 'status', None) or r.getcode();\n sys.exit(0 if code==200 else 1)\nexcept Exception:\n sys.exit(1)"
