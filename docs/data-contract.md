# CTSM Output Data Contract (NEON sites)

**Status:** Established from a completed KONZ run
**Date:** 2026-07-15
**Phase:** Hub Integration Phase 0 (issue #5)
**Author:** Steven Wangen

This document pins down **where live CTSM output lands and what it contains**,
so the Hub notebooks and `analytics_modules/` can be repointed from the S3
fixtures to native/in-container output (Phase 1, issue #6). It is derived from
an actual completed KONZ transient run, not from assumption.

## Source of truth for this document

- Case: `KONZ.transient`, compset `IHist1PtClm60Bgc`, transient, 2018-01 → 2024-11.
- Output inspected at `~/exsoil-baseline-konz/` on the host (the persisted copy
  of the container's output root). This is the same run documented in
  `docs/benchmarks/konz-performance-baseline.md`.
- Headers read with `ncdump -h` against real `.nc` files.

## 1. Where output lands

In the container, `run_neon_v2.py` resolves the output root to **`/home/user`**
by default (see `run_neon_v2.py` lines 727-728, where an unset
`CIME_OUTPUT_ROOT` falls back to `/home/user`). For one site the layout is:

```
{output_root}/                         # /home/user in-container
├── {site}.transient/                  # the CIME case directory
│   └── run/                           # live run dir: raw output during the run
│       ├── {site}.transient.clm2.h0a.YYYY-MM.nc
│       ├── {site}.transient.clm2.h1a.YYYY-MM-DD-SSSSS.nc
│       └── {site}.transient.clm2.r.YYYY-MM-DD-SSSSS.nc   # restart
└── archive/                           # CIME short-term archive (DOUT_S_ROOT)
    └── lnd/hist/                       # <-- canonical location to READ history
        ├── {site}.transient.clm2.h0a.YYYY-MM.nc
        ├── {site}.transient.clm2.h0i.YYYY-MM.nc
        └── {site}.transient.clm2.h1a.YYYY-MM-DD-SSSSS.nc
```

**Read history from `archive/lnd/hist/`.** After a run completes, CIME's
short-term archiver (`st_archive`) moves history files out of `run/` into
`archive/lnd/hist/`. During or immediately after a run only the tail may remain
in `run/`; the full time series lives in the archive.

### Relationship to the old S3 layout

| | Path |
|---|---|
| **S3 (old fixtures)** | `s3://clm-demonstration/archive_1/{site}.transient/lnd/hist/` |
| **Live (native)** | `{output_root}/archive/lnd/hist/` |

Two differences Phase 1 must handle: the bucket prefix `archive_1` becomes the
local `archive`, and the old layout nests history under a per-site
`{site}.transient/` subdirectory while the single-case live archive does not.
`DOUT_S_ROOT` is the CIME variable that controls the archive root.

## 2. History streams

A completed KONZ run produced these streams (counts for the full 2018-01 →
2024-11 run):

| Stream | Cadence | Aggregation | Filename pattern | Count | Example |
|--------|---------|-------------|------------------|-------|---------|
| `h0a` | Monthly | Time-averaged | `{site}.transient.clm2.h0a.YYYY-MM.nc` | 83 | `KONZ.transient.clm2.h0a.2018-07.nc` |
| `h0i` | Monthly | Instantaneous | `{site}.transient.clm2.h0i.YYYY-MM.nc` | 83 | `KONZ.transient.clm2.h0i.2018-07.nc` |
| `h1a` | Daily | Time-averaged | `{site}.transient.clm2.h1a.YYYY-MM-DD-SSSSS.nc` | 2557 | `KONZ.transient.clm2.h1a.2018-07-01-01800.nc` |
| `r`   | — | Restart | `{site}.transient.clm2.r.YYYY-MM-DD-SSSSS.nc` | 1 | `KONZ.transient.clm2.r.2024-12-01-00000.nc` |

- The `SSSSS` token in daily/restart filenames is seconds into the day
  (`01800` = 30 min).
- The `a` / `i` suffix means time-**a**veraged vs. **i**nstantaneous. The Hubs
  use the averaged streams (`h0a`, `h1a`).
- `h1a` daily files carry **48 half-hourly timesteps** (`time = 48`). `h0a`
  monthly files carry **1 timestep** (the monthly mean).

> ### ⚠️ Naming discrepancy — critical for Phase 1
> The current readers filter on the **stale plain-`h1`** convention and will
> match **zero** live files:
> - `analytics_modules/data_access.py` builds `{site}.transient.clm2.h1.{year}`
> - `cesm-tools/site_and_regional/run_neon_v2.py:263-264` builds the same
>
> Live files are `.clm2.h1a.` / `.clm2.h0a.`. Phase 1 must update the stream
> token (`h1` → `h1a`, add `h0a`) **and** the daily date format (`{year}` →
> `{year}-MM-DD-SSSSS`) in **both** files, not just repoint the directory.

## 3. Grid dimensions (single-point NEON case)

```
lndgrid = 1        gridcell = 1     column = 1     pft = 1
levgrnd = 25       (ground levels, used by TSOI)
levsoi  = 20       (soil levels, used by H2OSOI)
time    = UNLIMITED  (48 per h1a daily file; 1 per h0a monthly file)
```

`levgrnd` depths (m), top-of-column downward:

```
0.01, 0.04, 0.09, 0.16, 0.26, 0.40, 0.58, 0.80, 1.06, 1.36, 1.70, 2.08,
2.50, 2.99, 3.58, 4.27, 5.06, 5.95, 6.94, 8.03, 9.795, 13.33, 19.48,
28.87, 41.998
```

The Hubs typically use only the shallow soil range (e.g. `levgrnd[0:9]`,
`levsoi[0:15]`).

## 4. Variables used by the Hubs

All three are present in both `h0a` (monthly) and `h1a` (daily):

| Variable | Dims | Units | Long name | Used by |
|----------|------|-------|-----------|---------|
| `TSOI`   | `(time, levgrnd, lndgrid)` | `K` | soil temperature | Hub 1 (soil profile) |
| `H2OSOI` | `(time, levsoi, lndgrid)`  | `mm3/mm3` | volumetric soil water | Hub 1 (soil profile) |
| `GPP`    | `(time, lndgrid)` | `gC/m^2/s` | gross primary production | Hub 2 (Kalman target) |

Notes:
- `TSOI` is in **Kelvin**; existing plotting code subtracts 273.15 for °C.
- Because `lndgrid = 1`, code that indexes `[:, :, 0]` on `TSOI`/`H2OSOI`
  still works unchanged.
- **GPP** is the Kalman filter target for Hub 2 (per the July 9 doc comments);
  for daily model-vs-observation misfit use the `h1a` stream.

## 5. Time encoding

```
float time(time) ;
  time:long_name = "time at exact middle of time_bounds" ;
  time:units = "days since 2018-01-01 00:00:00" ;
  time:calendar = "gregorian" ;   (via time_bounds / mcdate)
```

Also present: `mcdate` (int `YYYYMMDD`), `mcsec` (seconds of day),
`time_bounds(time, nbnd)`. Files are NetCDF; open with xarray. The S3 fixtures
were NetCDF-3 (`engine="scipy"`); confirm the engine works for live files too
during Phase 1 (they may be NetCDF-4).

## 6. Reproducing / locating a file

To locate a live history file from a completed run (host example):

```
ls ~/exsoil-baseline-konz/archive/lnd/hist/KONZ.transient.clm2.h1a.2018-07-01-*.nc
ncdump -h <that file>
```

In-container equivalent after a `run_neon_v2.py` run:

```
ls /home/user/archive/lnd/hist/{site}.transient.clm2.h1a.*.nc
```

## 7. Sample `ncdump -h` excerpt (KONZ h1a, 2018-07-01)

```
dimensions:
    lndgrid = 1 ;  levgrnd = 25 ;  levsoi = 20 ;  time = UNLIMITED ; // (48)
variables:
    float time(time) ;
        time:units = "days since 2018-01-01 00:00:00" ;
    float GPP(time, lndgrid) ;
        GPP:units = "gC/m^2/s" ;
    float TSOI(time, levgrnd, lndgrid) ;
        TSOI:units = "K" ;
    float H2OSOI(time, levsoi, lndgrid) ;
        H2OSOI:units = "mm3/mm3" ;
```

## 8. Reference copies (validation oracle)

The 5-site reference copies (Maria's S3/Drive set) are now staged locally at
`archive/archive/{SITE}.transient/lnd/hist/` (gitignored — 343 MB). Evaluated
2026-07-15:

| Property | Reference copies | Live container output (§1-7) |
|----------|------------------|------------------------------|
| Sites | ABBY, CLBJ, CPER, KONZ, TALL | any NEON site |
| Streams | plain `h0` (monthly), `h1` (daily) | `h0a` / `h1a` (suffixed) |
| Filename | `{site}.transient.clm2.h1.YYYY-MM-DD-00000.nc` | `...clm2.h1a.YYYY-MM-DD-01800.nc` |
| Format | NetCDF-3 (64-bit offset), `engine="scipy"` | verify (may be NetCDF-4) |
| Coverage | 2018-01-01 → 2022-04-01 (CPER → 2022-03) | 2018-01 → 2024-11 (KONZ) |
| Grid / vars | levgrnd=25, levsoi=20, 48 steps/day; TSOI, H2OSOI, GPP | identical |
| Contents | **model output only** | model output |

**What matches:** grid, dimensions, the three Hub variables (TSOI/H2OSOI/GPP),
and units are identical to live output. The reference naming (`h1`, NetCDF-3)
is exactly what the *current* `data_access.py` expects — so reference reading
works with the existing reader; only *live* reading needs the `h1`→`h1a` fix.

**Two caveats:**
1. **Model output only — no observations.** These copies contain the
   `transient` model output but not the `evaluation` (NEON observed) product,
   and the `atm/hist` forcing dirs are empty. Hub 2's Kalman/misfit step
   compares model GPP against *observed* GPP, which is **not** in this set and
   must be sourced separately (NEON API, the `evaluation_files` product, or
   NCAR's eval files).
2. **Older model generation.** Plain `h0`/`h1` naming indicates an earlier
   CTSM/CLM version than the live container (CTSM5.4/CLM6). Treat these as a
   **shape / plausible-range oracle**, not bit-level or tight-numeric ground
   truth. Confirm the generating version with Maria before setting a
   validation tolerance.

## Handoff to Phase 1 (issue #6)

1. Update the history filter in **both** `data_access.py` and
   `run_neon_v2.py`: stream `h1` → `h1a` (and add `h0a` for monthly), date
   token `{year}` → the daily `YYYY-MM-DD-SSSSS` form.
2. Read from `{output_root}/archive/lnd/hist/`; handle the missing per-site
   subdirectory relative to the old S3 `archive_1/{site}.transient/` layout.
3. Verify the xarray engine for live files (NetCDF-3 `scipy` vs NetCDF-4).
