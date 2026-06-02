# ADR-0004: Distributed Computing Support (Dask + MPI)

**Status:** Proposed
**Date:** 2026-06-02
**Decision makers:** Steven Wangen

## Context

The upstream `escomp/cesm-lab-neon` image ships a full distributed computing stack: Dask (distributed, dask-gateway client, dask-labextension, dask-jobqueue), MPICH (hand-compiled from source), and esmpy/ESMF. This project does not currently use the Dask distributed features (see analysis below), but other users or future applications of the image may want to run:

- **Dask Gateway clusters** on Kubernetes for parallel analysis of large CESM output datasets
- **MPI-parallel CESM model runs** using multiple cores or nodes
- **HPC job submission** via dask-jobqueue (SLURM, PBS) for campus cluster integration

All components in the Dask + MPI stack are available on conda-forge for `linux-aarch64`, so there are no arm64 blockers. The question is how to structure the image to support these use cases without bloating the default build.

### Current project usage

| Component | Available in upstream | Used by this project? |
|---|---|---|
| MPICH | Hand-compiled from source | Yes, indirectly (CESM links against it for model builds) |
| Dask (core) | conda package | Minimally (xarray lazy I/O only; `chunks=None` is the default) |
| Distributed | conda package | No |
| Dask Gateway (client) | conda package | No (no gateway server deployed) |
| dask-labextension | conda package | No |
| dask-jobqueue | conda package | No |
| mpi4py | conda package | No |
| esmpy / ESMF | conda package | Yes (used for regridding in analysis notebooks) |

## Decision Drivers

- Default image should stay lean for the primary use case (JupyterHub teaching platform)
- Distributed computing support should be available without maintaining a separate fork
- MPICH ABI consistency is critical (mixing hand-compiled and conda MPICH causes silent failures)
- Build complexity should be proportional to the feature's importance

## Decisions

### 1. MPICH: Use conda-forge instead of compiling from source

The upstream image hand-compiles MPICH 3.3.2 from source. This made sense on CentOS 8 where system packages were stale, but on Ubuntu 24.04 with conda-forge it adds ~15 minutes of build time for no benefit.

**Decision: Install MPICH from conda-forge.**

| Approach | Pros | Cons |
|---|---|---|
| **conda-forge MPICH (chosen)** | Fast install; consistent ABI with mpi4py, esmf, and all other conda MPI packages; native aarch64 builds available; version kept current by conda-forge maintainers | Less control over configure flags; may differ from what NCAR HPC clusters use |
| Hand-compile from source (upstream approach) | Exact version control; can match HPC cluster config | Slow build; must also hand-compile mpi4py to avoid ABI mismatch; arm64 cross-compilation adds complexity |

**Consequence:** CESM's machine config files (`config_compilers.xml`, `config_machines.xml`) must point to conda's MPICH install path (`$CONDA_PREFIX/lib`, `$CONDA_PREFIX/include`) instead of `/usr/local`. The same applies to HDF5, NetCDF-C, NetCDF-Fortran, and PNetCDF, all of which are available on conda-forge for linux-aarch64 and can replace the hand-compiled versions.

This is a significant simplification: it eliminates the entire "compile C/Fortran libraries from source" stage of the Dockerfile, replacing ~30 minutes of `configure && make && make install` with a single `mamba install` that takes ~60 seconds.

**Risk:** If CESM's build system has hardcoded expectations about library layout at `/usr/local`, the machine config will need adjustment. This is low risk since the config files already abstract library paths via XML attributes.

### 2. Dask distributed stack: Optional build layer via build arg

The Dask distributed components (distributed, dask-gateway client, dask-labextension, dask-jobqueue) are all `noarch` (pure Python/JS) packages. They add no native-code complexity but do increase image size and conda solve time.

**Decision: Make the Dask distributed stack an optional build layer controlled by a Docker build arg.**

```dockerfile
ARG INSTALL_DASK_DISTRIBUTED=false
COPY environment-dask.yml /tmp/
RUN if [ "$INSTALL_DASK_DISTRIBUTED" = "true" ]; then \
      mamba env update -n base -f /tmp/environment-dask.yml; \
    fi
```

**Default build** (`docker build .`): Installs only `dask` (core, for xarray lazy I/O). No distributed scheduler, no gateway client, no lab extension.

**Distributed build** (`docker build --build-arg INSTALL_DASK_DISTRIBUTED=true .`): Adds the full stack:

```yaml
# environment-dask.yml
dependencies:
  - distributed
  - dask-gateway
  - dask-jobqueue
  - dask-labextension
```

This keeps the default image lean while making the distributed stack a one-flag addition for Kubernetes or HPC deployments.

### 3. esmpy/ESMF: Include in the base environment

esmpy is used by this project for regridding and is available on conda-forge as a `noarch` package that depends on the native `esmf` library (which has `linux-aarch64` builds with mpich, openmpi, and nompi variants). Since we are installing MPICH from conda-forge, the `esmf` package will automatically pick up the mpich variant, and everything links cleanly.

**Decision: Include `esmpy` in the base `environment.yml`.** No special handling needed.

## Consequences

- The Dockerfile build drops from ~45 minutes (with source compilation) to ~5-10 minutes (conda install only) for a cold build.
- All MPI-linked packages (mpich, mpi4py, esmf, netcdf4, hdf5, pnetcdf) come from conda-forge, ensuring consistent ABI across the stack.
- CESM machine configs need to reference conda library paths instead of `/usr/local`.
- Users deploying on Kubernetes with Dask Gateway can enable the full distributed stack with a single build arg.
- Users deploying on HPC clusters can add `dask-jobqueue` the same way.
- The default image remains focused on the teaching/analysis use case.

## Open Questions

- **Should HDF5/NetCDF also come from conda-forge?** If MPICH is moving to conda-forge, the same argument applies to HDF5, NetCDF-C, NetCDF-Fortran, and PNetCDF. Using conda-forge for the entire stack would eliminate the source-compilation stage entirely. This is likely the right call but needs validation that CESM's build system is happy with conda-forge library paths. See [ADR-0002](0002-arm64-build-strategy.md) Phase 1.
- **mpi4py in base or optional?** Currently not used by the project. Could go in the Dask optional layer or in the base environment for users who want MPI from Python. Leaning toward optional.
