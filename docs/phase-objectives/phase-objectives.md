# Phase Objectives: Scientific Capability on the Working Container

**Status:** Active
**Date:** 2026-07-16
**Author:** Steven Wangen
**Owner:** Steve / Abe

## Where we are

The infrastructure phase is complete. The project now has a self-maintained,
multi-architecture (amd64 + arm64) container running **standalone CTSM
5.4.043**, and a NEON tower simulation runs end-to-end to completion (KONZ
baseline: 83 monthly history files, full 2018-2024 transient run). See
`docs/ROADMAP.md` and `docs/multiarch-rebuild-report/` for that work.

This document marks the phase boundary: **infrastructure (done) → scientific
capability (this phase).** It states what this phase is trying to achieve and
how we will know it succeeded. Execution detail lives in the
[implementation plan](../hub-integration-plan/hub-integration-plan.md) and the
GitHub epic (#11); this is the charter above them.

## Objective

Deliver the three analysis **Hubs** running against **live/native data** on the
working container, validated across **5 NEON sites**. Each Hub realizes one of
the three capabilities motivated by Jingyi's NSF proposal:

| Hub | Capability | What it does |
|-----|-----------|--------------|
| **1 — Data Analysis** | Data access | Explore NEON + CTSM data (plots, histograms, soil profiles) |
| **2 — Modeling** | Model evaluation | Evaluate model fit and calibrate via a Kalman filter (target: **GPP**) |
| **3 — Experimentation** | Scenario analysis | Perturb an input, run CTSM on perturbed + unperturbed, compare via t-test |

The Hubs, their analytics backend, and the perturbation tooling already exist;
this phase repoints them from the original S3 fixtures to live/native data and
validates them. It is a **data-rebind + validation** effort, not a redesign.

**Sample sites (5):** KONZ (baseline), ABBY, CPER, TALL, CLBJ.

## Success criteria

This phase is done when:

1. All three Hubs run **end-to-end on live/in-container data** with no manual
   data-staging steps.
2. Each Hub runs **clean across all 5 sample sites** from a fresh container
   pull.
3. Hub outputs **validate against the reference copies** within an agreed
   tolerance (see open decisions — tolerance is shape/plausible-range, not
   bit-level, because the references are from an older model generation).
4. Hub 2's Kalman/misfit step evaluates model **GPP against observed GPP**
   (pending an observation source; see dependencies).
5. The workflow is documented so a new user can run all three Hubs from the
   getting-started guide.

## Scope

**In scope (MVP):**
- Local Docker image, **single-user, no authentication**
- The three Hubs on the 5 sample sites, live/native data
- Precipitation perturbation for Hub 3 (fully codified today)

**Out of scope (follow-on):**
- VM hosting and multi-user access
- User/password authentication and the S3 credential-rotation security work
- PFT / soil-type / temperature perturbations (unless promoted by Jingyi)

## Open decisions (need Jingyi)

- **Perturbation variable scope** — is precipitation-only acceptable for the
  MVP, with PFT / soil type / temperature as follow-ons?
- **Validation tolerance** — how close must a live run match the reference
  copies to pass? (Framed as shape/range given the version gap below.)

## Dependencies & known constraints

- **Observed GPP for Hub 2.** The reference copies are **model output only** —
  they do not include NEON observations, and the forcing dirs are empty. Hub 2's
  misfit step needs *observed* GPP, which must be sourced separately (NEON API,
  the `evaluation_files` product, or NCAR's pre-computed eval files). This is
  the main external dependency for the phase.
- **Reference copies are an older model generation.** They use the legacy
  `h1`/`h0` naming (vs the container's `h1a`/`h0a`) and cover 2018-2022, so they
  serve as a shape / plausible-range oracle, not exact ground truth. Confirm the
  generating version with Maria.
- **Model vs observation is not exact by construction.** Model GPP is "gross";
  tower GPP is derived from measured net flux via partitioning. Even a perfect
  model would not match exactly — reinforcing fit-quality over exact agreement.

## Scope discrepancies to reconcile

While mapping `communication-internal` against the code, three features are
described (two marked "done") that do not match what is actually implemented.
These are **scope decisions for Jingyi**, not silent omissions — flagged here so
they are not later read as delivered:

| Feature (per `communication-internal`) | Actual state | Decision / action |
|----------------------------------------|--------------|-------------------|
| **ILAMB metrics** (marked done) | No ILAMB in code; Hub 2 uses a custom fit framework (bias, R², residuals) | Accept custom metrics or build real ILAMB — issue #13 |
| **5-step EnKF loop** (marked done) | Code has a simple/scalar Kalman filter; no ensemble or cycle | Accept simple KF or build true EnKF — issue #14 |
| **Perturbation: PFT, soil type, temperature** | Only precipitation is codified today | MVP = precip; PFT (#3), soil, temperature deferred pending scope |
| **Observed data for evaluation** | Reference copies are model-output only | Source observed GPP — issue #12 (blocks Phase 3 validation) |

The three-hub integration itself (Phases 0-5) is concretely planned and
tracked; these four items are the remaining gaps between the source doc and the
plan.

## Related documents

- [Hub integration implementation plan](../hub-integration-plan/hub-integration-plan.md) — phases, tasks, acceptance criteria
- [Data contract](../data-contract.md) — live output schema + reference-copy evaluation
- GitHub epic **#11** — execution tracker (phase issues #5–#10)
- `docs/communication-internal.docx` — the July 9 decisions that settled this phase's direction
