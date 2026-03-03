# Building, Testing, and Publishing the OSSA Docker Image

This document collects step-by-step instructions to build and test the Docker image locally, and to publish it automatically with GitHub Actions (two options: GitHub Container Registry (GHCR) — recommended — and Docker Hub).

Use the repository root for commands. The repo already contains a robust `Dockerfile` (micromamba/conda-forge) and a `Dockerfile.slim` (Debian-slim/pip) alternative.

---

## Quick overview / checklist

- [ ] Build & test image locally (fast feedback loop)
- [ ] Run container and verify the app responds (smoke test)
- [ ] Tag image and push manually (optional)
- [ ] Configure GitHub Actions to publish images automatically (GHCR recommended)
- [ ] Provide users with pull/run commands and versioning guidance

---

## 1) Build & test locally

These commands assume you have Docker installed and Docker Desktop running on macOS.

Build the default (recommended) image (micromamba/conda-forge):

```bash
# from the repo root
docker build -t lancs-leeg-ossa:dev .
```

Build the slim alternative (smaller, might need tweaks for geo/R packages):

```bash
docker build -f Dockerfile.slim -t lancs-leeg-ossa:slim .
```

Run the image (production mode — uses gunicorn + uvicorn workers):

```bash
# run detached; container will start gunicorn via entrypoint
docker run --rm -d --name lancs_leeg_test -p 8000:8000 \
  -e PRODUCTION=1 -e PORT=8000 lancs-leeg-ossa:dev
```

Quick smoke test (repo includes `scripts/smoke_test.sh`):

```bash
# from repo root
./scripts/smoke_test.sh localhost 8000
# or a simple curl check
curl -I http://localhost:8000/health
```

Tail logs while debugging:

```bash
docker logs -f --tail 200 lancs_leeg_test
```

Cleanup:

```bash
docker stop lancs_leeg_test
docker rm lancs_leeg_test
```

---

## 2) Manual tagging & pushing (one-off)

Choose a registry and tag your local image accordingly.

### GitHub Container Registry (GHCR) — recommended

```bash
# Tag locally (use your GitHub user/org)
docker tag lancs-leeg-ossa:dev ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:0.1.0

# Authenticate to GHCR (use a personal access token with `write:packages`/`repo` as needed)
docker login ghcr.io

# Push
docker push ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:0.1.0
```

### Docker Hub (alternative)

```bash
docker tag lancs-leeg-ossa:dev yourdockerhubuser/lancs-leeg-ossa:0.1.0
docker login --username yourdockerhubuser
docker push yourdockerhubuser/lancs-leeg-ossa:0.1.0
```

---

## 3) Automatic builds & publishing with GitHub Actions

Two workflows are provided here as examples. Choose GHCR (recommended) or Docker Hub (alternate). Create the corresponding YAML under `.github/workflows/` (I can add it for you if you want).

### A — Publish to GHCR (recommended)

- Advantages: integrates with GitHub, can use `GITHUB_TOKEN` to push, supports publishing on tags/branches.
- Behavior in example: builds and pushes `ghcr.io/OWNER/REPO:latest` and `ghcr.io/OWNER/REPO:${{ github.ref_name }}` (so `v1.0.0` tag becomes `:v1.0.0`).

Create `.github/workflows/publish-ghcr.yml` with the following contents:

```yaml
name: Build and publish to GHCR

on:
  push:
    branches: [ "main" ]
    tags: [ 'v*' ]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v2
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      - name: Login to GHCR
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
          file: ./Dockerfile
```

Notes:
- `ghcr.io/${{ github.repository }}` expands to `ghcr.io/OWNER/REPO`.
- To publish only on tags (recommended for stable images), change `on:` to only listen for `tags: ['v*']`.
- To make GHCR packages public, go to your repo's Packages page or Organization Packages settings and change visibility.


### B — Publish to Docker Hub (alternate)

