# ADR-0002: Build Strategy for Multi-Arch Image

**Status:** Proposed
**Date:** 2026-06-02
**Decision makers:** Steven Wangen

## Context

We are replacing the upstream `escomp/cesm-lab-neon:latest` base image with a self-maintained, multi-arch (amd64 + arm64) image built on Ubuntu 24.04 (see [ADR-0001](0001-arm64-base-image.md)). This ADR covers how to structure and execute the build.

The upstream image is a 3-layer stack:

| Layer | Contents | Build time concern |
|-------|----------|--------------------|
| base (centos8) | MPICH 3.3.2, HDF5 1.12.0, NetCDF-C 4.7.4, NetCDF-Fortran 4.5.3, PNetCDF 1.12.1 (all compiled from source) | Heavy: ~30-45 min on native, hours under QEMU |
| cesm-2.2 | CESM source checkout + machine configs | Light: git clone + file copies |
| cesm-lab | Miniforge + ~400 conda packages + JupyterLab | Heavy: conda solve + download |

**Update (see [ADR-0004](0004-distributed-computing-support.md)):** The decision to use conda-forge MPICH (instead of hand-compiling) eliminates the source-compilation stage entirely. HDF5, NetCDF-C, NetCDF-Fortran, and PNetCDF can also come from conda-forge. This simplifies the build from a 4-stage multi-stage Dockerfile to a 3-stage one and reduces cold build time from ~45 minutes to ~5-10 minutes.

## Decision Drivers

- Build must produce both `linux/amd64` and `linux/arm64` images
- Fortran/C compilation under QEMU cross-emulation is extremely slow and error-prone
- The conda environment solve is architecture-dependent (different packages/hashes per platform)
- CI should not take hours per push
- Local dev iteration should be fast (change a notebook, rebuild in seconds)

## Options Considered

### Option A: Single Dockerfile, Native Builds on Both Architectures (Recommended)

Use `docker buildx` with QEMU or native runners to build the full image on each architecture. Structure as a **multi-stage Dockerfile** to maximize layer caching:

```
Stage 1 ("base"):  Ubuntu 24.04 + system packages + Miniforge + conda environment
                   (MPICH, HDF5, NetCDF, PNetCDF, scientific Python stack all from conda-forge)
Stage 2 ("cesm"):  FROM base + CESM source checkout + machine configs
Stage 3 ("app"):   FROM cesm + project-specific code (notebooks, analytics_modules, run_neon_v2)
```

Per [ADR-0004](0004-distributed-computing-support.md), all compiled scientific libraries come from conda-forge instead of being hand-compiled. This collapses the original 4-stage plan into 3 stages and eliminates the slowest build step entirely.

**Caching strategy:**
- Stage 1 changes when `environment.yml` or `conda-lock.yml` changes. Use `--mount=type=cache` for conda package cache. This is the heaviest stage but far faster than source compilation (~5 min vs ~45 min).
- Stage 2 changes only when updating CESM version or machine configs.
- Stage 3 changes on every code push. This is the only layer that rebuilds during normal development.

**CI approach:**
- GitHub Actions with `docker/build-push-action` and QEMU for arm64.
- The QEMU overhead is acceptable because Stage 1 (the slow compilation) is cached. Only Stage 4 rebuilds on typical pushes, which is fast on any architecture.
- For the initial build (or when Stage 1 cache is cold), consider using a self-hosted arm64 runner or accepting a one-time slow build.

### Option B: Separate Dockerfiles per Architecture

Maintain two Dockerfiles with architecture-specific tweaks (different package names, URLs, etc.).

**Rejected:** The only architecture-specific difference is the Miniforge installer URL (`Linux-x86_64.sh` vs `Linux-aarch64.sh`), which can be handled with a build arg or `uname -m` detection. Separate Dockerfiles would drift apart over time.

### Option C: Pre-built Base Image Published to GHCR

Build Stage 1-3 as a separate "base" image pushed to GHCR, then have the project Dockerfile `FROM` that base.

**Considered but deferred:** This is a good optimization once the base is stable, but adds CI complexity (two image builds, versioning, cache invalidation). Start with a single Dockerfile and extract the base later if build times become a problem.

## Decision

**Single multi-stage Dockerfile with `docker buildx` for multi-arch builds.**

