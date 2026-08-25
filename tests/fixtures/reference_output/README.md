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

## Reading them (Phase 1)

Because the copies use the old plain-`h1` naming, the **current**
`data_access.py` reader matches them with only a path change (S3 →
`reference-output/{site}.transient/lnd/hist/`). The `h1`→`h1a` fix is needed
only for reading *live* container output. See `docs/data-contract.md` §8.

## Local live sample (KONZ)

A completed KONZ run (new `h1a` naming) also exists at
`~/exsoil-baseline-konz/archive/lnd/hist/` — use it as the *live-output* sample
while wiring Phase 1, alongside these reference copies.
