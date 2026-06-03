# ADR-0005: Replace CESM with Standalone CTSM

**Status:** Accepted
**Date:** 2026-06-03
**Decision makers:** Steven Wangen
**Supersedes:** CESM 2.2.2 checkout in current Dockerfile (ADR-0002)

## Context

The multi-arch container rebuild (ADR-0001 through ADR-0004) successfully
modernized the base image, achieved native arm64 support, and produced a
working CESM 2.2.2 build with 89/89 tests passing. However, the project's
primary use case, the NEON tower site workflow, does not function because
CESM 2.2.2's CLM component (`release-cesm2.2.04`, from the `release-clm5.0`
maintenance line) predates NEON support entirely.

Research (documented in the
[decision brief](../decisions/001-neon-site-compatibility/001-neon-site-compatibility.md))
established that:

- The NEON tower workflow was developed exclusively on CTSM's `master`
  branch starting February 2021 (PR #1278), well after the CESM 2.2
  release line was cut.
- No CESM 2.x release has ever included NEON support. No backport is
  planned.
- The original `escomp/cesm-lab-neon` Docker image was a custom,
  undocumented build that grafted a newer CTSM development branch onto
  a CESM 2.2 framework. It was not a standard release.
- NCAR's official documentation and tutorials frame NEON as a standalone
  CTSM feature. The NCAR CTSM Tutorial teaches NEON via standalone CTSM,
  not within CESM.
- CESM 3.x (which will include NEON natively) was targeted for spring
  2026 but has slipped; the latest beta tag is from April 2026 with no
  release date announced.

Five options were evaluated (see decision brief for full analysis).

## Decision

**Replace the CESM 2.2.2 checkout with a standalone CTSM checkout.**

Use a current CTSM release tag (e.g., `ctsm5.2.x` or latest stable) that
includes the NEON tower workflow natively. CTSM's own `Externals.cfg` pulls
in only the components needed for land-surface modeling: CIME (build
system), DATM (data atmosphere), MOSART (river routing), and stub
components for ocean/ice/wave.

## Decision Drivers

- The NEON tower workflow is the project's primary use case and must work.
- NCAR designed and maintains the NEON workflow as a standalone CTSM
  feature. Using it that way aligns with the intended architecture.
- The project runs CLM in I-compset mode (land-only with data atmosphere),
  which is exactly what standalone CTSM is designed for.
- The full CESM components (CAM, POP, CICE, CISM, WW3) are present in
  the current container image but are never compiled, configured, or
  executed. They add ~3-4 GB to the image for no functional benefit.
- Waiting for CESM 3.x has no firm timeline and blocks current work.

## Options Considered

| Option | Description | Why not chosen |
|--------|-------------|----------------|
| A: Graft usermods | Copy NEON configs from newer CTSM into CESM 2.2.2 | Compatibility not guaranteed; maintenance burden tracking cross-version configs |
| B: Newer CLM tag | Pin just CLM to newer CTSM within CESM 2.2.2 | Mixing component versions is unsupported; could break the build |
| C: Bundle in repo | Maintain our own site configs | High effort; diverges from community; must maintain surface datasets manually |
| D: CESM 3.x | Upgrade to next major CESM release | Not yet released (spring 2026 target slipped); high effort; essentially a second rebuild |
| **E: CTSM standalone** | **Replace CESM with standalone CTSM** | **Chosen** |

## What Changes

### Dockerfile Stage 2 (the only stage that changes)

The current Stage 2 clones CESM 2.2.2 and checks out ~15 component
repositories (CAM, POP, CICE, CISM, CLM, MOSART, WW3, etc.). This
changes to clone CTSM and check out only ~5 components (CLM, CIME,
DATM, MOSART, stubs).

The `cesm-config/` machine configuration files need porting to CTSM's
version of CIME (which may differ in XML schema and available options).

The PIO2 source patches (disabling filter macros) and GCC compatibility
flags (`-fallow-argument-mismatch`, `-fallow-invalid-boz`,
`-D_FillValue=NC_FillValue`) may or may not still be needed with CTSM's
newer PIO and NetCDF integration. This must be tested.

### Stages 1 and 3 (unchanged)

The base environment (Ubuntu 24.04, Miniforge, conda-forge scientific
stack) and the application layer (notebooks, analytics_modules,
run_neon_v2.py) are independent of whether the model source tree is CESM
or CTSM. The conda lockfiles, environment.yml, and CI workflow carry over.

### run_neon_v2.py

The script resolves paths relative to `CESMROOT` and imports from
`ctsm.path_utils.path_to_ctsm_root()`. In a CTSM standalone checkout,
the directory layout differs:

- `CESMROOT` becomes `CTSMROOT` (or equivalent)
- `cime_config/usermods_dirs/NEON/` exists in CTSM (this is the fix)
- CIME lives at a different relative path within the source tree
- `tools/site_and_regional/` may have moved to a different location

These path adjustments are the primary code changes needed.

### Test suite

The 89-test suite needs re-validation. Tier 0 (smoke tests) and Tier 2
(analysis tests) should pass with minimal changes since they test the
conda environment and Python stack, not the model source tree. Tier 1
(case creation) and the Tier 2 case.build test will need updates for
CTSM's compset names, directory layout, and CIME version.

## What Is Lost

**Fully coupled simulations.** Without the full CESM framework, you
cannot run experiments where multiple Earth system components interact:
land surface changes feeding back into the atmosphere, ocean circulation
influencing coastal climate, ice sheet dynamics, etc. Specifically:

- No atmosphere model (CAM). CLM receives prescribed weather data and
  cannot influence atmospheric conditions. You cannot study how
  deforestation changes regional precipitation, how irrigation cools
  surface temperature and feeds back through clouds, or how agricultural
  expansion modifies the boundary layer.

- No ocean model (POP). Cannot study land-ocean interactions, coastal
  biogeochemistry, or how river discharge affects ocean salinity.

- No ice models (CICE, CISM). Cannot study ice sheet-climate feedbacks
  or sea ice impacts on land climate.

- No wave model (WW3). No coastal wave-surge interactions.

**This does not affect the project's current workflows.** All existing
notebooks run CLM in I-compset mode with data atmosphere (DATM), which
is exactly what standalone CTSM provides. The full CESM components in
the current image are never used.

**If the project's scope expands** to require coupled simulations in the
future, the options at that point would be:

1. Maintain a second container image with full CESM (3.x by then) for
   coupled experiments, alongside the CTSM container for NEON work.
2. Migrate to CESM 3.x entirely once it is released and stable.

This decision does not foreclose those paths; it prioritizes the
project's immediate needs.

## Consequences

- NEON tower workflow works natively with all 81 sites.
- Image size decreases by ~3-4 GB (no CAM/POP/CICE/CISM/WW3 source).
- Python version pin (3.11) likely removable if CTSM's CIME supports
  3.12+.
- PIO2 source patches may become unnecessary.
- `run_neon_v2.py` needs path updates for CTSM directory layout.
- Machine configs need porting to CTSM's CIME version.
- Test suite needs re-validation (89 tests, primarily Tier 1 and
  case.build changes).
- Coupled simulation capability is lost until a separate CESM 3.x
  container is created (if ever needed).

## Implementation Plan

1. Identify the appropriate CTSM release tag (latest stable with NEON
   support).
2. Replace the `git clone CESM` block in Dockerfile Stage 2 with
   `git clone CTSM` and its `checkout_externals`.
3. Port `cesm-config/` machine configs to CTSM's CIME version.
4. Test whether existing GCC/PIO patches are still needed; remove if not.
5. Update `run_neon_v2.py` path resolution for CTSM layout.
6. Update environment variables (`CESMROOT` to `CTSMROOT` or equivalent).
7. Re-run full test suite; fix and update tests as needed.
8. Validate NEON site workflow end-to-end (create case, setup, build for
   at least one site).

Estimated effort: 3-5 days.

## Related

- [Decision Brief](../decisions/001-neon-site-compatibility/001-neon-site-compatibility.md) --
  full analysis of all five options with comparison matrix
- [ADR-0002](0002-arm64-build-strategy.md) -- the CESM 2.2.2 build
  strategy this supersedes (Stage 2 only)
- [ADR-0001](0001-arm64-base-image.md) -- Ubuntu 24.04 base image
  (unchanged)
- [ADR-0003](0003-conda-environment-strategy.md) -- conda-lock strategy
  (unchanged)
- [ADR-0004](0004-distributed-computing-support.md) -- optional Dask
  layer (unchanged)
