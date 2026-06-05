# Image Generation Prompt: CESM/CTSM Version Lineage Diagram

## Style

Clean, technical diagram in the style of a GitHub network graph or a
dependency tree. White background, thin lines, small readable labels.
Horizontal time axis (left to right, 2020-2026). Vertical swim lanes
for each product/component. Use color coding consistently. No
decorative elements. Suitable for printing in a technical report.

## Layout

**X-axis:** Time, left to right. Years labeled: 2020, 2021, 2022, 2023, 2024, 2025, 2026.

**Y-axis (swim lanes, top to bottom):**

1. **CESM** (dark gray, #282728) -- "Full Earth System Model"
2. **CTSM** (red, #c5050c) -- "Standalone Land Model"
3. **CLM** (green, #3d7a38) -- "Land Model Code (Fortran)"
4. **CIME** (blue, #0479a8) -- "Build and Run System"
5. **NEON** (purple, #9b59b6) -- "Tower Site Workflow"
6. **Docker** (orange, #e67e22) -- "Container Images"
7. **Data** (gray, #888) -- "Input Datasets (CMIP)"

## Releases (shown as labeled nodes on their swim lane)

### CESM lane:
- **CESM 2.2.0** (2020): solid node
- **CESM 2.2.2** (mid-2021): solid node, connected to 2.2.0 by solid line
- **CESM 3.x beta08** (early 2026): dashed/hollow node, connected by dashed line from 2.2.2. Label: "Not yet released"

### CTSM lane:
- **ctsm5.1.dev114** (Nov 2022): small node, label "First NEON release"
- **ctsm5.2.005** (Aug 2024): medium node
- **ctsm5.3.021** (Jan 2025): small node
- **ctsm5.4.002** (Dec 2025): large/bold node (this is our current version)
- Connected left to right by solid line

### CLM lane (two parallel branches):
- **Upper branch (maintenance):** "release-clm5.0" starting ~2020, dashed line extending to "clm5.0.37" at May 2024. Label below: "Maintenance only. No NEON. Used by CESM 2.2.x"
- **Lower branch (development):** Forks downward from clm5.0 around early 2021. "clm5.1" label, solid line extending right to "clm6.0" at Dec 2025. Label below: "Active development. NEON support. Used by CTSM."
- Show the fork visually (branch splits)

### CIME lane:
- **cime5.x** (2020-2024): solid line. Label: "Uses import imp (Python <3.12 only)"
- **cime6.0** (mid-2024): node
- **cime6.1** (late 2025): node. Label: "Python 3.12+ OK"
- Connected as one continuous line with version bump markers

### NEON lane:
- **PR #1278** (Feb 2021): node with label "NEON usermods added to CTSM master"
- Solid line extending right to **48 sites** (Dec 2025)
- Label along the line: "Active development: usermods, surface datasets, run_tower"
- Important: this line should NOT connect upward to any CESM 2.x release. It only connects to CTSM releases.

### Docker lane:
- **escomp/cesm-lab-neon** (Oct 2022): node. Label: "Custom build, amd64 only"
- **ExSOIL container** (Jun 2026): bold node. Label: "CTSM 5.4, arm64+amd64, Python 3.13"

### Data lane:
- **CMIP6** (2020-present): solid green bar spanning full width. Label: "Fully published on NCAR servers"
- **CMIP7** (2025-2026): short red dashed bar at right end. Label: "NOT YET PUBLISHED" in red

## Connection lines (vertical, showing composition)

These are the critical lines that show what each release contains.
Draw them as thin vertical or diagonal lines connecting nodes across
swim lanes.

**CESM 2.2.0 and 2.2.2 connect downward to:**
- CLM: release-clm5.0 (upper maintenance branch)
- CIME: cime5.x
- NOT connected to NEON (mark this gap explicitly with a red X or "none")
- Connected to CMIP6 data bar

**ctsm5.4.002 connects downward to:**
- CLM: clm6.0 (lower development branch)
- CIME: cime6.1
- NEON: 48 sites
- Connected to CMIP7 data bar (with a warning indicator since data is not published)

**escomp/cesm-lab-neon Docker image connects upward to:**
- CESM 2.2.0 (dashed line, partial)
- A point on the CTSM development line between 5.1.dev and 5.2 (dashed line, label: "custom graft")
- This represents the non-standard nature of that image

**ExSOIL container connects upward to:**
- ctsm5.4.002 (solid line)

**CESM 3.x connects downward to:**
- CLM: clm6.0
- CIME: 6.x
- NEON: via CTSM (dashed, since 3.x is not released)
- CMIP7 data bar

## Key visual callouts

1. A red X or "not connected" label between CESM 2.2.x and the NEON lane, making it obvious that NEON was never in CESM 2.x.

2. The CLM branch fork (clm5.0 splits into clm5.1) is a critical visual element. It explains why CESM 2.2 and CTSM 5.4 use different CLM versions.

3. The CMIP7 "NOT PUBLISHED" bar at the bottom right should be visually prominent (red, dashed border) since it represents the current blocker.

4. The ExSOIL container node should be the most prominent element on the Docker lane (bold border, slightly larger) since it's the thing this whole project produces.

## What this diagram should make immediately obvious to a reader

1. CESM releases are bundles of specific component versions (CLM + CIME + CAM + POP + etc.)
2. CTSM releases are similar bundles but without atmosphere/ocean/ice
3. NEON support was developed on the CTSM development branch, never on the CESM 2.x line
4. The old Docker image was a non-standard hybrid; our new container uses a standard CTSM release
5. There is a data availability gap blocking live simulations with CTSM 5.4
6. CESM 3.x will eventually bring NEON support into the full Earth system model
