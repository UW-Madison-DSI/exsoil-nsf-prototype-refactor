# Hub Integration Implementation Plan

**Status:** Phase 0 complete; Phase 1 ready for implementation
**Date:** 2026-07-10 (revised 2026-07-30 with Phase 0 findings)
**Author:** Steven Wangen
**Owner:** Steve / Abe (project reassigned from Maria per Eric Wait, 2026-05-29)

## Purpose

Finish the three-Hub implementation from `docs/communication-internal.docx`
so it runs against the **new container architecture** (standalone CTSM
5.4.043, native NEON input, in-container CESM runs) instead of the original
S3-fixture design.

This is a **data-rebind + validation** effort, not a redesign. CTSM already
runs to completion in the container (KONZ: 83 monthly history files in
337 s), and every Hub and the `analytics_modules/` backend already exist.
What remains is repointing them from the hardcoded UW S3 store to the
live/native flow, then validating.

## What the doc comments settled

From the July 9 comment thread in `communication-internal.docx` (Steve's
questions, Maria's answers):

| Question | Resolution | Source |
|----------|-----------|--------|
| S3 vs live/native data? | **Go native/live.** S3 is now an optional sample copy, not a requirement. Maria: "no strong need to make it from s3 or natively." | Comments 0/1, 3/4 |
| Hub 3 architecture? | **Confirmed 4-step loop:** 1 NEON input → 1 perturbed copy → run CESM on both → t-test the two outputs. | Comments 7/8 |
| Which parameter does the Kalman filter target? | **GPP** (Gross Primary Productivity). | Comments 5/6 |
| Sample sites? | **5 stations** (corrected from 3), copies in a shared Google Drive folder (portable, not network-restricted). | Comment 2 |
| Ownership? | **Reassigned to Steve;** Maria is now a reference. | Comments 9/10 |

## Deliverable definition (MVP scope)

A self-contained **local Docker image**, **single-user, no auth**, in which
all three Hubs run end-to-end against **live NEON input + in-container CESM
output**, validated on the **5 sample sites**.

**Out of scope (follow-on):** VM hosting, multi-user, user/password auth, and
S3 credential-rotation security work.

## Confirmed current state

- **CESM runs to completion** in the container for KONZ (proven, `docs/benchmarks/konz-performance-baseline.md`). This is the foundation Phase 0 depends on.
- All three Hub notebooks exist: `notebooks/Data_Hub.ipynb` (Hub 1), `notebooks/Modeling_Hub.ipynb` (Hub 2), `notebooks/Design_Hub_v2.ipynb` + `notebooks/pft_perturbation_comparison.ipynb` (Hub 3).
- Backend exists: `analytics_modules/` (Kalman filter, misfit, perturbation manager, data access).
- Perturbation tooling exists: `cesm-tools/site_and_regional/run_neon_v2.py` (transform functions + CLI flags).
- **Everything reads from S3.** `analytics_modules/data_access.py` hardcodes `endpoint_url="https://campus.s3.wisc.edu"`, `COS_ACCESS_KEY_ID/COS_SECRET_ACCESS_KEY`, and the path `archive_1/{site}.transient/lnd/hist/`. Nothing points at native output yet. Verified still true on 2026-07-30.
- **The current readers match zero live files** (Phase 0 finding). Both `data_access.py` and `run_neon_v2.py:264` filter on the stale `clm2.h1.{year}` pattern; live output is `clm2.h1a.YYYY-MM-DD-SSSSS`. See the corrected data-convention section below.

## The data convention — corrected by Phase 0

> **Revised 2026-07-30.** This section previously claimed the S3 and live-run
> layouts shared the same filename convention. **They do not.** Phase 0
> compared them against a real KONZ run and found the readers match **zero**
> live files. The rebind is still low-risk, but it is not a pure prefix swap.

| | S3 fixtures / reference copies | Live in-container run |
|---|---|---|
| Root | `archive_1/{site}.transient/lnd/hist/` | `{output_root}/archive/lnd/hist/` |
| Per-site subdir | yes (`{site}.transient/`) | **no** |
| Monthly stream | `h0` | **`h0a`** |
| Daily stream | `h1` | **`h1a`** |
| Daily filename | `...clm2.h1.YYYY-MM-DD-00000.nc` | `...clm2.h1a.YYYY-MM-DD-01800.nc` |
| NetCDF version | 3 (`engine="scipy"`) | unconfirmed, may be 4 |

Three consequences for Phase 1:

1. **Both the stream token and the date token change.** The current filter
   `{site}.transient.clm2.h1.{year}` is wrong on two axes, not one.
2. **The reader must handle both conventions.** The reference copies (the
   Phase-5 validation oracle) use the *old* plain `h0`/`h1` naming, so the
   reader cannot simply switch to the new one — it has to read both.
3. **Two files need the fix**, not one: `analytics_modules/data_access.py`
   *and* `cesm-tools/site_and_regional/run_neon_v2.py` (~line 264).

Still true and still helpful: `plot_soil_profile_timeseries()` in
`data_access.py` **already has a local branch**. The rebind is flipping the
default source and generalizing the two S3-only readers.

Full detail: [`docs/data-contract.md`](../data-contract.md).

---

## Phase 0 — Data contract + fixtures (~0.5 day) — ✅ DONE

**Status:** Complete (issue #5). `docs/data-contract.md` is written and
grounded in a real KONZ run; fixtures scaffolding exists at
`tests/fixtures/reference_output/` with `.nc` payloads gitignored. The 343 MB
of reference copies are staged locally. Two follow-ups remain open: populating
the fixtures from Drive, and deciding whether to version `.nc` files via LFS.

**Goal:** pin down where live CESM output lands and stage the validation
oracle.

1. Run a KONZ transient case to completion (already proven).
2. Document the output directory and filename pattern in a new
   `docs/data-contract.md`: the `lnd/hist/` path, `h1` stream naming, variable
   list, dimensions (`time`, `levgrnd`, `levsoi`), units, and a sample
   `ncdump -h` header.
3. Pull the 5-station reference copies from Drive into
   `tests/fixtures/reference_output/{site}/`. These become the acceptance
   oracle for later phases.

**Acceptance:** `docs/data-contract.md` exists and a reviewer can locate a
live `.nc` history file from the documented path without guessing.

---

## Phase 1 — Rebind the data-access layer (~1 day)

**Goal:** one function the notebooks call regardless of source; local by
default, S3 opt-in.

**Files:** `analytics_modules/data_access.py` **and**
`cesm-tools/site_and_regional/run_neon_v2.py`

Task 0 below is new, added from Phase 0's findings. It is the substance of the
phase — without it the reader returns an empty Dataset rather than an error,
which is the failure mode most likely to waste an afternoon.

### 0. Fix the history-file pattern (do this first)

Both files currently filter on `{site}.transient.clm2.h1.{year}`, which
matches zero live files.

- `data_access.py`: generalize the stream token and date form.
- `run_neon_v2.py` (~line 264): same fix to `fname_prefix`.
- Support **both** conventions — new-style `h0a`/`h1a` for live output and
  legacy `h0`/`h1` for the reference copies. A stream parameter defaulting to
  the daily stream, resolved per source, is enough; do not hardcode either.
- Daily files are `YYYY-MM-DD-SSSSS` (seconds-of-day, e.g. `01800`), not
  `{year}`. Glob the seconds field rather than assuming `00000`.
- Live path is `{output_root}/archive/lnd/hist/` with **no** per-site
  subdirectory; S3 is `archive_1/{site}.transient/lnd/hist/`. The per-site
  segment is part of the source-specific path builder, not a shared constant.

### 1. Add the local reader

`open_ctsm_hist_local(site, year, output_root, *, input_label="transient")`,
mirroring `open_ctsm_hist_from_s3()` but reading local files with `glob` +
`xr.open_mfdataset` and the same `drop_variables`.

**Verify the engine.** The S3 fixtures were NetCDF-3, hence `engine="scipy"`.
Live files may be NetCDF-4, where `scipy` fails outright. Confirm against a
real file and select the engine per source (or let xarray infer) rather than
copying `"scipy"` forward.

### 2. Add the dispatch entry point

`open_ctsm_hist(site, year, *, source=None, ...)`. Resolve `source` from env
var `CTSM_DATA_SOURCE` (`"local"` default, `"s3"` fallback) and
`CTSM_OUTPUT_ROOT` for the local path.

### 3. Repoint the plotting helper

In `plot_soil_profile_timeseries()`, remove the hardcoded
`sim_path = "s3://clm-demonstration/..."` (~line 280) and derive it from the
same source resolution. The local branch already exists; make it the default.

### 4. Keep S3 working, but optional

`get_s3_client`, `get_storage_options`, and `open_ctsm_hist_from_s3` stay for
the opt-in path. Do **not** raise on missing `COS_*` creds unless
`source="s3"`.

**Acceptance:** with `CTSM_DATA_SOURCE=local` and no COS credentials set,
`open_ctsm_hist("KONZ", 2018)` returns a **non-empty** xarray Dataset from the
live run (assert on variable presence and time length, not just a successful
call — an empty glob otherwise passes silently). Reading a reference copy with
legacy `h1` naming also returns data. With `source="s3"` the old path still
works.

---

## Phase 2 — Hub 1: Data Analysis (~0.5 day)

Simplest Hub first, per Maria's recommendation.

**File:** `notebooks/Data_Hub.ipynb`

1. Replace direct S3 helper calls with the Phase-1 `open_ctsm_hist(...)`.
2. Remove the preflight cell that hard-requires `COS_ACCESS_KEY_ID` /
   `COS_SECRET_ACCESS_KEY`.
3. Re-run all cells against the live KONZ output.

**Acceptance:** plots and histograms render from live output and match the
reference copy for KONZ within the Phase-5 tolerance (see Open Decisions).

---

## Phase 3 — Hub 2: Modeling / Kalman filter (~1 day)

**Files:** `notebooks/Modeling_Hub.ipynb`, `analytics_modules/kalman_filter.py`,
`analytics_modules/neon_eval_utils.py`, `analytics_modules/model_misfit.py`

1. Point the misfit/calibration workflow at native output via
   `open_ctsm_hist(...)`.
2. Confirm the filter's target variable is **GPP** (per Comment 6). Verify
   `calibrate_and_evaluate` / `compute_fit` operate on GPP against the NEON
   observed GPP series.
3. Validate misfit metrics (bias, residuals, R²) and the calibrated result
   against the reference `misfit_eval.ipynb` output on the sample sites.

**Acceptance:** misfit and Kalman-calibration numbers reproduce the
reference notebook's results within tolerance for at least 2 sites.

---

## Phase 4 — Hub 3: Experimentation (~1.5 days)

**Files:** `notebooks/Design_Hub_v2.ipynb`,
`notebooks/pft_perturbation_comparison.ipynb`,
`cesm-tools/site_and_regional/run_neon_v2.py`,
`analytics_modules/perturbation.py`

Wire the confirmed 4-step loop:

1. Take a single NEON input for a site.
2. Create one perturbed copy via `run_neon_v2.py` transform
   (`--transform-var --transform-method --transform-value`). **Precipitation
   is fully codified** — start there.
3. Run CESM on both (unperturbed + perturbed) live in the container. Both
   runs land in the Phase-0 output convention.
4. Apply the t-test to the two output series and report the difference.

Confirm the in-scope perturbation variable set (see Open Decisions). PFT is
handled via `perturbation.py` (surface-dataset edit), a different mechanism
from the DATM forcing transforms in `run_neon_v2.py`.

**Acceptance:** a single notebook run produces two CESM outputs and a t-test
result for a precipitation perturbation on one site, with no manual steps.

---

## Phase 5 — Multi-site validation + hardening (~1 day)

1. Run all three Hubs across the 5 sample sites.
2. Compare live output to the Drive reference copies at the agreed tolerance.
3. Address the known Mac/Linux "loading / server disconnection" slowness
   noted in the doc (suspected container arch / resource issue; the
   arm64 rebuild may already mitigate — verify).
4. Update `docs/getting-started.md` to document the native/local data flow
   and demote the S3 path to optional.

**Acceptance:** all three Hubs run clean on all 5 sites from a fresh
container pull, documented in an updated getting-started guide.

---

## Open decisions to confirm with Jingyi

These do not block starting Phases 0–2, but are needed before Phase 4
closes:

1. **Perturbation variable scope for the MVP** — is precipitation-only
   acceptable, with PFT / soil type / temperature as follow-ons? The doc is
   inconsistent (one section literally reads "PFT, Soil type and `[]`";
   others list precip and temperature).
2. **Validation tolerance** — how close must a live in-container run match
   the 5-station reference copies to count as passing? A live re-run will
   not be bit-identical to the archived output.
3. **The 5 site codes** — confirm the exact NEON sites (KONZ is the proven
   baseline).

## Risks

- **Silent empty reads.** A stale glob pattern matches zero files and
  `open_mfdataset` on an empty list fails late or yields an empty Dataset,
  which downstream Hub code may treat as "no data for that year" rather than a
  bug. Assert on variable presence and non-zero time length at the reader
  boundary, not in the notebooks.
- **Dual naming conventions persist.** Live output is `h0a`/`h1a`; the
  reference copies are legacy `h0`/`h1`. This is not transitional — Phase 5
  validation needs both readable simultaneously.
- **Non-identical reproduction.** Live runs won't bit-match archived
  reference output; without an agreed tolerance, "validation" is undefined.
  Mitigation: settle decision #2 before Phase 2 sign-off.
- **Compute time.** KONZ is 337 s single-threaded per run; Hub 3 needs two
  runs per site, and Phase 5 covers 5 sites. Budget wall-clock accordingly.
- **PFT/soil perturbation maturity.** Forcing (precip) transforms are
  codified; surface-dataset perturbations (PFT/soil) are less exercised.
  Keep them out of the MVP critical path unless Jingyi requires them.

## Estimated effort

~5.5 engineer-days across Phases 0–5, plus the three Jingyi confirmations.
Phases are sequential by dependency (0 → 1 gate everything; 2 → 3 → 4 run in
Hub order per Maria's recommendation).
