# Roadmap

Tracks completed work, current status, and planned next steps for the
ExSOIL NSF Prototype container infrastructure.

Last updated: 2026-06-05

---

## Completed

### Multi-architecture container rebuild (June 2026)

Replaced the legacy `escomp/cesm-lab-neon` container (amd64-only,
CentOS 8, Python 3.7, last updated 2022) with a self-maintained,
multi-arch image on Ubuntu 24.04.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Architecture Decision Records (6 ADRs) | Done | [docs/adr/](adr/) |
| Ubuntu 24.04 base image with conda-forge | Done | [ADR-0001](adr/0001-arm64-base-image.md) |
| 3-stage Dockerfile (base, model, app) | Done | [ADR-0002](adr/0002-arm64-build-strategy.md) |
| Reproducible conda-lock environment | Done | [ADR-0003](adr/0003-conda-environment-strategy.md) |
| Optional Dask distributed layer | Done | [ADR-0004](adr/0004-distributed-computing-support.md) |
| CI/CD multi-arch builds (amd64 + arm64) | Done | `.github/workflows/docker-publish.yml` |
| 90-test validation suite (3 tiers) | Done | [tests/](../tests/) |
| Native arm64 build verified on Apple Silicon | Done | 90/90 tests pass |
| Technical report (MD + HTML + PDF) | Done | [docs/multiarch-rebuild-report/](multiarch-rebuild-report/) |

### CTSM migration (June 2026)

Replaced the full CESM 2.2.2 checkout with standalone CTSM, which
includes the NEON tower workflow natively.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Decision brief: NEON site compatibility | Done | [docs/decisions/001-neon-site-compatibility/](decisions/001-neon-site-compatibility/) |
| ADR-0005: Standalone CTSM | Done | [ADR-0005](adr/0005-standalone-ctsm.md) |
| Dockerfile rewritten for CTSM | Done | `Dockerfile` |
| Python version pin removed (3.11 to 3.13) | Done | `environment.yml` |
| cmake version pin removed | Done | `environment.yml` |
| NEON usermods functional (48 sites) | Done | `run_neon_v2 --help` lists all sites |
| CTSM case.build verified on arm64 | Done | 90/90 tests pass |
| Getting Started notebook | Done | `notebooks/Getting_Started_CTSM_NEON.ipynb` |
| Getting Started guide | Done | [docs/getting-started.md](getting-started.md) |
| Architecture guide with diagrams | Done | [docs/ctsm-architecture-guide/](ctsm-architecture-guide/) |
| Version lineage chart | Done | [docs/ctsm-architecture-guide/lineage-chart.png](ctsm-architecture-guide/lineage-chart.png) |

### Input data resolution (June 2026)

Investigated and resolved the NEON simulation data availability issue
across multiple CTSM versions and NCAR data servers.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Identified ctsm5.4.002 data not on old servers | Done | [decision trail 003](decisions/003-neon-input-data-resolution/) |
| Tested CLM_CMIP_ERA=cmip6 workaround | Done (insufficient) | [ADR-0006](adr/0006-cmip-era-override-for-neon.md) |
| Tested ctsm5.2.005 fallback | Done (Python 3.13 incompatible) | [decision brief 002](decisions/002-ctsm-version-selection.md) |
| Discovered NCAR GDEX server migration | Done | [resolution doc](decisions/003-neon-input-data-resolution/resolution.md) |
| Upgraded to ctsm5.4.043 (current dev tag) | Done | Uses new GDEX data server |
| Verified all global input data downloadable | Done | 19/19 files retrieved from GDEX + SVN + FTP |
| Identified NEON tower data temporal limit | Done | KONZ data available through ~Apr 2023 |

### Documentation (June 2026)

| Document | Status | Path |
|----------|--------|------|
| Full decision trail (9 steps) | Done | [docs/decisions/000-full-decision-trail.md](decisions/000-full-decision-trail.md) |
| NSF progress report | Done | [docs/project-summary/](project-summary/) |
| CTSM architecture guide (4 diagrams) | Done | [docs/ctsm-architecture-guide/](ctsm-architecture-guide/) |
| Version lineage chart | Done | [docs/ctsm-architecture-guide/lineage-chart.png](ctsm-architecture-guide/lineage-chart.png) |
| Plain-language data issue explanation | Done | [docs/decisions/003-neon-input-data-resolution/plain-language-explanation.md](decisions/003-neon-input-data-resolution/plain-language-explanation.md) |
| CHANGELOG | Done | [docs/CHANGELOG.md](CHANGELOG.md) |

### Compatibility fixes discovered and resolved

