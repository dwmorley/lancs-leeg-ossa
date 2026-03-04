# syntax=docker/dockerfile:1

# ── Base: R 4.4 on Ubuntu 22.04 (rocker already has R compiled with --enable-R-shlib,
#    which rpy2 requires). Python 3.13 is added on top via the deadsnakes PPA.
FROM rocker/r-ver:4.4

# ── Prevent apt interactive prompts ──────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ── Install system libraries ──────────────────────────────────────────────────
# Geo stack: GDAL, PROJ, GEOS, SpatialIndex (needed by rasterio/geopandas/pyproj/shapely)
# HDF5 + NetCDF (needed by netcdf4/xarray)
# Build tools and Python 3.13 prerequisites
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    wget ca-certificates gnupg2 \
    libcurl4-openssl-dev libssl-dev libxml2-dev \
    libgdal-dev libproj-dev libgeos-dev libspatialindex-dev \
    libhdf5-dev libnetcdf-dev \
    libudunits2-dev \
    libbz2-dev liblzma-dev zlib1g-dev \
    libdeflate-dev libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python 3.13 via deadsnakes PPA ────────────────────────────────────
RUN add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.13 python3.13-dev python3.13-venv \
    && rm -rf /var/lib/apt/lists/*

# ── Install pip for Python 3.13 ───────────────────────────────────────────────
RUN wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py \
    && python3.13 /tmp/get-pip.py \
    && rm /tmp/get-pip.py

# Make python3.13 the default python / python3
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1

# ── rpy2 runtime: ensure the R shared library is on the linker path ───────────
# R_HOME is already set by the rocker base image (/usr/local/lib/R).
ENV LD_LIBRARY_PATH=/usr/local/lib/R/lib:${LD_LIBRARY_PATH}

# ── Install R packages required by the app ───────────────────────────────────
# MASS and nlme are included with R base, so only extras are needed here.
RUN Rscript -e "\
    options(repos = c(CRAN = 'https://cloud.r-project.org')); \
    install.packages(c('AICcmodavg', 'MBA'), dependencies = TRUE)"

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY . .

# ── Runtime directories ───────────────────────────────────────────────────────
# /data  → mount point for the user's local drive (read/write)
# output → app output directory (can also be mounted)
RUN mkdir -p /data /app/output

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

# ── Expose Shiny port ─────────────────────────────────────────────────────────
EXPOSE 8000

# ── Start the app ─────────────────────────────────────────────────────────────
ENV HOST=0.0.0.0
ENV PORT=8000
CMD ["python", "app.py"]
