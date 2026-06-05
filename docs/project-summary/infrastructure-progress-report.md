# Infrastructure Progress Report: ExSOIL Containerized Modeling Environment

**Period:** May-June 2026
**Project:** ExSOIL NSF Prototype
**Prepared by:** Steven Wangen, UW-Madison Data Science Institute

## Objectives

The ExSOIL project uses the Community Terrestrial Systems Model (CTSM)
to simulate soil processes at NEON ecological observatory sites across
the United States. Researchers run CTSM at specific tower locations,
feed the model observed atmospheric forcing data, and compare the
model's predictions of soil temperature, moisture, and carbon fluxes
against real measurements from the tower instruments. This
model-observation comparison is the foundation for evaluating and
improving CTSM's representation of soil biogeochemistry.

The project's computational environment is delivered as a Docker
container that packages CTSM, the NEON site workflow, and a Python
analysis stack into a single reproducible unit. Researchers pull the
container, launch JupyterLab, and work with model simulations and
observational data without installing or configuring any of the
underlying software.

The diagram below shows how the components, releases, and container
relate over time:

![Version Lineage](../ctsm-architecture-guide/lineage-chart.png)

This reporting period focused on two infrastructure objectives:

1. **Multi-platform support.** The existing container only ran on
   Intel/AMD processors. Team members on Apple Silicon Macs (M1-M4)
   could not run the container reliably, limiting local development
   and testing.

2. **NEON workflow restoration.** The container's NEON tower site
   workflow had become non-functional due to version incompatibilities
   in the underlying CESM/CTSM model framework.

## Activities and Outcomes

### Multi-architecture container rebuild

The project's Docker container was rebuilt from scratch on a modern
foundation. The previous container was based on CentOS 8 (end-of-life
since December 2021), shipped Python 3.7 (end-of-life since June 2023),
and only produced Intel/AMD binaries.

The rebuilt container:

- **Runs natively on both Intel/AMD and Apple Silicon** (arm64)
  processors. Docker automatically selects the correct architecture
  when pulling the image. Team members on Apple Silicon Macs can now
  develop and test locally without the performance penalties and
  stability issues of processor emulation.

- **Uses Ubuntu 24.04 LTS** as the base operating system, with
  security support through 2029. This replaces CentOS 8, which has
  not received security patches since December 2021.

- **Installs all scientific libraries from conda-forge** pre-built
  binaries instead of compiling them from Fortran and C source code.
  This reduced container build time from approximately 45 minutes to
  5 minutes and eliminated a major source of architecture-specific
  build failures.

- **Pins exact package versions** via conda-lock for both processor
  architectures, ensuring that every team member gets identical
  software regardless of their hardware.

- **Upgrades to Python 3.13** and current versions of all scientific
  packages (xarray, cartopy, matplotlib, scipy, etc.), replacing
  versions that were 4-6 years old.

A 90-test automated validation suite was developed to verify the
container's functionality across three tiers: basic environment checks
(Python imports, compilers, libraries), CIME case management workflow
(creating and configuring CTSM cases), and full Fortran model
compilation with scientific analysis workflows (NetCDF I/O, cartopy
map rendering, xarray diagnostics). All 90 tests pass on native arm64.

### CTSM migration and NEON workflow restoration

During the rebuild, we discovered that the NEON tower site workflow
was non-functional. Investigation revealed that NEON support was never
part of any CESM 2.x release; it was developed exclusively for
standalone CTSM starting in February 2021 and will not enter CESM
until version 3.x (currently in beta, targeted for late 2026). The
previous container had worked around this by using a custom,
undocumented build that mixed component versions from different release
lines.

Based on this finding, we replaced the full CESM framework with
standalone CTSM 5.4, which is NCAR's intended platform for the NEON
workflow. This change:

- **Restored the NEON tower site workflow** with pre-configured
  settings for 48 NEON sites. Researchers can create and run
  single-point CLM simulations at any of these sites.

- **Reduced the container image size** by removing approximately 3-4 GB
  of source code for Earth system components the project does not use
  (atmosphere, ocean, sea ice, ice sheet, and wave models).

- **Aligned with NCAR's recommended approach** for NEON tower
  experiments, as documented in the official CTSM user guide and NCAR
  tutorial materials.

- **Removed the need for several workarounds** that had been applied to
  make CESM 2.2.2 compile with modern compilers, including PIO2 source
  patches, Python version pinning, and cmake version restrictions.

The trade-off is that the container no longer supports fully coupled
Earth system simulations (where the land surface interacts with a
simulated atmosphere, ocean, and ice). The project does not currently
use coupled simulations; all existing workflows run CLM in single-point
mode with observed atmospheric forcing. If coupled experiments are
needed in the future, a separate CESM 3.x container can be maintained
alongside the CTSM container.

### Documentation

The rebuild and migration are documented through:

- **5 Architecture Decision Records** that capture the rationale for
  each major technical choice (base image selection, build strategy,
  dependency management, distributed computing support, and the CTSM
  migration)
- **A decision brief** analyzing five options for restoring NEON
  support, including a version lineage diagram and CESM 3.x timeline
  research
- **A technical rebuild report** covering the full implementation
  detail for platform engineering review
- **A getting-started guide and introductory notebook** for new users
  joining the project
- **A roadmap** tracking completed work and planned next steps
- **A changelog** summarizing all additions, changes, and removals

## Challenges

The primary challenge was the gap between CESM's official release
versions and the NEON workflow's development timeline. The NEON tower
site functionality was developed on CTSM's master branch after the
CESM 2.2 release line had been cut, and will not be available in a
full CESM release until version 3.x ships. The previous container
masked this gap by using an undocumented custom build. Our rebuild
exposed the issue, which led to the architectural decision to move
to standalone CTSM.

A secondary challenge was achieving Fortran compilation on arm64 with
modern compiler and library versions. CESM 2.2.2's code (written
primarily for Intel compilers on x86 HPC systems) required 13 separate
compatibility fixes to compile with GCC 15 and conda-forge's current
NetCDF libraries on ARM processors. These fixes were identified
iteratively through the automated test suite. Many of them became
unnecessary after the CTSM migration, which uses newer, more
portable code.

## Next Steps

1. **NEON simulation pipeline.** The Modeling_Hub notebook, which
   performs model-data evaluation and Kalman Filter calibration,
   requires CLM history files from a completed transient run and
   processed NEON tower observations. Building this end-to-end
   pipeline (data download, simulation execution, observation
   processing) is the next priority.

2. **CI/CD test integration.** The 90-test validation suite runs
   locally but is not yet wired into the GitHub Actions workflow.
   Adding automated testing on both architectures after each push
   will catch regressions early.

3. **Cross-architecture validation.** All local testing was performed
   on Apple Silicon (arm64). The Intel/AMD (amd64) image builds in CI
   but has not been validated through the test suite.

4. **Science notebook validation.** The Data_Hub and Design_Hub
   notebooks need end-to-end testing with S3 credentials on the new
   CTSM container to verify the full analysis workflow.
