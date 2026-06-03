# Changelog

All notable changes to the ExSOIL NSF Prototype container.

## [Unreleased] - feature/arm64-multiarch-rebuild

### Added
- Multi-architecture Docker support (amd64 + arm64) on Ubuntu 24.04
- Standalone CTSM 5.4 with native NEON tower site workflow (48 sites)
- Reproducible conda-lock environment for both platforms
- 90-test validation suite across 3 tiers (smoke, case creation, build + analysis)
- Container machine configs for conda-forge library paths
- Optional Dask distributed computing layer via build arg
- Getting Started notebook (`Getting_Started_CTSM_NEON.ipynb`)
- Getting started guide (`docs/getting-started.md`)
- 5 Architecture Decision Records (base image, build strategy, conda env, distributed computing, standalone CTSM)
- Decision brief on NEON site compatibility with version lineage research
- Multi-platform rebuild technical report (Markdown, HTML, PDF)
- Roadmap tracking completed and planned work
- CI/CD workflow updated for multi-arch builds

### Changed
- Base image: CentOS 8 (EOL) to Ubuntu 24.04 LTS
- Model: CESM 2.2.2 to standalone CTSM 5.4.002
- Python: 3.7 (via old conda env) to 3.13 (via conda-lock)
- Scientific libraries: hand-compiled from source to conda-forge binaries
- Build time: ~45 min (source compilation) to ~5 min (conda install)
- Coupling framework: MCT (legacy) to NUOPC (current)
- CIME: 5.x (Python 3.11 required) to 6.1 (Python 3.12+ supported)
- Package count: ~400 (upstream) to ~35 direct deps + lockfile
- `run_neon_v2.py`: updated usermods path and compset names for CTSM 5.4

### Removed
- CentOS 8 base image
- Full CESM checkout (CAM, POP, CICE, CISM, WW3 source trees)
- Hand-compiled MPICH, HDF5, NetCDF-C, NetCDF-Fortran, PNetCDF
- PIO2 source patches (no longer needed with CTSM's newer PIO)
- Python 3.11 version pin
- cmake <4 version pin
- CESM-specific PE configs for atmosphere, ocean, and ice components
