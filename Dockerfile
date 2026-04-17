# syntax=docker/dockerfile:1

# ── Base: Ubuntu 22.04 with R and Python 3.11 ──────────────────────────────────
FROM ubuntu:22.04

# ── Prevent apt interactive prompts ──────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ── Install system libraries ──────────────────────────────────────────────────────
# R dependencies
# Geo stack: GDAL, PROJ, GEOS, SpatialIndex (needed by rasterio/geopandas/pyproj/shapely)
# HDF5 + NetCDF (needed by netcdf4/xarray)
# Build tools and Python 3.11 prerequisites
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

# ── Install R 4.1 ──────────────────────────────────────────────────────────────
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E298A3A825C0D65DFD57CBB651716619E084DAB9 && \
    add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu jammy-cran40/" && \
    apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    r-base-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python 3.11 ────────────────────────────────────────────────────────────
# Ubuntu 22.04 has Python 3.11 in the standard repos
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3.11-venv \
    python3-pip python3-setuptools python3-wheel \
    libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default python / python3
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip, setuptools, and wheel
RUN python3.11 -m pip install --upgrade pip setuptools wheel

# ── rpy2 runtime: ensure the R shared library is on the linker path ───────────
# R is installed system-wide in /usr/lib/R
ENV LD_LIBRARY_PATH=/usr/lib/R/lib
ENV R_HOME=/usr/lib/R

# ── Install R packages required by the app ───────────────────────────────────
# Packages used: MBA, MASS, nlme, AICcmodavg, spmodel, sdmTMB, extRemes, fields
# MASS and nlme are included with R base, so only extras are needed here.
# Posit Package Manager serves pre-compiled binaries for Ubuntu 22.04 (Jammy),
# which avoids triggering C++ compilation (e.g. RcppEigen) during docker build
# — critical for fast cross-platform builds on CI.
RUN Rscript -e "\
    options(repos = c(CRAN = 'https://packagemanager.posit.co/cran/__linux__/jammy/latest')); \
    install.packages(c('MBA', 'AICcmodavg', 'spmodel', 'sdmTMB', 'extRemes', 'fields'), dependencies = TRUE)"

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Copy application source ───────────────────────────────────────────────────────
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
