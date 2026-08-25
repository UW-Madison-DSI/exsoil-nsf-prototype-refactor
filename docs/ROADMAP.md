# Roadmap

Tracks completed work, current status, and planned next steps for the
ExSOIL NSF Prototype.

The project crossed a phase boundary in July 2026: the **infrastructure
phase is complete**, and work is now in the **scientific-capability
phase** (getting the three analysis Hubs running on live/native data).
Execution for that phase is planned and tracked separately:

- Charter: [docs/phase-objectives/](phase-objectives/phase-objectives.md)
- Implementation plan: [docs/hub-integration-plan/](hub-integration-plan/hub-integration-plan.md)
- Data contract: [docs/data-contract.md](data-contract.md)
- Execution tracker: GitHub epic **#11** (phase issues #5-#10, scope decisions #12-#14)
- Shareable status: [docs/project-summary/hub-integration-progress-report.md](project-summary/hub-integration-progress-report.md)

Last updated: 2026-08-25

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
| `MPILIB=mpi-serial` conflict | MPI runtime | CIME serial stubs conflict with conda-forge MPICH at runtime; patched NEON usermods to use mpich |

### End-to-end simulation (June 2026)

First successful NEON tower site simulation in the container.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Diagnose MPI initialization failure | Done | mpi-serial stubs conflict with conda-forge MPICH |
| Patch NEON usermods for mpich | Done | `Dockerfile` sed removes `MPILIB=mpi-serial` |
| Add mpi-serial mpirun safety net | Done | `config_machines.xml` |
| 1-day KONZ transient simulation | Done | 31 variables, 48 time steps, valid NetCDF output |
| xarray reads CLM output (FSH, TSOI, H2OSOI) | Done | Soil temp, moisture, sensible heat flux |
| Full-duration KONZ run (2018-2024) | Done | 83 monthly history files, 337 s model time |
| Performance baseline documented | Done | [docs/benchmarks/konz-performance-baseline.md](benchmarks/konz-performance-baseline.md) |

### Hub integration planning + Phase 0 (July 2026)

Phase boundary from infrastructure to scientific capability. Target:
the three Hubs (Data Analysis, Modeling, Experimentation) running on
live/native data across 5 NEON sites (KONZ, ABBY, CPER, TALL, CLBJ).
This is a data-rebind and validation effort, not a redesign.

| Milestone | Status | Reference |
|-----------|--------|-----------|
| Phase objectives / charter | Done | [docs/phase-objectives/](phase-objectives/phase-objectives.md) |
| Implementation plan (6 phases) | Done | [docs/hub-integration-plan/](hub-integration-plan/hub-integration-plan.md) |
| GitHub epic + phase issues | Done | Epic #11, issues #5-#10 |
| **Phase 0** — data contract | Done | [docs/data-contract.md](data-contract.md) |
| **Phase 0** — fixtures scaffolding | Done | `tests/fixtures/reference_output/` (`.nc` payloads gitignored) |
| Reference copies received + evaluated | Done | 343 MB, 5 sites, staged locally |

---

## Current Status

The container can:
- Build and run on arm64 and amd64
- Discover and configure all 48 NEON tower sites
- Compile CTSM from Fortran source (case.build)
- Download all global input data (parameter files, forcing, meshes)
- **Run a complete NEON simulation end-to-end** (case.submit produces CLM history files)
- Read simulation output with xarray for analysis

The full pipeline (pre-download, case.build, case.submit, archive,
xarray analysis) has been validated at KONZ with a full 2018-2024
transient run (83 monthly history files). NEON tower forcing data is
available through December 2024 for KONZ (84 monthly files; use
`STOP_N=83` — see the performance baseline for the boundary gotcha).

**Infrastructure is done. The active work is hub integration.** Phase 0
and Phase 1 are complete; Phases 2-5 have not started. The analysis
library now reads local output by default, but the Hub notebooks still
contain their own S3 calls, which is Phase 2 onward.

### Phase 1 outcome (resolved, July 2026)

The blocker was that live CTSM output uses suffixed streams (`h0a`
monthly, `h1a` daily) while the readers filtered on the stale
`archive_1/...clm2.h1.{year}` pattern, matching **zero** live files.
Resolved in `430d416` — but three of the plan's assumptions turned out
to be wrong, and the fixes differ from what was written:

