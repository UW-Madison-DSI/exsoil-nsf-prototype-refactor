# ADR-0006: Set CLM_CMIP_ERA=cmip6 for NEON Runs

**Status:** Proposed (pending validation)
**Date:** 2026-06-04
**Decision makers:** Steven Wangen

## Context

CTSM 5.4's NEON tower simulations fail during input data download
because the `CLM_CMIP_ERA` flag defaults to `cmip7` for IHist
compsets, but the NEON usermods set SSP3-7.0 forcing dates. This
creates a request for CMIP7-era SSP forcing files that do not exist.
CMIP7 datasets only cover the historical period (1850-2023); future/SSP
data is not yet available.

The full investigation trail is documented in
[decision 003](../decisions/003-neon-input-data-resolution/003-neon-input-data-resolution.md).

## Decision

**Set `CLM_CMIP_ERA=cmip6` explicitly when creating NEON tower cases.**

This forces the namelist generator to resolve CMIP6-era datasets for
SSP-period forcings (aerosols, nitrogen deposition, ozone, population
density), which are available on NCAR's public data servers.

## Rationale

The ctsm5.4.002 release notes explicitly state:

> "For future periods and N deposition we continue to use CMIP6 data
> from CESM2."

And:

> "Defaults to cmip7 except in compsets containing SSP for which it
> defaults to cmip6 because there are no future-period datasets yet
> available for CMIP7."

The NEON case falls through a gap in the auto-detection: it uses an
IHist compset (not SSP), so `CLM_CMIP_ERA` defaults to `cmip7`, but
the DATM forcing dates are in the SSP period (2018-2021). Setting
`cmip6` explicitly aligns with the stated intent of the flag for
SSP-period data.

## Implementation

Add to `run_neon_v2.py`'s case creation, after `create_newcase`:

```python
xmlchange("CLM_CMIP_ERA=cmip6")
```

Or add to the NEON defaults usermods `shell_commands`:

```bash
./xmlchange CLM_CMIP_ERA=cmip6
```

## Consequences

- NEON simulations should be able to download all required input data
  from NCAR's public servers.
- CLM6 physics runs with CMIP6-era forcing data instead of CMIP7. For
  the historical/near-present period (2018-2021) that NEON covers,
  the practical difference is expected to be small (both eras provide
  observed-based datasets for this period).
- When NCAR publishes CMIP7 SSP datasets in the future (likely with
  CESM 3.x), this override can be removed and the default behavior
  re-evaluated.
- The fix does not address the NEON-specific surface dataset
  (`surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.nc`), which may
  need to come from the NEON science server or be generated. Testing
  will determine if `CLM_CMIP_ERA=cmip6` resolves this file as well.

## Related

- [Decision trail 003](../decisions/003-neon-input-data-resolution/003-neon-input-data-resolution.md):
  full investigation of the data availability issue
- [ADR-0005](0005-standalone-ctsm.md): decision to use standalone CTSM
- [Decision brief 002](../decisions/002-ctsm-version-selection.md):
  CTSM version comparison (5.4 vs 5.2)