- Requires two repository secrets: `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (create an access token in Docker Hub settings).

Create `.github/workflows/publish-dockerhub.yml` with the following contents:

```yaml
name: Build and publish to Docker Hub

on:
  push:
    branches: [ "main" ]
    tags: [ 'v*' ]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Buildx
        uses: docker/setup-buildx-action@v2
      - name: Log in to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/lancs-leeg-ossa:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/lancs-leeg-ossa:${{ github.ref_name }}
          file: ./Dockerfile
```

---

## 4) Configure repository secrets (if needed)

- For Docker Hub: set `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` in GitHub repo Settings → Secrets and variables → Actions.
- For GHCR: the `GITHUB_TOKEN` is available automatically to workflows, but ensure `permissions.packages` is set to `write` as shown.

---

## 5) Tagging & releases (recommended workflow)

1. Create a git tag for a release (semantic versioning preferred):

```bash
git tag v1.0.0
git push origin v1.0.0
```

2. The GH Actions workflow (if configured to run on tags) will build and push images tagged `:v1.0.0`.

3. Users can then pull a specific release image:

```bash
docker pull ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:v1.0.0
```

---

## 6) How users run the published image

Examples (GHCR):

```bash
# run latest
docker run --rm -p 8000:8000 -e PRODUCTION=1 ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:latest
open http://localhost:8000/

# run a versioned tag
docker run --rm -p 8000:8000 ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:v1.0.0
```

If you published on Docker Hub, replace the image name with `yourdockerhubuser/lancs-leeg-ossa:TAG`.

---

## 7) Troubleshooting common issues

1. Build fails at `pip install` or package compilation
   - Retry (network may be transient).
   - For geospatial packages (GDAL, rasterio, rioxarray) prefer the micromamba/conda-forge `Dockerfile` (the repo default). If you use `Dockerfile.slim`, you may need to pin compatible versions or add system libs.
   - If you see `rpy2` errors, ensure `r-base` is installed in the image (the micromamba Dockerfile installs it).

2. Container starts but app returns errors (tracebacks / ImportError)
   - `docker logs <container>` and paste relevant traceback. Typical fixes: pin versions, ensure system libs are present, or install packages via conda.

3. Healthcheck failing repeatedly
   - Check `curl -I http://localhost:8000/health` inside and outside the container.
   - Ensure the container's gunicorn is running and bound to 0.0.0.0 (the image entrypoint uses `PRODUCTION=1` to run gunicorn and `app` is an ASGI callable).

4. Docker build timeout / memory issues
   - Increase Docker Desktop memory to at least 6–8 GB if building the large conda-based image.

---

## 8) Best practices & recommendations

- Use the micromamba `Dockerfile` for reproducible builds with geospatial & R packages.
- Use `Dockerfile.slim` only if you accept potential additional troubleshooting for compiled packages; it can produce significantly smaller images.
- Publish stable releases (tagged) and keep `latest` for development snapshots.
- Add a small CI smoke-test job that pulls your new image and runs `./scripts/smoke_test.sh` to verify the deployed container responds.

---

## 9) Want me to add the GitHub Actions workflow to this repo?

If you want I can create the workflow file for GHCR or Docker Hub in `.github/workflows/` (choose which registry and whether to publish on every push to `main` or only on tags/releases). Tell me your preferred registry and publishing trigger and I will add it.

---

## Reference commands (quick paste)

Build: `docker build -t lancs-leeg-ossa:dev .`
Run: `docker run --rm -d -p 8000:8000 -e PRODUCTION=1 lancs-leeg-ossa:dev`
Smoke test: `./scripts/smoke_test.sh localhost 8000`
Push to GHCR (manual): `docker tag ... && docker push ghcr.io/YOUR_GITHUB_USER/lancs-leeg-ossa:0.1.0`


---

If you want, I will add the GHCR workflow file to `.github/workflows/publish-ghcr.yml` now (recommended). Which trigger do you prefer: `on: push to main` (auto-build latest), or `on: push tags only` (publish only for releases)?