This keeps the build self-contained and reproducible. The multi-stage structure ensures that day-to-day development (changing notebooks or Python code) only rebuilds the final lightweight stage. The heavy compilation stages are cached and rarely invalidated.

## Implementation Plan

### Phase 1: Base Environment (Ubuntu + Miniforge + conda-forge stack)

Write Stage 1 of the new Dockerfile. Per [ADR-0004](0004-distributed-computing-support.md), all scientific libraries (MPICH, HDF5, NetCDF, PNetCDF) come from conda-forge instead of being hand-compiled:

```dockerfile
FROM ubuntu:24.04 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran cmake m4 wget curl git \
    liblapack-dev libblas-dev graphviz xmlstarlet \
    && rm -rf /var/lib/apt/lists/*

# Install Miniforge (detects architecture automatically)
RUN wget -q "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh" \
    && bash Miniforge3-Linux-$(uname -m).sh -b -p /opt/conda \
    && rm Miniforge3-*.sh

# Install scientific stack from conda-forge (see environment.yml / conda-lock.yml)
COPY conda-lock.yml /tmp/
RUN /opt/conda/bin/conda-lock install --name base /tmp/conda-lock.yml

# Optional: Dask distributed stack (see ADR-0004)
ARG INSTALL_DASK_DISTRIBUTED=false
COPY environment-dask.yml /tmp/
RUN if [ "$INSTALL_DASK_DISTRIBUTED" = "true" ]; then \
      /opt/conda/bin/mamba env update -n base -f /tmp/environment-dask.yml; \
    fi
```

Validate that MPICH, HDF5, NetCDF, and PNetCDF from conda-forge work with CESM's build system by checking library paths in `$CONDA_PREFIX`.

**Estimated effort:** 2-3 days (environment.yml authoring, conda-lock solve, testing on both architectures).

### Phase 2: CESM Integration

Write Stage 2: clone CESM, run `checkout_externals`, install machine configs.

Port the upstream `config_machines.xml` and `config_compilers.xml`. The `container` machine definition must be updated to point to conda library paths (`$CONDA_PREFIX/lib`, `$CONDA_PREFIX/include`) instead of `/usr/local`. Compiler settings (GNU gfortran/gcc/g++) remain the same.

**Estimated effort:** 1-2 days (mostly testing that CESM's `case.build` succeeds with conda-forge libraries).

### Phase 3: Project Layer + CI

Write Stage 3: copy project code (same as current Dockerfile). Update `.github/workflows/docker-publish.yml` to build multi-arch with `platforms: linux/amd64,linux/arm64`.

**Estimated effort:** 1 day.

### Phase 4: Validation

Run all project notebooks end-to-end on both architectures. Compare outputs (especially CESM model runs) to verify numerical correctness.

**Estimated effort:** 2-3 days.

## Consequences

- The project takes ownership of the full image stack instead of depending on an unmaintained upstream base.
- Cold build times drop significantly (~5-10 min vs ~45 min) since all scientific libraries come from conda-forge binaries instead of source compilation.
- Day-to-day rebuilds (notebook/code changes) only touch Stage 3 and remain fast (~seconds).
- The conda environment is modernized (Python 3.12+, JupyterLab 4.x, current package versions), which may surface minor API changes in notebooks.
- Distributed computing support is available via a build arg without maintaining a separate image.
- Total estimated effort: **~1-2 weeks** (reduced from initial estimate due to eliminating source compilation).

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| CESM Fortran code fails to compile on arm64 | Low (confirmed working on Graviton and macOS arm64) | Known fix: add `-llapack` to linker flags if needed |
| CESM build system rejects conda-forge library paths | Low (paths are configured via XML, not hardcoded) | Update `config_machines.xml` to reference `$CONDA_PREFIX`; test early in Phase 2 |
| A conda package lacks arm64 build | Low (all key packages verified available) | Pin to a version that has arm64 support, or use pip fallback |
| Numerical differences between amd64 and arm64 | Medium (floating-point behavior can differ) | Accept small differences; compare CESM output fields within tolerance |
| QEMU-based CI builds are too slow | Low (no source compilation; conda install is fast even under QEMU) | Cache conda packages; consider self-hosted arm64 runner if needed |
