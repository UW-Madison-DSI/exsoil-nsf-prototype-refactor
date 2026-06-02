# ADR-0001: Base Image for ARM64 Container Rebuild

**Status:** Accepted
**Date:** 2026-06-02
**Decision makers:** Steven Wangen

## Context

The project's Docker image inherits from `escomp/cesm-lab-neon:latest`, which is:

- **amd64-only** (no arm64 manifest on Docker Hub)
- **Built on CentOS 8**, which reached EOL in December 2021
- **Last pushed 3+ years ago**, with pinned Python 3.7 and packages from 2020
- **A 3-layer build** from [ESCOMP/ESCOMP-Containers](https://github.com/ESCOMP/ESCOMP-Containers):
  1. `centos:8` + hand-compiled MPICH 3.3.2, HDF5 1.12.0, NetCDF-C 4.7.4, NetCDF-Fortran 4.5.3, PNetCDF 1.12.1
  2. CESM 2.2 source checkout + custom machine configs
  3. Miniforge (x86_64 binary) + ~400 pinned conda packages + JupyterLab 2.x

Team members on Apple Silicon Macs cannot productively run the container. QEMU emulation causes kernel hangs (especially on cartopy cells) and 2-3x slowdowns. An arm64-native image is needed.

Since the base is both EOL and stale, this is an opportunity to modernize the entire image stack rather than just cross-compile the existing one.

## Decision Drivers

- Must build natively for both `linux/amd64` and `linux/arm64`
- Must support compiling CESM/CTSM Fortran code with gfortran + MPICH
- Must support hand-compiled HDF5, NetCDF-C, NetCDF-Fortran, PNetCDF from source
- Should align with community norms for scientific Python / Jupyter containers
- Should have long-term support (5+ years)
- Should minimize image size where practical

## Options Considered

### Option A: Ubuntu 24.04 LTS (Recommended)

**Pros:**
- Both [Jupyter Docker Stacks](https://github.com/jupyter/docker-stacks) and [Pangeo Docker Images](https://github.com/pangeo-data/pangeo-docker-images) use Ubuntu 24.04 as their base. This is the de facto standard for scientific Jupyter containers.
- Native arm64 manifests on Docker Hub.
- Smallest compressed size (~29 MB).
- Excellent `apt` ecosystem for Fortran/C toolchains (`gfortran`, `mpich`, `cmake`, dev headers).
- Free standard support through April 2029; ESM through 2036.
- Miniforge and conda-forge work cleanly (the `condaforge/miniforge3` image is itself Ubuntu-based).
- Abundant community documentation for compiling earth-science libraries (WRF, NetCDF, etc.) on Ubuntu.

**Cons:**
- Moves away from the RHEL-family lineage of the original image (`yum`/`dnf` commands become `apt`).
- System library versions differ from NCAR HPC clusters (which run RHEL-family). Not relevant for this project since we are building a JupyterHub teaching/analysis container, not deploying to an HPC scheduler.

### Option B: AlmaLinux 9

**Pros:**
- Direct CentOS successor; closest to the original image's OS lineage.
- RHEL binary-compatible. NCAR clusters (Cheyenne/Derecho) run RHEL-family, so there is some alignment.
- Native arm64 manifests. Support through May 2032.
- Used by CERN and Fermilab for scientific computing containers.

**Cons:**
- Heavier than Ubuntu (~30 MB minimal, but practical installs are larger).
- The scientific Jupyter container community (Pangeo, Jupyter Stacks, Project Pythia) has standardized on Ubuntu, not RHEL clones. Less reference material.
- `dnf` package names differ slightly from the original CentOS 8 (powertools -> crb, some package renames).
- We do not need HPC cluster binary compatibility for this project.

### Option C: Rocky Linux 9

**Pros:** Nearly identical to AlmaLinux 9 (also RHEL 9 clone, arm64 support, May 2032 EOL).

**Cons:** Same as AlmaLinux. Marginally larger compressed size (~44 MB). CIQ (the backing company) has a smaller community than AlmaLinux. No meaningful advantage over AlmaLinux for this use case.

### Option D: Debian 12 (Bookworm)

**Pros:** Ubuntu's upstream; slightly more minimal. Excellent arm64 support.

**Cons:** Regular support ends June 2026 (imminent). LTS extends to June 2028, but that is shorter than Ubuntu 24.04. Debian 13 (Trixie) just released in August 2025 and is viable but very fresh, with less community testing.

### Option E: jupyter/scipy-notebook

**Pros:** Pre-built with JupyterLab, conda/mamba, and common scientific Python packages. arm64 manifests available.

**Cons:** ~1.5 GB compressed. Designed as a ready-to-use notebook server, not as a base for hand-compiling Fortran libraries on top. No Fortran toolchain included. Opinionated directory layout and user setup that may conflict with CESM's expectations. Adds an abstraction layer that is harder to debug.

### Option F: condaforge/miniforge3

**Pros:** Minimal conda-ready image (~148 MB). arm64 support. Clean starting point.

**Cons:** Ubuntu-based internally, so we would still be on Ubuntu but with an extra layer. No Fortran toolchain. For our use case, starting from `ubuntu:24.04` and installing Miniforge ourselves gives more control for roughly the same result.

## Decision

**Use `ubuntu:24.04` as the base image.**

Ubuntu 24.04 is the clear choice for a scientific Jupyter container that does not need HPC cluster binary compatibility. It aligns with the Pangeo and Jupyter Docker Stacks communities, has the longest free support window, the smallest base size, and the best-documented path for compiling Fortran/C scientific libraries. The RHEL-family options (AlmaLinux, Rocky) would be appropriate if we were targeting NCAR HPC clusters directly, but we are building a JupyterHub teaching and analysis platform.

## Consequences

- All `yum`/`dnf` commands in the upstream Dockerfiles must be translated to `apt-get`. However, per [ADR-0004](0004-distributed-computing-support.md), the scope of `apt-get` installs is much smaller than the upstream image since MPICH, HDF5, NetCDF, and PNetCDF now come from conda-forge instead of being compiled against system dev headers.
- Package names differ for the remaining system packages (e.g., `gcc-gfortran` becomes `gfortran`, `gcc-c++` becomes `g++`).
- The CESM machine config files (`config_machines.xml`, `config_compilers.xml`) must be updated to reference conda library paths (`$CONDA_PREFIX/lib`, `$CONDA_PREFIX/include`) instead of `/usr/local`.
- The CI workflow already has QEMU + Buildx configured; adding `platforms: linux/amd64,linux/arm64` to the build step is straightforward.
