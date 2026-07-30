# Hub Integration Implementation Plan

**Status:** Ready for implementation
**Date:** 2026-07-10
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
- **Everything reads from S3.** `analytics_modules/data_access.py` hardcodes `endpoint_url="https://campus.s3.wisc.edu"`, `COS_ACCESS_KEY_ID/COS_SECRET_ACCESS_KEY`, and the path `archive_1/{site}.transient/lnd/hist/`. Nothing points at native output yet.

## The data convention that makes the rebind clean

The S3 and live-run layouts share the **same filename convention** — this is
what makes the repoint low-risk:

- S3 today: `archive_1/{site}.transient/lnd/hist/{site}.transient.clm2.h1.{YYYY-MM}*.nc`
- Live run: `{output_root}/{site}.transient/lnd/hist/{site}.transient.clm2.h1.{YYYY-MM}*.nc`

`plot_soil_profile_timeseries()` in `data_access.py` **already has a local
branch**. The rebind is flipping the default source and generalizing the two
S3-only readers.

---

## Phase 0 — Data contract + fixtures (~0.5 day)

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

**File:** `analytics_modules/data_access.py`

1. Add `open_ctsm_hist_local(site, year, output_root, *, input_label="transient")`
   mirroring `open_ctsm_hist_from_s3()` but reading local files with
   `glob` + `xr.open_mfdataset` (engine `"scipy"`, same `drop_variables`).
2. Introduce a single dispatch entry point:
   `open_ctsm_hist(site, year, *, source=None, ...)`. Resolve `source` from
   an env var `CTSM_DATA_SOURCE` (`"local"` default, `"s3"` fallback) and a
   `CTSM_OUTPUT_ROOT` env var for the local path.
3. In `plot_soil_profile_timeseries()`, remove the hardcoded
   `sim_path = "s3://clm-demonstration/..."` (line ~280) and derive it from
   the same source resolution. The local branch already exists; make it the
   default.
4. Keep all S3 functions intact but no longer required: `get_s3_client`,
   `get_storage_options`, `open_ctsm_hist_from_s3` stay for the opt-in path.
   Do **not** raise on missing `COS_*` creds unless `source="s3"`.

**Acceptance:** with `CTSM_DATA_SOURCE=local` and no COS credentials set,
`open_ctsm_hist("KONZ", 2018)` returns an xarray Dataset from the live run.
With `source="s3"` the old path still works.

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
