# ExSOIL Container Infrastructure: Presentation Walkthrough

A suggested flow for walking someone through the project's progress.
Assumes the audience is not deeply familiar with the CESM/CTSM
software stack. Total time: 10-15 minutes plus questions.

---

## 1. The goal (1 minute)

Start with what the project does, not how it works.

**Key points:**

- The ExSOIL project runs land surface simulations at real ecological
  observatory sites (NEON network, 48 sites across the U.S.) and
  compares the model's predictions against what the tower instruments
  actually measured.
- The variables we care about: soil temperature, soil moisture,
  carbon fluxes, sensible heat flux. These are what tell us whether
  the model's representation of soil processes is accurate.
- The computational environment is delivered as a Docker container.
  Researchers pull the container, launch JupyterLab, and work with
  simulations and data. No installation, no configuration, no
  dependency headaches.

## 2. Where we started (1-2 minutes)

Explain the problem we inherited.

**Key points:**

- The previous container (`escomp/cesm-lab-neon`, last updated
  October 2022) was built on end-of-life software: CentOS 8,
  Python 3.7, Intel-only binaries.
- Team members on Apple Silicon Macs (M1-M4) could not run it
  reliably. It either crashed or ran under processor emulation
  (slow, unstable).
- The NEON tower site workflow (the core research capability) was
  non-functional. It had been assembled from an undocumented mix of
  component versions that no longer worked together.
- In short: the container could not run on modern hardware, and
  even on compatible hardware, it could not perform its primary
  research function.

## 3. How the pieces fit together (2-3 minutes)

Use the architecture guide and lineage chart to orient the audience
before describing what changed.

**Open:** `docs/ctsm-architecture-guide/lineage-chart.png`

**Key points:**

- CESM is the full Earth system model (atmosphere, ocean, ice, land).
  It is very large and we only need the land component.
- CTSM is the standalone land model. It includes CLM (the land
  simulation code), CIME (the build/case management system), and
  the NEON tower workflow. CTSM is what NCAR recommends for
  single-site land experiments.
- The old container used the full CESM and grafted in NEON support
  from a development branch. That graft broke as the components
  diverged.
- Our rebuild uses standalone CTSM 5.4, which includes NEON
  natively. This aligns with NCAR's intended approach and eliminates
  the custom graft.

**If questions arise about CESM vs CTSM:**
`docs/ctsm-architecture-guide/ctsm-architecture-guide.html` has
four diagrams covering the component hierarchy, build pipeline,
data flow, and NEON workflow.

## 4. What we built (3-4 minutes)

Walk through the deliverables. Concrete outcomes, not process.

**Multi-platform container:**

- Runs natively on both Intel/AMD and Apple Silicon (arm64). Docker
  selects the right architecture automatically.
- Ubuntu 24.04 base (supported through 2029), Python 3.13, current
  scientific libraries.
- All compiled dependencies (MPICH, HDF5, NetCDF, compilers) come
  from conda-forge pre-built binaries. Build time dropped from ~45
  minutes to ~5 minutes.
- Exact package versions pinned via conda-lock for reproducibility
  across platforms.

**NEON simulation pipeline (end-to-end):**

- 48 NEON tower sites discoverable and configurable.
- The model compiles from Fortran source inside the container
  (~100 seconds).
- A 1-day transient simulation at KONZ (Konza Prairie, Kansas) runs
  to completion and produces valid CLM output: 31 variables, 48
  half-hourly time steps.
- Output includes the core research variables: soil temperature
  (TSOI), soil moisture (H2OSOI), sensible heat flux (FSH).
- Output is readable directly with xarray for analysis in Python.

**Validation:**

- 90-test automated suite across three tiers: environment checks,
  case management workflow, full model compilation and analysis.
- All 90 tests pass on native arm64.

**Documentation:**

- 6 Architecture Decision Records (why each technical choice was made)
- Architecture guide with diagrams (for domain experts, not just
  engineers)
- Decision trail documenting the path from the initial problem
  through each resolution
- NSF progress report, roadmap, changelog, getting-started guide

## 5. Challenges worth mentioning (1-2 minutes)

These give context for why it took the effort it did.

**The NEON gap:** NEON tower support was developed for standalone
CTSM starting in 2021. It was never part of any CESM 2.x release
and will not enter CESM until version 3.x (targeted late 2026).
The previous container masked this by using an undocumented custom
build. Our rebuild exposed the gap, which led to the architectural
decision to move to standalone CTSM.

**Data infrastructure migration:** NCAR migrated their data servers
between the CTSM 5.4.002 release (December 2025) and the current
development branch. The release shipped before configuration files
were updated to point at the new server. This was not documented in
the release notes. We resolved it by upgrading to a newer CTSM tag
(5.4.043) and building a pre-download script with retries and
server fallback.

**MPI compatibility:** The NEON workflow defaults to a serial MPI
mode, but conda-forge's MPICH libraries are always present. The two
conflict at runtime. We patched the defaults to use real MPICH,
which works correctly with the standard launcher.

## 6. What is next (1 minute)

**Near-term:**

- Extend validation to longer run periods and additional NEON sites
- Connect the analysis notebooks (Modeling_Hub, Design_Hub) to
  simulation output for model-data comparison workflows
- Cache input data on university infrastructure to eliminate the
  slow download step for new users

**Medium-term:**

- Merge to main and publish the updated container image
- CI/CD integration for automated testing on both architectures
- Evaluate multi-site batch runs for systematic model evaluation

---

## Reference documents to have open

| Document | When to use it |
|----------|---------------|
| [lineage-chart.png](../ctsm-architecture-guide/lineage-chart.png) | Section 3: explaining how components relate |
| [ctsm-architecture-guide.html](../ctsm-architecture-guide/ctsm-architecture-guide.html) | If architecture questions go deeper |
| [plain-language-explanation.md](../decisions/003-neon-input-data-resolution/plain-language-explanation.md) | If data availability questions come up |
| [infrastructure-progress-report.md](infrastructure-progress-report.md) | Leave-behind: formal summary of all work |
| [ROADMAP.md](../ROADMAP.md) | "What's next" questions |

## If asked: "Can you show me?"

The most compelling demonstration is the Getting Started notebook
inside the running container:

```bash
docker run --rm -p 8888:8888 exsoil-ctsm543-test
```

Open the URL in a browser, then open
`notebooks/Getting_Started_CTSM_NEON.ipynb`. This shows NEON site
discovery, case configuration, and environment verification without
needing to run a full simulation (which takes ~15 minutes for data
download and build).

For a full simulation demo, run the pre-download script first (the
slow step), then the notebook can create and build a case
interactively.
