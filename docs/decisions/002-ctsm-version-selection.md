# Decision Brief: CTSM Version Selection

**Status:** Decided (CTSM 5.4.002, with caveats)
**Date:** 2026-06-03
**Author:** Steven Wangen

## Summary

After deciding to use standalone CTSM instead of full CESM (ADR-0005),
we needed to choose which CTSM release tag to use. Both CTSM 5.4.002
(December 2025) and CTSM 5.2.005 (August 2024) were built, tested,
and evaluated against the full 90-test validation suite and a live
simulation attempt. Neither version works end-to-end without caveats.

**Decision:** Use CTSM 5.4.002. It passes all 90 container tests,
has a clean codebase (no six.py workarounds, modern CIME, Python 3.13
native), and represents the current state of CTSM development. The
one blocker, missing input data on NCAR's servers, is an upstream
issue that will resolve as NCAR publishes CMIP7 datasets.

## What We Tested

### CTSM 5.4.002

| Capability | Result |
|-----------|--------|
| Container build | Passes |
| Python 3.13 | Works natively (CIME 6.1, no `import imp`) |
| NEON usermods | 48 sites at `usermods_dirs/clm/NEON/` |
| case.build (Fortran compilation) | Passes on arm64 |
| Test suite | 90/90 pass |
| Bundled six.py issues | None |
| **Live simulation** | **Fails: input data not on NCAR servers** |

The simulation downloaded 8 GB of available data from NCAR's FTP
servers before failing. The missing files are CMIP7-era datasets with
2025 timestamps:

- `surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.nc` (CTSM 5.4-specific NEON surface data)
- `clmforc.Li_2025_CMIP7_SSP3CMIP6_hdm_0.5x0.5_simyr1850-2100_c250717.nc` (CMIP7 fire forcing)
- Multiple ozone, crop calendar, dust, and nitrogen deposition files

These are part of the CMIP7 data pipeline tied to the CESM 3.x release
(still in beta). NCAR has not published them to the public FTP/SVN
servers. This is an upstream issue, not a container problem.

### CTSM 5.2.005

| Capability | Result |
|-----------|--------|
| Container build | Passes |
| Python 3.13 | **Fails: CIME XML parsing error** (`_Element` vs `Element`) |
| NEON usermods | ~47 sites at `usermods_dirs/NEON/` (different path) |
| Bundled six.py | **Present** (shadows conda six, breaks dateutil) |
| Input data availability | Expected to work (10-month-old release) |
| **Live simulation** | **Not tested** (blocked by Python 3.13 incompatibility) |

CTSM 5.2 uses an older CIME (6.0.x) that has an XML parsing
incompatibility with Python 3.13. The `xml.etree.ElementTree` module
in Python 3.13 rejects `lxml._Element` objects where it expects
`xml.etree.ElementTree.Element`. This causes `create_newcase` to fail.

Fixing this would require either pinning Python back to 3.11-3.12
(re-introducing the version constraint we removed) or patching CIME's
XML handling.

## Why 5.4 Over 5.2

| Factor | CTSM 5.4 | CTSM 5.2 |
|--------|-----------|-----------|
| Container tests | 90/90 pass | Blocked by Python 3.13 CIME error |
| Python 3.13 | Works | Incompatible |
| six.py workaround | Not needed | Required |
| Usermods path | `clm/NEON/` (new layout) | `NEON/` (old layout) |
| CIME version | 6.1.x (current) | 6.0.x (older, Python 3.13 issues) |
| CLM physics | CLM 6.0 | CLM 5.1 |
| Input data | **Not yet published** | Expected available |
| Simulation run | Blocked (data) | Blocked (Python compat) |

Both versions are blocked from running live simulations, but for
different reasons. CTSM 5.4's blocker (missing data) is an external
dependency that will resolve on its own as NCAR publishes CMIP7
datasets. CTSM 5.2's blocker (Python incompatibility) would require
us to downgrade Python or patch CIME, both of which are regressions
from work we already completed.

The 5.4 container is a better foundation:
- Clean codebase (no workarounds for six.py, Python version, or CIME XML)
- 90/90 tests passing
- Modern CIME and CLM physics
- The data issue resolves without any code changes on our side

## What Works Today

With CTSM 5.4, everything works except running a simulation to
completion with real forcing data:

- Container builds natively on arm64 and amd64
- JupyterLab launches and serves notebooks
- All Python imports, compilers, MPI, and NetCDF libraries verified
- NEON sites discoverable (48 sites listed)
- CIME case creation and setup workflow functional
- Fortran model compilation produces cesm.exe
- Scientific analysis stack (xarray, cartopy, matplotlib) operational
- Getting Started notebook runs cleanly

## What Is Blocked

Running a live CTSM simulation at a NEON site. This requires NCAR to
publish the CMIP7-era input datasets that CTSM 5.4 references. There
is no workaround other than using an older CTSM version (which
introduces its own incompatibilities) or manually provisioning the
missing files from an alternative source.

## Next Steps

1. **Report the data availability issue to ESCOMP.** File a GitHub
   issue on ESCOMP/CTSM documenting which files are missing from the
   public servers for ctsm5.4.002.

2. **Monitor for data publication.** When NCAR publishes CMIP7
   datasets (likely tied to the CESM 3.x release timeline), the
   simulation pipeline should work without any container changes.

3. **Investigate alternative data sources.** The NEON-specific forcing
   data may be available on `storage.neonscience.org` even if the
   global CLM input data isn't. A targeted investigation of which
   specific files are available vs. missing could narrow the gap.

4. **University S3 cache.** If we can obtain the required files from
   any source (NCAR collaborators, direct generation, alternative
   servers), caching them on the university S3 (`campus.s3.wisc.edu`)
   would provide a reliable data source independent of NCAR's
   publication timeline.

5. **Re-evaluate when CTSM 5.4.x or 5.5 ships.** A point release may
   fix the data availability issue or provide alternative dataset
   references.
