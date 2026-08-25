# Reference output fixtures (validation oracle)

The **reference copies** of CTSM output for the 5 sample NEON sites, used to
validate that live in-container runs reproduce known-good results (Hub
Integration Phases 2-5). See `docs/data-contract.md` §8 for the full evaluation
and `docs/hub-integration-plan/hub-integration-plan.md` for how they are used.

## Where the data lives

Staged locally (2026-07-15) at the repo root, **gitignored** (343 MB):

```
reference-output/{SITE}.transient/lnd/hist/
├── {SITE}.transient.clm2.h0.YYYY-MM.nc            # monthly (51 files/site)
└── {SITE}.transient.clm2.h1.YYYY-MM-DD-00000.nc   # daily (~1552 files/site)
```

This directory (`tests/fixtures/reference_output/`) holds the documentation
only; the `.nc` payloads are not versioned (Git LFS if the team ever wants
them tracked).

## Sites (5) — confirmed set

| Site | NEON location | Coverage | Status |
|------|---------------|----------|--------|
| KONZ | Konza Prairie, KS | 2018-01 → 2022-04 | present + live baseline at `~/exsoil-baseline-konz/` |
| ABBY | Abby Road, WA | 2018-01 → 2022-04 | present |
| CPER | Central Plains, CO | 2018-01 → 2022-03 | present |
| TALL | Talladega National Forest, AL | 2018-01 → 2022-04 | present |
| CLBJ | LBJ National Grassland, TX | 2018-01 → 2022-04 | present |

## What the copies contain (and don't)

**Present:** `transient` **model output** — daily (`h1`) and monthly (`h0`)
streams with `TSOI` (K), `H2OSOI` (mm3/mm3), and `GPP` (gC/m²/s) on the
standard single-point grid (levgrnd=25, levsoi=20, 48 half-hourly steps/day).
NetCDF-3 (`engine="scipy"`), plain `h0`/`h1` naming.

**Two gaps to know about:**
1. **Model output only — no observations.** No `evaluation_files/` (NEON
   observed data) and the `atm/hist` forcing dirs are empty. Hub 2's misfit
   step needs *observed* GPP, which must be sourced separately.
2. **Older model generation.** Plain `h0`/`h1` (vs the live container's
   `h0a`/`h1a`) means an earlier CTSM/CLM version. Use as a shape /
   plausible-range oracle, not exact ground truth. Confirm the version with
   Maria before fixing a validation tolerance.

## Reading them

Nothing special is required — the reader handles these and live output alike:

```python
from analytics_modules import open_ctsm_hist, find_ctsm_hist_files

ds = open_ctsm_hist("CLBJ", 2019, output_root="/path/to/repo")
```

`find_ctsm_hist_files()` probes the known archive layouts and resolves the
stream token from what is on disk, so the copies' legacy `h1`/`h0` naming and
the container's `h1a`/`h0a` both work. The engine is picked per file from its
magic number, which matters here: these copies are NetCDF-3 (CDF-2) while live
output is CDF-5.

Both conventions are supported permanently, not transitionally — Phase 5
compares live output *against* these copies, so both must stay readable.

## Local live sample (KONZ)

A completed KONZ run (current `h1a` naming, CDF-5) exists at
`~/exsoil-baseline-konz/archive/lnd/hist/` — the live-output counterpart to
these copies, and what `tests/test_data_access_local.py` reads when
`CTSM_TEST_LIVE_ROOT` points at it.
