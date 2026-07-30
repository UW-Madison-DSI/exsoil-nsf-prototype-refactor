# Hub Integration — Progress Report

**Status:** Active — planning complete, implementation starting
**Date:** 2026-07-17
**Author:** Steven Wangen
**Audience:** ExSOIL project team (shareable)

## Summary

The infrastructure phase is done: a multi-arch container runs standalone CTSM
5.4.043 and completes a NEON tower simulation end-to-end. We are now in the
**scientific-capability phase** — getting the three analysis Hubs (Data
Analysis, Modeling, Experimentation) running on live/native data across 5 NEON
sites. This is a data-rebind and validation effort, not a redesign.

Planning for that phase is complete and tracked; the first execution phase (data
contract) is done. This report is the shareable status snapshot.

## Status at a glance

| Item | Status |
|------|--------|
| Multi-arch container, CTSM 5.4.043 | ✅ Done |
| KONZ NEON simulation, end-to-end | ✅ Done (83 monthly files, full 2018-2024 run) |
| Phase objectives / charter | ✅ Written (`docs/phase-objectives/`) |
| Implementation plan (6 phases) + tracker | ✅ Written (`docs/hub-integration-plan/`, epic #11) |
| **Phase 0** — data contract + reference copies | ✅ Done (see below) |
| **Phase 1** — rebind data-access layer | ⏳ Ready to start (#6) |
| **Phases 2-5** — Hubs 1/2/3 + validation | ⏳ Planned (#7-#10) |
| Scope decisions with Jingyi | ⚠️ 5 pending (see below) |

## What we completed this cycle (Phase 0)

- **Data contract** (`docs/data-contract.md`) — documents the live CTSM output
  layout, streams, variables (TSOI, H2OSOI, GPP), dimensions, and units,
  grounded in the real KONZ run.
- **5 sample sites confirmed:** KONZ (baseline), ABBY, CPER, TALL, CLBJ.
- **Reference copies received and evaluated** (343 MB, staged locally,
  gitignored). Findings:
  - They are the right sites with the right structure and variables — they plug
    into the existing reader with a path change.
  - **Model output only** — no NEON observations included.
  - **Older model generation** (legacy `h1`/`h0` naming, 2018-2022 coverage) —
    a shape/plausible-range oracle, not exact ground truth.
- **Naming discrepancy identified:** live output uses `h1a`/`h0a` streams while
  the current code (and the reference copies) use plain `h1`/`h0`. Phase 1 must
  handle both. Catching this now avoids a silent mid-implementation failure.

## Gaps surfaced between the source doc and reality

Mapping `communication-internal` against the code turned up four items that need
resolution. Two are features marked "done" in the doc that are actually simpler
stand-ins:

| Feature | Doc says | Actual | Tracked |
|---------|----------|--------|---------|
| ILAMB benchmarking | done | Custom fit metrics (bias, R², residuals); no ILAMB | #13 |
| 5-step EnKF loop | done | Simple/scalar Kalman filter; no ensemble | #14 |
| Observed data for evaluation | (assumed) | Not in the reference copies; must be sourced | #12 |
| PFT / soil / temperature perturbation | listed | Only precipitation is codified | #3 + MVP scope |

These are scope decisions, not missing engineering — except observed-data
sourcing (#12), which is a real prerequisite for validating Hub 2.

## Decisions pending (Jingyi)

1. **Observed-GPP source** for Hub 2 (#12) — NEON API vs. `evaluation_files` vs.
   NCAR eval files. *Blocks Phase 3 validation.*
2. **ILAMB** (#13) — accept the custom metrics, or build real ILAMB?
3. **EnKF** (#14) — accept the simple Kalman filter, or build a true EnKF?
4. **Perturbation scope** — precipitation-only for the MVP, with PFT/soil/temp
   as follow-ons?
5. **Validation tolerance** — how close must live runs match the (older-model)
   reference copies to pass?

## Next steps

- Start **Phase 1** (#6): add a local reader and source-agnostic entry point in
  `analytics_modules/data_access.py`; fix the `h1`→`h1a` naming for live output.
  This is not blocked by the pending decisions.
- Get decisions 1-3 in front of Jingyi (they set the scope of Hub 2 and whether
  any net-new work is needed).

## Reference documents

- Phase charter — `docs/phase-objectives/`
- Implementation plan — `docs/hub-integration-plan/`
- Data contract — `docs/data-contract.md`
- Execution tracker — GitHub epic #11 (issues #5-#14)
