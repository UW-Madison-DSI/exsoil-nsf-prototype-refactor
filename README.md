# ExSOIL NSF Prototype

A containerized environment for evaluating the Community Land Model
(CLM) against NEON tower site observations. Researchers run CLM at
real-world instrumented sites, compare predictions of soil temperature,
moisture, and carbon fluxes against what the towers actually measured,
and use statistical techniques (misfit diagnostics, Kalman filter
calibration) to quantify and reduce model-data disagreement.

The container packages CTSM 5.4 (standalone CLM with the NEON tower
workflow), a full Fortran build toolchain, and a Python analysis stack
(xarray, cartopy, matplotlib, JupyterLab) into a single image that
runs natively on both Intel/AMD and Apple Silicon machines.

## How the pieces fit together

![Version Lineage](docs/ctsm-architecture-guide/lineage-chart.png)

The ExSOIL container is built on **CTSM 5.4** (tag ctsm5.4.043),
NCAR's standalone land modeling framework. CTSM assembles CLM 6.0
(the land model code), CIME 6.1 (the build and case management
system), and the NEON tower workflow (48 site configurations) into
a single release. Our container adds the arm64/amd64 multi-platform
build, a conda-forge Python analysis stack, and project-specific
notebooks and analysis tools on top.

For a detailed guide to the software architecture, see
[docs/ctsm-architecture-guide](docs/ctsm-architecture-guide/).
For the full decision trail from the initial ARM64 problem through
the CTSM migration, see
[docs/decisions/000-full-decision-trail.md](docs/decisions/000-full-decision-trail.md).

## Quick start

```bash
docker run --rm -p 8888:8888 exsoil-arm64-test
```

Open the URL printed in the terminal. In JupyterLab, start with
`notebooks/Getting_Started_CTSM_NEON.ipynb` to verify the environment
and explore available NEON sites. No credentials needed.

For the full analysis workflows (which pull data from S3), pass your
credentials:

```bash
docker run --rm -p 8888:8888 --env-file .env exsoil-arm64-test
```

See [docs/getting-started.md](docs/getting-started.md) for detailed
setup instructions.

## What is inside

| Component | What it does |
|-----------|-------------|
| **CTSM 5.4** | Standalone Community Terrestrial Systems Model with NEON usermods for 48 tower sites |
| **CLM** | Community Land Model: simulates soil physics, vegetation, hydrology, carbon cycling |
| **CIME** | Build and case management: create_newcase, case.setup, case.build, case.submit |
| **DATM** | Data atmosphere: feeds observed weather to CLM instead of a simulated atmosphere |
| **Python stack** | xarray, cartopy, matplotlib, scipy, pandas, bokeh, panel, JupyterLab |
| **analytics_modules** | Project-specific: Kalman filter calibration, model misfit diagnostics, S3 data access |
| **Compilers** | gfortran, gcc, MPICH, cmake (via conda-forge): build CLM from Fortran source |

## Notebooks

| Notebook | Purpose | Needs credentials? |
|----------|---------|-------------------|
| **Getting_Started_CTSM_NEON** | Verify environment, explore NEON sites, create a sample case | No |
| **Data_Hub** | Load CLM output from S3, soil profile visualization | Yes |
| **Design_Hub_v2** | Run CLM with forcing perturbations, compare scenarios | Yes |
| **Modeling_Hub** | Model-data misfit evaluation, Kalman filter calibration | Yes (+ simulation output) |
| **pft_perturbation_comparison** | Compare control and perturbed PFT runs | Yes |

## Multi-platform support

The container builds for both `linux/amd64` and `linux/arm64`. Docker
selects the correct architecture automatically. On Apple Silicon Macs,
the container runs natively with no emulation.

## Project layout

```
Dockerfile                      3-stage build: base (conda) -> ctsm (model) -> app (notebooks)
environment.yml                 ~35 direct conda dependencies
conda-lock.yml                  Pinned versions for both architectures
ctsm-config/                    Machine config overlay for conda-forge library paths
notebooks/                      JupyterLab notebooks
analytics_modules/              Kalman filter, model misfit, data access, LLM tools
cesm-tools/                     run_neon_v2.py (NEON site simulation wrapper)
scripts/
  pre-download-inputdata.sh     Downloads ~6 GB of input data with retry/fallback
tests/                          90-test validation suite (tier0 smoke, tier1 case, tier2 build)
docs/
  getting-started.md            New user guide
  ctsm-architecture-guide/      Visual guide + version lineage chart
  adr/                          6 Architecture Decision Records
  decisions/                    Decision briefs + investigation trails
  multiarch-rebuild-report/     Technical report on the multi-arch rebuild
  project-summary/              NSF progress report
  ROADMAP.md                    Completed work and planned next steps
  CHANGELOG.md                  What changed in this release
```

## Documentation

| Document | Audience | What it covers |
|----------|----------|---------------|
| [Getting Started](docs/getting-started.md) | New users | How to run the container and use the notebooks |
| [Architecture Guide](docs/ctsm-architecture-guide/) | Domain experts | How CESM, CTSM, CLM, CIME, and NEON relate; diagrams |
| [ADRs](docs/adr/) | Maintainers | Why each technical decision was made |
| [Rebuild Report](docs/multiarch-rebuild-report/) | Platform engineers | Full technical detail of the multi-arch rebuild |
| [Roadmap](docs/ROADMAP.md) | Team | What is done, what is next |

## Building locally

```bash
# Native build with embedded input data (default, ~13 GB image)
docker build -t exsoil-arm64-test .

# Lightweight build without input data (faster, ~7 GB image)
docker build --build-arg EMBED_INPUTDATA=false -t exsoil-arm64-test .

# With optional Dask distributed computing stack
docker build --build-arg INSTALL_DASK_DISTRIBUTED=true -t exsoil-arm64-test .

# Run the test suite
./tests/run_container_tests.sh tier0 tier1    # quick (6 seconds)
./tests/run_container_tests.sh                # full including case.build (2 minutes)
```

By default, the build embeds ~6 GB of global CTSM input data from a
GitHub Release so simulations can start without downloading from NCAR.
Use `EMBED_INPUTDATA=false` for development builds where you don't
need to run simulations.

## CI/CD

`.github/workflows/docker-publish.yml` builds for both architectures
on every push to `main` and on version tags. Images are pushed to
`ghcr.io/uw-madison-dsi/exsoil-nsf-prototype-refactor`.

## License

[MIT](LICENSE.md)
