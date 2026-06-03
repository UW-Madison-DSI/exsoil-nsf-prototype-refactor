# Roadmap

Tracks completed work, current status, and planned next steps for the
ExSOIL NSF Prototype container infrastructure.

Last updated: 2026-06-03

---

## Completed

### Multi-architecture container rebuild (June 2026)

Replaced the legacy `escomp/cesm-lab-neon` container (amd64-only,
CentOS 8, Python 3.7, last updated 2022) with a self-maintained,
multi-arch image on Ubuntu 24.04.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Architecture Decision Records (5 ADRs) | Done | [docs/adr/](adr/) |
| Ubuntu 24.04 base image with conda-forge | Done | [ADR-0001](adr/0001-arm64-base-image.md) |
| 3-stage Dockerfile (base, model, app) | Done | [ADR-0002](adr/0002-arm64-build-strategy.md) |
| Reproducible conda-lock environment | Done | [ADR-0003](adr/0003-conda-environment-strategy.md) |
| Optional Dask distributed layer | Done | [ADR-0004](adr/0004-distributed-computing-support.md) |
| CI/CD multi-arch builds (amd64 + arm64) | Done | `.github/workflows/docker-publish.yml` |
| 90-test validation suite (3 tiers) | Done | [tests/](../tests/) |
| Native arm64 build verified on Apple Silicon | Done | 90/90 tests pass |
| Technical report (MD + HTML + PDF) | Done | [docs/multiarch-rebuild-report/](multiarch-rebuild-report/) |

### CTSM migration (June 2026)

Replaced the full CESM 2.2.2 checkout with standalone CTSM 5.4, which
includes the NEON tower workflow natively.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Decision brief: NEON site compatibility | Done | [docs/decisions/001-neon-site-compatibility/](decisions/001-neon-site-compatibility/) |
| ADR-0005: Standalone CTSM | Done | [ADR-0005](adr/0005-standalone-ctsm.md) |
| Dockerfile rewritten for CTSM 5.4 | Done | `Dockerfile` |
| Python version pin removed (3.11 to 3.13) | Done | `environment.yml` |
| cmake version pin removed | Done | `environment.yml` |
| NEON usermods functional (48 sites) | Done | `run_neon_v2 --help` lists all sites |
| CTSM case.build verified on arm64 | Done | 90/90 tests pass |
| Getting Started notebook | Done | `notebooks/Getting_Started_CTSM_NEON.ipynb` |
| Getting Started guide | Done | [docs/getting-started.md](getting-started.md) |

### Compatibility fixes discovered and resolved

These issues were found through iterative build-test cycles and are
documented in the test suite and ADR-0002 implementation notes.

| Fix | Category | Notes |
|-----|----------|-------|
| CESM 2.2.0 to 2.2.2 | SVN deprecation | GitHub removed SVN support Jan 2024 |
| Python 3.12 pin | CIME compat | CIME 2.2.x used `import imp` (resolved by CTSM migration) |
| cmake <4 pin | PIO compat | PIO 2.2 used old cmake_minimum_required (resolved by CTSM migration) |
| `rdtsc` x86 asm in GPTL | arm64 compat | Removed `HAVE_NANOTIME` flag |
| `-fallow-argument-mismatch` | GCC 10+ | MPI type mismatch strictness |
| `-fallow-invalid-boz` | GCC 10+ | Legacy hex constant strictness |
| `_FillValue` to `NC_FillValue` | NetCDF-C compat | Macro renamed in newer NetCDF |
| PIO2 filter API mismatch | NetCDF compat | Resolved by CTSM migration (newer PIO) |
| Bundled `six.py` shadowing | Python compat | Resolved by CTSM migration (no bundled six) |
| `XML::LibXML` Perl module | CLM namelists | Added to apt packages |
| `ESMFMKFILE` env var | NUOPC coupling | Required by CTSM's CMEPS coupler |
| Git user config | CIME6 | CIME6 commits during case.build |
| `ctsm.download_utils` fallback | CTSM compat | Module absent in CESM 2.2.2's CTSM |

---

## In Progress

Nothing currently in progress. The feature branch
`feature/arm64-multiarch-rebuild` is ready for PR review.

---

## Planned

### Near-term (next sprint)

| Item | Priority | Description |
|------|----------|-------------|
| **NEON simulation pipeline** | High | The `Modeling_Hub` notebook requires CLM history files from a completed transient run and NEON evaluation files, neither of which are currently producible in the container. Needs: (1) implement or document the end-to-end run workflow, (2) implement `download_eval_files` to fetch NEON tower observations, or (3) bundle sample data for one site/year. |
| **CTSM input data availability** | High | CTSM 5.4.002 references CMIP7-era input datasets not yet on NCAR's servers (8 GB downloaded, then failed on missing NEON surface data and CMIP7 forcing files). CTSM 5.2.005 was tested as a fallback but has Python 3.13 CIME incompatibility. Staying with 5.4; need to report to ESCOMP and investigate alternative data sources. See [decision brief](decisions/002-ctsm-version-selection.md). |
| **amd64 build validation** | Medium | All local testing was on arm64. The amd64 image builds in CI but has not been tested through the test suite. Run tier0+tier1 on an amd64 machine. |
| **CI test integration** | Medium | Wire the test suite into the GitHub Actions workflow. At minimum, run tier0+tier1 on both architectures after each push. |
| **PR and merge to dev** | Medium | Open PR from `feature/arm64-multiarch-rebuild` to `dev` (or `main` per team workflow). |

### Medium-term

| Item | Priority | Description |
|------|----------|-------------|
| **Design_Hub_v2 end-to-end validation** | Medium | Test the full perturbation experiment workflow (S3 forcing download, `run_neon_v2` with transform flags, output analysis) on the new CTSM container. |
| **Data_Hub S3 connectivity** | Medium | Verify S3 data access works from the container with valid credentials. The Data_Hub notebook timed out during earlier testing due to S3 endpoint connectivity. |
| **Image size optimization** | Low | Current image is ~7 GB. Investigate whether CTSM's git history can be pruned further, or whether a `--filter=blob:none` clone reduces size. |
| **BuildKit cache mounts** | Low | Add `--mount=type=cache` for conda packages to speed up cache-miss rebuilds. |

### Long-term

| Item | Description |
|------|-------------|
| **Input data caching on university S3** | A first-time NEON simulation downloads 2+ GB of input data from NCAR's FTP servers, which is slow and adds several minutes to the first run. Investigate caching frequently-used CTSM input data (surface datasets, forcing files for common NEON sites) on UW-Madison's campus S3 (`campus.s3.wisc.edu`) and providing a FastAPI service that delivers chunked downloads. This could significantly reduce first-run latency, particularly for workshop/classroom settings where many users pull the same data simultaneously. The `run_neon_v2.py` S3 pathway (`--s3-input-bucket`, `--s3-endpoint-url`) already supports non-AWS S3; the infrastructure question is standing up the API and populating the cache. |
| **CESM 3.x evaluation** | When CESM 3.x ships (est. late 2026), evaluate whether to maintain a separate coupled-model container for experiments requiring atmosphere-land feedbacks. |
| **NEON observation pipeline** | Build an automated pipeline to download, process, and format NEON tower observations for model-data comparison. |
| **Pre-built case images** | Explore shipping a container with a pre-compiled CLM binary for common compsets to eliminate the `case.build` step for users. |