| Plan said | Reality |
|---|---|
| Change `h1`→`h1a` in both files | Would have broken the S3 path. S3 and the reference copies legitimately use `h1`; both conventions must work at once, so the token is discovered by probing. |
| Engine may be NetCDF-4; try `h5netcdf` | Live output is **CDF-5**. `scipy` cannot read it and `h5netcdf` cannot either. Engine is chosen from the file's magic number. |
| Live path is `{output_root}/archive/lnd/hist/` | That is the `run_tower` layout. `run_neon_v2.py:1086-1089` uses `{dirname(base_case_root)}/archive/{site}/{control\|VAR_VALUE}/`. Data contract corrected in `ebf68fc`. |
| Two files need the fix | Three. `analytics_modules/neon_notebook_wrapper.py:34` is named nowhere in the plan or issue. |

Also fixed along the way: `plot_soil_profile_timeseries`'s local branch
was dead code (`is_s3` derived from a literal, so always `True`), and
`run_neon_v2.py` carried 238 lines of forked S3 helpers, three-quarters
of them unreachable, removed in `621d329`.

`CTSM_OUTPUT_ROOT` defaults to `/home/user`, documented in
[getting-started](getting-started.md).

---

## Planned

### Data downloads and CI/CD (resolved, June 2026)

The ~6 GB of global input data is embedded in the Docker image via
GitHub Release assets (`inputdata-v5.4.043`). The Dockerfile fetches
compressed tarballs and split raw files from GitHub's CDN during the
build. Researchers pull the image and it's ready to run.

The CI/CD pipeline builds both amd64 and arm64 images on separate
GitHub Actions runners (to avoid disk exhaustion), pushes per-platform
digests, then merges them into a multi-arch manifest list on GHCR.

| Milestone | Status |
|-----------|--------|
| Embed input data in image via GitHub Release | Done |
| Multi-arch CI (split per-platform builds) | Done |
| Published to GHCR (`v2.0.0-rc4`) | Done |
| amd64 build validated in CI | Done (17 min) |
| arm64 build validated in CI | Done (32 min, QEMU) |

Image: `ghcr.io/uw-madison-dsi/exsoil-nsf-prototype-refactor:v2.0.0-rc4`

Image size: ~14.7 GB uncompressed (~7 GB compressed per architecture).
For lightweight development builds, use `--build-arg EMBED_INPUTDATA=false`.

**Data profile (verified 2026-06-05):**

| Category | Size | Changes? | Download speed | Notes |
|----------|------|----------|---------------|-------|
| Global input data | ~6 GB | Never (static per CTSM version) | Slow (GDEX CDN unreliable, SVN ~300 KB/s) | Parameter files, meshes, forcing scenarios. Shared across all sites. Download once, cache forever. |
| NEON site surface data | ~56 KB per site | Never (static per CTSM version) | Fast (GDEX) | One file per site. All 48 sites = ~2.7 MB. |
| NEON tower forcing | ~150 KB/month per site | New months added as NEON publishes | Fast (Google Cloud, 5 files in 2s) | 84 months available (2018-01 through 2024-12). All 48 sites through 2024 = ~600 MB. |

Total for one site: ~6 GB global + 56 KB site + 12.6 MB forcing = ~6 GB.
Total for all 48 sites: ~6 GB global (shared) + 600 MB forcing = ~6.6 GB.

The global data is the bottleneck. It's large, slow to download, and
the GDEX CDN is unreliable. But it only needs to be downloaded once.
A pre-download script or cache eliminates this cost for all subsequent
runs. The NEON tower data is trivial.

### Near-term: Other items

