# ADR-0003: Conda Environment Strategy for Multi-Arch Image

**Status:** Proposed
**Date:** 2026-06-02
**Decision makers:** Steven Wangen

## Context

The upstream `escomp/cesm-lab-neon` image contains a conda environment with ~400 packages pinned to exact amd64 build hashes from 2020 (Python 3.7.8, JupyterLab 2.2.8, NumPy 1.19.2, etc.). This environment cannot be reused for an arm64 build because:

1. The pinned build hashes are architecture-specific (linux-64 only).
2. Python 3.7 reached EOL in June 2023.
3. Many pinned versions are 4-6 years old and lack arm64 builds.

We need a strategy for defining and locking the conda environment in the new multi-arch image.

## Decision Drivers

- Must resolve cleanly on both `linux-64` (amd64) and `linux-aarch64` (arm64)
- Must include all packages needed to run project notebooks
- Should be reproducible (same versions across builds)
- Should be maintainable (easy to update, easy to audit)
- Should not carry unnecessary packages from the upstream image

## Options Considered

### Option A: Minimal environment.yml + conda-lock (Recommended)

Create a lean `environment.yml` listing only the packages our notebooks actually import, with loose version constraints (e.g., `xarray >=2024`). Use [conda-lock](https://github.com/conda/conda-lock) to generate per-platform lockfiles (`conda-lock.yml`) that pin exact versions and hashes for both `linux-64` and `linux-aarch64`.

**Pros:**
- Only installs what we use. The upstream image has packages (e.g., `rst2pdf`, `sphinx`, many LaTeX packages, `dask-gateway`) that our project does not need.
- `conda-lock` produces reproducible, cross-platform lockfiles that resolve once and install fast (no solver overhead at build time).
- Loose constraints in `environment.yml` make updates easy: bump the lockfile periodically, review changes.
- The split between "what we want" (`environment.yml`) and "what we got" (`conda-lock.yml`) is clear and auditable.

**Cons:**
- Adds `conda-lock` as a dev dependency for maintaining the lockfile.
- Initial effort to determine the minimal package set from notebook imports.

### Option B: Fully pinned environment.yml per architecture

Maintain two `environment.yml` files (one for linux-64, one for linux-aarch64) with exact version pins but no build hashes.

**Rejected:** Maintaining two files is error-prone and they will drift. `conda-lock` solves this more cleanly.

### Option C: Unpinned environment.yml (floating)

List packages without version constraints and let conda solve fresh on each build.

**Rejected:** Non-reproducible. A build today and a build next week could produce different environments. Conda solve times are also unpredictable and can be very slow.

## Decision

**Use a minimal `environment.yml` with `conda-lock` for cross-platform locking.**

### Minimal Package Set

Based on notebook imports and project requirements, the environment needs:

**Core scientific:**
`python >=3.11`, `numpy`, `scipy`, `pandas`, `xarray`, `netCDF4`, `h5py`

**CESM/Earth science:**
`esmpy`, `cartopy`, `pyproj`, `shapely`, `fiona`, `geopandas`, `rasterio`, `gdal`

**Visualization:**
`matplotlib`, `bokeh`, `holoviews`, `hvplot`, `panel`, `geoviews`, `datashader`, `ipyleaflet`

**Jupyter:**
`jupyterlab >=4`, `ipykernel`, `ipywidgets`, `jupyterhub`

**Dask:**
`dask`, `distributed`

**Project-specific (pip):**
`openai` (used by analytics_modules), `boto3` / `s3fs` (S3 forcing data access)

This is roughly 30-35 direct dependencies vs. ~400 in the upstream image. Transitive dependencies will bring the total higher, but the environment will be significantly leaner.

### Workflow

1. Maintain `environment.yml` in the repo root with loose constraints.
2. Run `conda-lock lock -p linux-64 -p linux-aarch64` to generate `conda-lock.yml`.
3. In the Dockerfile, install from the lockfile: `conda-lock install --name base conda-lock.yml`.
4. Commit both `environment.yml` and `conda-lock.yml` to the repo.
5. To update: edit `environment.yml`, re-run `conda-lock`, review the diff, commit.

## Consequences

- Reproducible builds on both architectures from a single lockfile.
- Significantly smaller image (fewer packages, no LaTeX/Sphinx/docs toolchain).
- Python version jumps from 3.7 to 3.11+. Notebooks may need minor syntax or API updates (e.g., `datetime.utcnow()` deprecation, pandas copy-on-write).
- Package version jumps are large (4-6 years of changes). Some notebook code may need adaptation, particularly around cartopy (API changed significantly between 0.18 and 0.23+) and panel/holoviews.
- The `conda-lock.yml` file will be large but is machine-generated and not meant for human editing.
