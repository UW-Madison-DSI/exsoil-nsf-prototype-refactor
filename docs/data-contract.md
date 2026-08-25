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

> **Corrected 2026-07-30.** This section originally listed a single live
> layout. There are **three**, because the archive root depends on which
> wrapper produced the run. The layout documented below as "live" is the one
> `run_tower` produces, which is what the KONZ baseline used — but the Hubs
> drive `run_neon_v2.py`, which archives somewhere else entirely.

| Producer | Path |
|---|---|
| **S3 (old fixtures)** | `s3://clm-demonstration/archive_1/{site}.transient/lnd/hist/` |
| **Reference copies (as delivered)** | `reference-output/{site}.transient/lnd/hist/` |
| **`run_tower`** (KONZ baseline) | `{output_root}/archive/lnd/hist/` |
| **`run_neon_v2.py`** (what the Hubs use) | `{dirname(base_case_root)}/archive/{site}/{control\|VAR_VALUE}/lnd/hist/` |

`DOUT_S_ROOT` is the CIME variable controlling the archive root.
`run_neon_v2.py:1086-1089` overrides it per experiment:

```python
archroot = os.path.join(os.path.dirname(base_case_root), "archive")
exp_name = f"{transform_var}_{transform_value}" if transform_var else "control"
archroot_exp = os.path.join(archroot, self.name, exp_name)
case.set_value("DOUT_S_ROOT", archroot_exp)
```

Two consequences. The root is derived from `base_case_root`, **not** from
`output_root`, so they are not interchangeable. And the `control` vs
`PRECTmms_1.2` segment is exactly the run separation Phase 4 needs in order to
compare a perturbed run against an unperturbed one — it already exists, and no
other document mentions it.

Rather than making callers pick, `analytics_modules.find_ctsm_hist_files()`
probes all of these layouts and both stream naming conventions.

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

> ### Naming discrepancy — resolved in Phase 1
> **Historical, kept because the reasoning still governs the code.** The
> readers used to filter on the plain-`h1` convention and matched **zero**
> live files; live output is `.clm2.h1a.` / `.clm2.h0a.`.
>
> The fix was *not* a rename. The S3 fixtures and the reference copies
> legitimately use `h1`/`h0` and must stay readable for Phase 5 validation,
> so both conventions have to work at once — this is not a migration that
> finishes. `analytics_modules.find_ctsm_hist_files()` therefore resolves
> the token by probing what is on disk, newest naming first
> (`STREAM_TOKENS`), rather than switching to the new one.
>
> Anyone "simplifying" that probe back to a single token will silently break
> reading of the validation oracle.

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
`time_bounds(time, nbnd)`. Files are NetCDF; open with xarray.

**Engine — resolved in Phase 1, and not what this document originally
guessed.** Live output is **CDF-5** (magic bytes `CDF\x05`), verified on disk;
the reference copies are CDF-2 (`CDF\x02`). `scipy` reads CDF-1/2 only, so it
fails on live files, and `h5netcdf` fails too because CDF-5 is not HDF5.
`netcdf4` reads both. `analytics_modules.data_access` selects the engine per
file from its magic number rather than assuming one.

## 6. Reproducing / locating a file

To locate a live history file from a completed run (host example):

```
ls ~/exsoil-baseline-konz/archive/lnd/hist/KONZ.transient.clm2.h1a.2018-07-01-*.nc
ncdump -h <that file>
```

In-container equivalent. Note these differ by wrapper — `run_neon_v2.py`
inserts site and experiment segments, `run_tower` does not:

```
# run_tower
ls /home/user/archive/lnd/hist/{site}.transient.clm2.h1a.*.nc

# run_neon_v2.py (what the Hubs drive); exp is "control" or e.g. "PRECTmms_1.2"
ls {dirname(base_case_root)}/archive/{site}/{exp}/lnd/hist/{site}.transient.clm2.h1a.*.nc
```

Rather than choosing, use the reader, which probes both:

```python
from analytics_modules import find_ctsm_hist_files
files = find_ctsm_hist_files("KONZ", 2018)
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
`reference-output/{SITE}.transient/lnd/hist/` (gitignored — 343 MB). Evaluated
2026-07-15:

| Property | Reference copies | Live container output (§1-7) |
|----------|------------------|------------------------------|
| Sites | ABBY, CLBJ, CPER, KONZ, TALL | any NEON site |
| Streams | plain `h0` (monthly), `h1` (daily) | `h0a` / `h1a` (suffixed) |
| Filename | `{site}.transient.clm2.h1.YYYY-MM-DD-00000.nc` | `...clm2.h1a.YYYY-MM-DD-01800.nc` |
| Format | NetCDF-3 CDF-2, reads with `scipy` | **CDF-5** (`CDF\x05`), needs `netcdf4` |
| Coverage | 2018-01-01 → 2022-04-01 (CPER → 2022-03) | 2018-01 → 2024-11 (KONZ) |
| Grid / vars | levgrnd=25, levsoi=20, 48 steps/day; TSOI, H2OSOI, GPP | identical |
| Contents | **model output only** | model output |

**What matches:** grid, dimensions, the three Hub variables (TSOI/H2OSOI/GPP),
and units are identical to live output. **What differs is naming and binary
format**, and since Phase 1 the reader handles both without the caller
choosing: the stream token is probed from disk and the engine is selected per
file from its magic number. Reading a reference copy and reading live output
are the same call.

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

## Phase 1 outcome (issue #6, closed)

The three handoff items this section originally listed are done, and two of
the three turned out differently than written. Recorded because the
departures are what the code now depends on.

| Handoff item | Outcome |
|---|---|
| Update the history filter in both files: `h1` → `h1a` | **Not a rename.** Both conventions must work simultaneously, so the token is probed rather than switched. A straight rename would have broken the S3 path and the reference copies. |
| Read from `{output_root}/archive/lnd/hist/` | **Insufficient.** That is the `run_tower` layout; `run_neon_v2.py` inserts site and experiment segments. `find_ctsm_hist_files()` probes all known layouts rather than assuming one. See §1. |
| Verify the xarray engine (NetCDF-3 vs NetCDF-4) | **Neither.** Live output is CDF-5. `scipy` cannot read it and `h5netcdf` cannot either. The engine is chosen per file from its magic number. See §5. |

A third file also carried the stale pattern and was named nowhere in the
plan or the issue: `analytics_modules/neon_notebook_wrapper.py:34`.

Entry points: `open_ctsm_hist()`, `open_ctsm_hist_local()`, and
`find_ctsm_hist_files()`, local by default via `CTSM_DATA_SOURCE` and
`CTSM_OUTPUT_ROOT`. Covered by `tests/test_data_access_local.py`.
