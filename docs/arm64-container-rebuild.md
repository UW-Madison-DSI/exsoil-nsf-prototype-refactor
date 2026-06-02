# ARM64 Multi-Arch Container Rebuild

This document explains why and how we rebuilt the project's Docker image to
support both Intel/AMD (amd64) and Apple Silicon/ARM (arm64) processors.

## Background

### What is the container image?

This project runs inside a Docker container: a self-contained environment that
packages the operating system, scientific libraries, CESM climate model, Python
stack, and JupyterLab together. Researchers launch the container and open
JupyterLab in their browser to run analysis notebooks.

### Why did we need to rebuild it?

The original container image (`escomp/cesm-lab-neon`) had three problems:

1. **It only ran on Intel/AMD processors.** Newer Macs use Apple Silicon (M1,
   M2, M3, M4) which is a different processor architecture called ARM64. When
   team members tried to run the container on these Macs, it ran through a
   slow translation layer (QEMU emulation) that caused frequent crashes and
   made the system 2-3x slower. Local development was effectively unusable.

2. **Its operating system was outdated.** The image was built on CentOS 8,
   which lost security support in December 2021.

3. **Its software was 4-6 years old.** Python 3.7 (end-of-life), JupyterLab
   2.x, and hundreds of scientific packages frozen at 2020 versions.

### What did we do?

We rebuilt the entire container from scratch on a modern foundation, producing
an image that runs natively on both Intel/AMD and Apple Silicon machines. The
key decisions are documented in Architecture Decision Records (ADRs) in the
[docs/adr/](adr/) directory.

## Summary of Changes

### New base operating system

We switched from CentOS 8 to **Ubuntu 24.04 LTS**, which is supported through
2029. Ubuntu was chosen because it is the standard base for scientific Python
containers in the Pangeo and Jupyter communities, and it publishes native ARM64
images.

Full evaluation: [ADR-0001](adr/0001-arm64-base-image.md)

### Simplified build process

The original image compiled five scientific libraries (MPICH, HDF5, NetCDF-C,
NetCDF-Fortran, PNetCDF) from source code, a process that took 30-45 minutes.
We replaced this with pre-built packages from **conda-forge**, a community
repository that publishes binaries for both processor architectures. This
reduced build time to about 5 minutes and eliminated a major source of
complexity.

The image now builds in three stages:

| Stage | What it contains | When it rebuilds |
|-------|-----------------|-----------------|
| **1. Base** | Ubuntu + Python + all scientific libraries | Only when dependencies change |
| **2. CESM** | Climate model source code + configuration | Only when CESM version changes |
| **3. App** | Project notebooks, analysis modules, tools | Every code change (seconds) |

Full details: [ADR-0002](adr/0002-arm64-build-strategy.md)

### Leaner Python environment

The original image installed ~400 Python packages, many of which the project
never uses. We trimmed this to ~35 direct dependencies based on what the
notebooks actually import. A tool called `conda-lock` pins the exact versions
for both processor architectures, so builds are reproducible.

Full details: [ADR-0003](adr/0003-conda-environment-strategy.md)

### Optional distributed computing

The original image included a Dask distributed computing stack (for running
parallel computations across multiple machines). Our project does not currently
use this, so it is disabled by default to keep the image smaller. It can be
enabled with a single flag for deployments that need it:

```bash
docker build --build-arg INSTALL_DASK_DISTRIBUTED=true .
```

Full details: [ADR-0004](adr/0004-distributed-computing-support.md)

### Updated CESM version

We updated from CESM 2.2.0 to **CESM 2.2.2**. The older version relied on
Subversion (SVN) to download some components, and GitHub removed SVN support
in January 2024, breaking the build. Version 2.2.2 uses Git for all
components.

## Issues Discovered During Build

Several compatibility issues surfaced during testing:

- **Package naming.** The PNetCDF package on conda-forge is named `libpnetcdf`,
  not `pnetcdf`. This caused the initial build to fail until corrected.

- **Conflicting `six` library.** CESM bundles an old copy of a Python library
  called `six` that conflicted with the modern version installed by conda-forge.
  This broke date/time handling throughout the Python stack. The Dockerfile
  removes these bundled copies so the correct version is used.

- **CESM Python module paths.** The `run_neon_v2` tool imports Python modules
  from non-standard locations within the CESM source tree. The Dockerfile
  configures `PYTHONPATH` to include these locations.

## How To Use

### Running the container locally

```bash
# Build the image (uses your machine's native architecture)
docker build -t exsoil-nsf-prototype .

# Start JupyterLab
docker run --rm -p 8888:8888 --env-file deploy/jupyterhub/.env exsoil-nsf-prototype
```

Then open the URL printed in the terminal (http://127.0.0.1:8888/lab?token=...).

### Updating Python dependencies

1. Edit `environment.yml` to add, remove, or change packages.
2. Regenerate the lockfile:
   ```bash
   conda-lock lock -f environment.yml -p linux-64 -p linux-aarch64 --mamba
   ```
3. Review the changes to `conda-lock.yml`.
4. Commit both files and rebuild the image.

### Enabling Dask distributed computing

```bash
docker build --build-arg INSTALL_DASK_DISTRIBUTED=true -t exsoil-nsf-prototype .
```

This adds: `distributed`, `dask-gateway`, `dask-jobqueue`, `dask-labextension`,
and `mpi4py`.

## Project File Layout

```
environment.yml            Packages the project needs (human-maintained)
conda-lock.yml             Exact pinned versions for both architectures (generated)
environment-dask.yml       Optional Dask packages for distributed computing
Dockerfile                 Three-stage container build definition
requirements.txt           Additional pip-only packages (if needed)

cesm-config/               CESM machine configuration for container builds
  machines/
    config_machines.xml     Defines the "container" machine target
    config_compilers.xml    Compiler and library path settings
    config_inputdata.xml    Where to download CESM input data
  cime_config/
    config_pes.xml          How many processors each component uses
  component_pes/            Per-component processor layouts

docs/
  adr/                      Architecture Decision Records (design rationale)
  arm64-container-rebuild.md   This document
```

## Continuous Integration

The GitHub Actions workflow (`.github/workflows/docker-publish.yml`) builds
images for both Intel/AMD and ARM64 using Docker Buildx. Images are
automatically pushed to the GitHub Container Registry on pushes to `main` and
on version tags.
