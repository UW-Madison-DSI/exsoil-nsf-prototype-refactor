# Decision Trail: Resolving NEON Input Data Availability

**Status:** Investigation complete, fix identified
**Date:** 2026-06-04
**Author:** Steven Wangen

## Problem Statement

After migrating the container from CESM 2.2.2 to standalone CTSM 5.4
(ADR-0005), the NEON tower simulation workflow could not run to
completion. CIME's `check_input_data` failed because several input
files were not found on any of NCAR's public data servers.

The container was otherwise fully functional: 90/90 tests passing,
NEON sites discoverable, Fortran compilation working, Python analysis
stack healthy. The blocker was specifically the data download step
during `case.submit`.

## Investigation Trail

### Step 1: Initial simulation attempt (CTSM 5.4.002)

Ran `run_tower --neon-sites KONZ --run-type transient --setup-only`
inside the container. CIME downloaded 8 GB of available data before
failing on missing files:

```
surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.nc
clmforc.Li_2025_CMIP7_SSP3CMIP6_hdm_0.5x0.5_simyr1850-2100_c250717.nc
O3_surface.f09_g17.CMIP6-SSP3-7.0-WACCM.001.monthly.201501-210012.nc
```

Plus crop calendar, nitrogen deposition, dust, and snow optics files.
All had 2025 timestamps.

**Initial hypothesis:** NCAR hadn't published the input data for the
5.4 release yet.

### Step 2: Try CTSM 5.2.005 as a fallback

Built a container with the previous stable release. Found that CTSM
5.2's older CIME has an XML parsing incompatibility with Python 3.13
(`_Element` vs `Element` type error in `create_newcase`). This would
require re-pinning Python to 3.11-3.12, undoing work from the
multi-arch rebuild.

**Conclusion:** CTSM 5.2 introduces its own regressions (Python
compat, bundled six.py, different usermods path). Both versions were
blocked from running simulations.

See [decision brief 002](../002-ctsm-version-selection.md) for
the full comparison.

### Step 3: Probe NCAR data servers

Tested individual file URLs across NCAR's data servers:
- `ftp.cgd.ucar.edu` (FTP/wget)
- `svn-ccsm-inputdata.cgd.ucar.edu` (SVN)
- `storage.neonscience.org/neon-ncar/` (NEON-specific)

The NEON surface dataset (`surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.nc`)
returned 404 on all servers, including the NEON-specific Google Cloud
Storage backend. However, the NEON server did have pre-computed
transient run output for 45 sites (daily history files, 2018-2022).

**Finding:** NCAR publishes pre-computed NEON output but not the raw
input data needed to reproduce those runs with 5.4.

### Step 4: Examine the ctsm5.4.002 release notes

The release notes revealed a `CLM_CMIP_ERA` flag (cmip7 vs cmip6) and
explicitly stated:

> "These data are only available through the historical record
> (1850-2023), and are not available for future periods (presently
> known as SSP), for future periods and N deposition we continue to
> use CMIP6 data from CESM2."

And:

> "Defaults to cmip7 except in compsets containing SSP for which it
> defaults to cmip6 because there are no future-period datasets yet
> available for CMIP7."

### Step 5: Examine NEON usermods configuration

Inspected the NEON defaults usermods (`cime_config/usermods_dirs/clm/NEON/defaults/shell_commands`):

```bash
./xmlchange DATM_PRESAERO=SSP3-7.0
./xmlchange DATM_PRESNDEP=SSP3-7.0
./xmlchange DATM_PRESO3=SSP3-7.0
```

These set SSP3-7.0 forcing because NEON runs cover 2018-2021, which
extends past the historical period.

### Step 6: Deep research (multi-source verification)

Conducted a comprehensive search across GitHub issues, DiscussCESM
forums, NCAR documentation, and tutorial materials. Key findings:

1. **No one has successfully run NEON simulations with ctsm5.4.002 in
   Docker.** The `escomp/ctsm-neon` Docker image on Docker Hub hasn't
   been updated since October 2022.

2. **The NCAR CTSM Tutorial skipped 5.4 entirely.** The main branch
   uses CLM5.1, and the most recent tutorial (EMBER_Tutorial_2025,
   May 2025) jumped directly to CLM6.0. That tutorial runs on NCAR's
   cloud JupyterHub with pre-staged data, sidestepping public data
   download entirely.

3. **Known issues exist** with large SSP forcing files (6.5 GB aerosol
   deposition, 4 GB nitrogen deposition) causing Docker container runs
   to hang. CTSM developers discussed subsetting these for NEON sites.

4. **The `CLM_CMIP_ERA` auto-detection has a gap** for NEON cases: the
   IHist compset is not technically an SSP compset, so the flag
   defaults to `cmip7`, but the DATM settings request SSP3-7.0
   forcing dates, creating a request for CMIP7 SSP files that do not
   exist.

## Root Cause

The issue is a configuration mismatch, not missing data.

NEON transient runs use an IHist compset (`IHistClm60Bgc`) with SSP-era
forcing dates (`DATM_PRESAERO=SSP3-7.0`, etc.) because the simulation
period (2018-2021) extends past the end of the historical record (~2014).
The `CLM_CMIP_ERA` flag auto-detects based on the compset name. Since
IHist does not contain "SSP", the flag defaults to `cmip7`. This causes
the namelist generator to request CMIP7-era SSP forcing files that NCAR
has not produced yet (CMIP7 only covers the historical period through
2023).

If `CLM_CMIP_ERA` were set to `cmip6`, the namelist generator would
reference CMIP6-era forcing files that are available on NCAR's public
servers. The ctsm5.4 release notes explicitly say to use CMIP6 data
for SSP-period forcings.

## Fix

Set `CLM_CMIP_ERA=cmip6` explicitly for NEON runs. This can be done in:
- The NEON defaults usermods (`shell_commands`)
- Our `run_neon_v2.py` wrapper
- Or as an `xmlchange` in the case directory after creation

This is not a hack. The release notes say SSP-period data should use
CMIP6. The auto-detection just doesn't account for the NEON case where
an IHist compset uses SSP-era forcing dates.

## Remaining Unknowns

1. **Will `CLM_CMIP_ERA=cmip6` resolve all missing files?** The
   population density file and NEON surface dataset have "CMIP7" and
   "ctsm5.4.0" in their filenames, which may not have CMIP6
   equivalents. Testing the fix will confirm.

2. **Is this a known issue to ESCOMP?** No GitHub issue was found
   specifically describing this NEON + CLM_CMIP_ERA mismatch. It may
   be worth filing one after testing the workaround.

3. **Will the NEON surface datasets be published?** The `surfdata`
   files are specific to ctsm5.4.0 and may require ESCOMP to generate
   and upload them to `storage.neonscience.org`.
