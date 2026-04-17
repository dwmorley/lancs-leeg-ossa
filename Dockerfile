# syntax=docker/dockerfile:1

# ──────────────────────────────────────────────────────────────────────────────
# BUILDER STAGE: Compiles all Python packages and R packages
# ──────────────────────────────────────────────────────────────────────────────
FROM ubuntu:22.04 as builder

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Consolidate all system library installations in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    software-properties-common \
    wget ca-certificates gnupg2 \
    python3.11 python3.11-dev python3.11-venv \
    python3-pip python3-setuptools python3-wheel \
    libcurl4-openssl-dev libssl-dev libxml2-dev libffi-dev \
    libgdal-dev libproj-dev libgeos-dev libspatialindex-dev \
    libhdf5-dev libnetcdf-dev libudunits2-dev \
    libbz2-dev liblzma-dev zlib1g-dev libdeflate-dev libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R 4.1 (builder needs r-base-dev for compilation)
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E298A3A825C0D65DFD57CBB651716619E084DAB9 && \
    add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu jammy-cran40/" && \
    apt-get update && apt-get install -y --no-install-recommends \
    r-base r-base-dev \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip and build tools
RUN python3.11 -m pip install --upgrade --no-cache-dir pip setuptools wheel

# Create a virtual environment for wheels
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies with optimizations
WORKDIR /tmp
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --no-deps \
    --compile \
    -r requirements.txt

# Install R packages (must be in builder stage since sdmTMB needs compilation)
ENV LD_LIBRARY_PATH=/usr/lib/R/lib
ENV R_HOME=/usr/lib/R
RUN Rscript -e "\
    options(repos = c(CRAN = 'https://cran.r-project.org')); \
    install.packages(c('remotes', 'MBA', 'AICcmodavg', 'spmodel', 'extRemes', 'fields'), dependencies = TRUE); \
    remotes::install_github('pbs-assess/sdmTMB@v0.6.0', dependencies = TRUE, upgrade = 'never')"

# ──────────────────────────────────────────────────────────────────────────────
# FINAL STAGE: Minimal runtime image
# ──────────────────────────────────────────────────────────────────────────────
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install runtime dependencies matching builder stage
# (Same packages but without -dev flag where possible, but include dev libs for runtime)
# Note: Keeping full dev packages here is fine since we're removing build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    software-properties-common gnupg2 wget ca-certificates \
    libcurl4-openssl-dev libssl-dev libxml2-dev \
    libgdal-dev libproj-dev libgeos-dev libspatialindex-dev \
    libhdf5-dev libnetcdf-dev libudunits2-dev \
    libdeflate-dev libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R runtime
RUN apt-get update && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E298A3A825C0D65DFD57CBB651716619E084DAB9 && \
    add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu jammy-cran40/" && \
    apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-compiled R packages from builder
COPY --from=builder /usr/local/lib/R /usr/local/lib/R
COPY --from=builder /usr/lib/R/library /usr/lib/R/library

# rpy2 runtime configuration
ENV LD_LIBRARY_PATH=/usr/lib/R/lib
ENV R_HOME=/usr/lib/R

# Set up application
WORKDIR /app
COPY . .

# Create runtime directories
RUN mkdir -p /data /app/output

# Non-root user for security
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

# Expose Shiny port
EXPOSE 8000

# Runtime environment
ENV HOST=0.0.0.0
ENV PORT=8000

# Start the app
CMD ["python", "app.py"]