| Fix | Category | Notes |
|-----|----------|-------|
| CESM 2.2.0 to 2.2.2 | SVN deprecation | GitHub removed SVN support Jan 2024 |
| Python 3.12 pin | CIME compat | Resolved by CTSM migration (CIME 6.1) |
| cmake <4 pin | PIO compat | Resolved by CTSM migration (PIO 2.6) |
| `rdtsc` x86 asm in GPTL | arm64 compat | Removed `HAVE_NANOTIME` flag |
| `-fallow-argument-mismatch` | GCC 10+ | MPI type mismatch strictness |
| `-fallow-invalid-boz` | GCC 10+ | Legacy hex constant strictness |
| `_FillValue` to `NC_FillValue` | NetCDF-C compat | Macro renamed in newer NetCDF |
| PIO2 filter API mismatch | NetCDF compat | Resolved by CTSM migration |
| Bundled `six.py` shadowing | Python compat | Resolved by CTSM migration |
| `XML::LibXML` Perl module | CLM namelists | Added to apt packages |
| `ESMFMKFILE` env var | NUOPC coupling | Required by CTSM's CMEPS coupler |
| Git user config | CIME6 | CIME6 commits during case.build |
| NCAR data server migration | Data infra | ctsm5.4.002 pointed at old servers; 5.4.043 uses GDEX |
| GDEX CDN reliability | Data download | CDN redirect chain intermittent; retries needed |

---

## Current Status

The container can:
- Build and run on arm64 and amd64
- Discover and configure all 48 NEON tower sites
- Compile CTSM from Fortran source (case.build)
- Download all global input data (parameter files, forcing, meshes)
- Set up a NEON transient case through case.setup

The remaining gap is operational: CIME's built-in `check_input_data`
doesn't reliably download all files due to the GDEX CDN redirect chain
and server fallback behavior. Pre-downloading the ~19 problem files
manually works (19/19 succeeded with retries). NEON tower forcing data
is available through approximately April 2023 for KONZ.

---

## Planned

### Near-term: Make data downloads reliable

The core issue is that CIME's download logic fails intermittently on
NCAR's new GDEX CDN (3-hop redirect chain, sometimes returns empty
responses), and some files only exist on one server. Three approaches,
not mutually exclusive:

| Approach | Description | Effort | Benefit |
|----------|-------------|--------|---------|
| **Robust pre-download script** | A script that runs before `case.submit`, fetching all required input data with retries and server fallback (GDEX -> SVN -> FTP). Could be integrated into `run_neon_v2.py` or run as a standalone setup step. | Low-medium | Immediate fix. Works for any NEON site. No infrastructure needed. |
| **Cache on university S3** | Download all CTSM input data for common NEON sites once, host on UW-Madison's campus S3 (`campus.s3.wisc.edu`). The `run_neon_v2.py` S3 pathway already supports non-AWS endpoints. Could serve as a FastAPI service with chunked downloads for workshop/classroom use. | Medium-high | Fast, reliable downloads. Good for multi-user settings. Eliminates dependency on NCAR server reliability. |
| **Bundle static data in container** | Include the ~6 GB of global input data (parameter files, meshes, forcing files that don't change per site) in the Docker image itself. Only site-specific NEON tower observations would need downloading at runtime. | Medium | Zero-download for global data. Increases image size from ~7 GB to ~13 GB. Site-specific data still needs network. |

**Recommendation:** Start with the pre-download script (quick win),
then evaluate S3 caching for classroom/workshop scenarios. Bundling
in the container is only worth it if image size is acceptable.

**Note on data dynamics:** The global input data (parameter files,
meshes, forcing files) is static per CTSM version. It doesn't change
between runs or sites. The NEON tower forcing data is also static once
published, but new months get added as NEON processes new observations.
Both are safe to cache. The only thing that changes per run is the case
configuration itself.

### Near-term: Other items

| Item | Priority | Description |
|------|----------|-------------|
| **Update Dockerfile to ctsm5.4.043** | High | Commit the tag change and document the rationale (GDEX server support). |
| **Shorten default NEON run period** | High | KONZ tower data is available through ~Apr 2023. Adjust `run_neon_v2.py` defaults or documentation to use 2018-2023 instead of 2018-2024. |
| **amd64 build validation** | Medium | All local testing was on arm64. Run tier0+tier1 on an amd64 machine. |
| **CI test integration** | Medium | Wire the test suite into the GitHub Actions workflow. |
| **PR and merge** | Medium | Open PR from `feature/arm64-multiarch-rebuild` to `dev` or `main`. |
| **File ESCOMP GitHub issue** | Low | Report the GDEX CDN reliability issue and the gap between ctsm5.4.002 release config and actual data server. Draft at [docs/ctsm-issue-draft.md](../docs/ctsm-issue-draft.md). May not be needed if ctsm5.4.043 works. |

### Medium-term

| Item | Priority | Description |
|------|----------|-------------|
| **End-to-end NEON simulation test** | High | Run a complete transient simulation at KONZ (2018-2023) with the pre-download script, verify history file output. |
| **Modeling_Hub notebook** | High | Connect the notebook to either live simulation output or NCAR's pre-computed output (available for 45 sites at storage.neonscience.org). |
| **Design_Hub_v2 validation** | Medium | Test perturbation experiments end-to-end. |
| **NEON observation pipeline** | Medium | Implement `download_eval_files` to fetch processed tower observations for model-data comparison. |
| **Image size optimization** | Low | Investigate `--filter=blob:none` clone, BuildKit cache mounts. |

### Long-term

| Item | Description |
|------|-------------|
| **CESM 3.x evaluation** | When CESM 3.x ships (est. late 2026), evaluate whether to maintain a separate coupled-model container. |
| **Pre-built case images** | Explore shipping a container with a pre-compiled CLM binary for common compsets. |
| **Multi-site batch runs** | Support running all 48 NEON sites in batch for systematic model evaluation. |