| Item | Priority | Description |
|------|----------|-------------|
| ~~Update Dockerfile to ctsm5.4.043~~ | ~~High~~ | Done. |
| ~~Embed input data in image~~ | ~~High~~ | Done. GitHub Release assets, fetched during build. |
| ~~Multi-arch CI/CD~~ | ~~High~~ | Done. Split per-platform builds, manifest merge. |
| ~~amd64 build validation~~ | ~~Medium~~ | Done. Built and pushed via CI (17 min native). |
| ~~Publish to GHCR~~ | ~~Medium~~ | Done. `v2.0.0-rc4` with both architectures. |
| ~~Review use cases with Jingyi~~ | ~~High~~ | Done. Settled in the July 9 `communication-internal` thread: native/live data, GPP as the Kalman target, 5 sites, 4-step Hub 3 loop. |
| ~~Full-duration simulation~~ | ~~Medium~~ | Done. Full 2018-2024 KONZ run, 83 monthly files. |
| ~~Phase 1: rebind data-access layer~~ | ~~High~~ | Done (#6, `430d416`). `open_ctsm_hist()` / `find_ctsm_hist_files()` read local output with no credentials; 15 tests pass against real KONZ and reference data. |
| **Phase 2: Hub 1 on live output** | High | Issue #7. Repoint `Data_Hub.ipynb` at `open_ctsm_hist()` and drop its eager credential cell. Note `/opt/analytics_modules` shadows the repo on `sys.path`. ~0.5 day. |
| **Get scope decisions to Jingyi** | High | Issues #12-#14 plus perturbation scope and validation tolerance. #12 blocks Phase 3. |
| **PR and merge** | Medium | Open PR from `feature/arm64-multiarch-rebuild` to `dev`. 63 commits ahead of `main`, no PR open. |
| **File ESCOMP GitHub issue** | Low | Report the mpi-serial conflict and data server gap. Draft at `docs/ctsm-issue-draft.md`. |

### Medium-term

Hub work is tracked in detail by the
[implementation plan](hub-integration-plan/hub-integration-plan.md) and
epic #11. Summarized here:

| Item | Priority | Description |
|------|----------|-------------|
| ~~End-to-end NEON simulation test~~ | ~~High~~ | Done. Full KONZ transient produces valid CLM output. |
| ~~Observation source discovery~~ | ~~Medium~~ | Done (#12). NCAR/NEON eval files, public and credential-free, 45 monthly files per site covering 2018-01 → 2021-09 for all 5 sites, carrying observed GPP. Ingestion spec (units, cadence, quality flags) written. |
| ~~Observed-GPP comparison policy~~ | ~~High~~ | Decided (#12). **Compare at monthly resolution.** Negatives are a flux-partitioning artifact affecting 26-36% of half-hourly values; monthly aggregation reduces that to 8%, all dormant-season and within ±0.1 umol/m2/s of zero. See [decision 005](decisions/005-observed-gpp-comparison/). |
| **NEON observation pipeline** | High | Issue #12. Implement the fetch/read helper replacing the unwritten `download_eval_files`, applying the monthly-comparison decision and the ×12.011e-6 unit conversion. |
| **Rescope Phase 3/5 site coverage** | High | **41 of 225 site-months have no GPP at all** (18%). Only KONZ is complete (45/45); ABBY is 28/45. The five-site scope needs revisiting against real coverage. See [decision 005](decisions/005-observed-gpp-comparison/). |
| **Phase 2: Hub 1 (Data Analysis)** | High | Issue #7. Simplest Hub first, per Maria's recommendation. ~0.5 day. |
| **Phase 3: Hub 2 (Modeling / Kalman)** | High | Issue #8. Unblocked on data; still needs the negative-GPP filtering policy (#12). ~1 day. |
| **Extend the fit metrics** | Medium | Add seasonal-cycle and interannual-variability scoring to `compute_fit`, the genuine gap versus ILAMB. See [Goodness-of-fit evaluation](#goodness-of-fit-evaluation) below. |
| **Phase 4: Hub 3 (Experimentation)** | Medium | Issue #9. Precip perturbation → two runs → t-test. ~1.5 days. |
| **Phase 5: multi-site validation** | Medium | Issue #10. All 3 Hubs × 5 sites from a fresh pull. Scope to the 2018-01 → 2021-09 observation window. ~1 day. |
| **Image size optimization** | Low | Investigate `--filter=blob:none` clone, BuildKit cache mounts. |

### Goodness-of-fit evaluation

Hub 2 currently computes **R², RMSE, MAE, and bias** (`neon_eval_utils.compute_fit`),
plus bias and RMSE ratios against observed standard deviation in
`residuals_plots`. That covers *magnitude* agreement.

**The gap is attribution, not detection.** Because `compute_fit` compares
aligned observation/prediction pairs, a seasonal peak at the wrong time
*does* already degrade R², RMSE, and MAE — the existing metrics are not
blind to phase error. What they cannot do is tell you it *was* phase
error. A single worse RMSE could be amplitude bias, phase shift, noise,
or a handful of bad months, and the current output gives no way to
distinguish them.

Separately scoring the **seasonal cycle** (phase and amplitude of the
mean annual cycle) and **interannual variability** (year-to-year tracking
of departures from that cycle) turns one undifferentiated number into a
diagnosis. That is what ILAMB does, and it is the part of ILAMB this
project genuinely lacks. Bias alone is the weakest case — it can be near
zero under a pure phase shift — but the broader point is interpretability
across all four existing metrics.

**Proposed direction: add the metrics, not the framework.** Fold
ILAMB-style seasonal-cycle and interannual-variability scoring into
`compute_fit` rather than adopting ILAMB itself. The reasoning is in #13,
but briefly: ILAMB's value is comparability through its curated global
reference datasets, and this project evaluates against NEON tower
observations instead — so running its machinery over our own data
forfeits most of the benefit that justifies the machinery.

> **Not yet decided.** #13 is open and the choice is Jingyi's: whether
> "ILAMB metrics" in `communication-internal` meant the package
> specifically or goodness-of-fit generally. If it meant the package,
> #18 becomes a stepping stone rather than the destination, and the
> ~2-3 day ILAMB integration returns to scope. Nothing here should be
> scheduled ahead of that answer.

### Scope gaps to reconcile

`communication-internal` marks two features "done" that are simpler
stand-ins in the code. Flagged so they are not later read as delivered:

| Feature | Doc says | Actual | Issue |
|---------|----------|--------|-------|
| ILAMB benchmarking | Done | Custom fit metrics (bias, R², residuals). Direction: extend the metrics, revisit ILAMB later — see above and Long-term. | #13 |
| 5-step EnKF loop | Done | Simple/scalar Kalman filter, no ensemble | #14 |
| PFT / soil / temperature perturbation | Listed | Only precipitation is codified | #3 |

### Long-term

| Item | Description |
|------|-------------|
| **Revisit ILAMB integration** | Deferred, not rejected — see the trigger conditions below. |
| **Sub-monthly GPP comparison** | Deferred with the monthly decision (#12). Revisit when a question needs diurnal or event-scale behaviour, when Kalman calibration needs a faster cadence, or when a defensible sub-monthly treatment of the partitioning negatives exists. |
| **CESM 3.x evaluation** | When CESM 3.x ships (est. late 2026), evaluate whether to maintain a separate coupled-model container. |
| **Pre-built case images** | Explore shipping a container with a pre-compiled CLM binary for common compsets. |
| **Multi-site batch runs** | Support running all 48 NEON sites in batch for systematic model evaluation. |

#### Revisiting ILAMB

Deferred rather than rejected. Recorded here so the decision can be
re-opened on evidence rather than re-litigated from scratch.

**What was verified (2026-08-25, in the container image):** `ilamb 2.7.3`
installs cleanly from conda-forge with a `py313` build matching the
image — **14 packages, 15 MB**, a one-line `environment.yml` change. It
will *not* pip-install, because `cf-units` needs `UDUNITS2_XML_PATH`;
conda-forge supplies it. Site (non-gridded) data is supported: `ndata`,
ILAMB's unstructured site dimension, appears 65 times in
`ILAMB.Variable`, so single-point NEON towers are not a mismatch. It
ships `ilamb-run`, `ilamb-fetch`, `ilamb-mean`, `ilamb-setup` and 16
confrontation modules, scoring Bias, RMSE, Seasonal Cycle, Spatial
Distribution, and Interannual Variability.

**Why we deferred:** ILAMB's advantage is comparability with other
land-model evaluations through its curated global reference datasets
(fetched via `ilamb-fetch`). This project evaluates against NEON tower
observations, which ILAMB does not ship — so we would be using it as a
scoring library over our own data and forfeiting the comparability that
justifies it. Its workflow is also config-file plus CLI producing an
HTML dashboard, where the Hubs are notebooks.

**Revisit if any of these become true:**

- The grant, a reviewer, or a collaborator expects **ILAMB-comparable
  scores** specifically, rather than goodness-of-fit generally.
- The project starts evaluating against **gridded or global reference
  data**, where ILAMB's curated collection becomes the point.
- **Multi-site batch runs** (above) land, making a standardized scored
  dashboard across 48 sites more valuable than bespoke notebook output.
- The extended `compute_fit` metrics prove insufficient in practice.

**Estimated cost if adopted:** ~2-3 days, net-new work absent from
Phases 0-5 — wiring NEON observations into ILAMB's site path and
surfacing its scores in the notebook.
