# Image Generation Prompt: Dependency Tree with Timeline

## Concept

A hybrid diagram that combines a dependency tree (what contains what,
flowing top-down) with a timeline (when each release was published,
flowing left-to-right). Each release is a node positioned at its
correct date on the x-axis, with its components hanging below it as
a small subtree. This shows both composition and chronology in one view.

## Style

Clean technical diagram. White background. Thin lines, small readable
labels. No decorative elements. Suitable for printing in a report or
displaying in a presentation. Use consistent colors for each component
type across all trees.

## Layout

**X-axis:** Time, left to right. Light gridlines or tick marks at
each year: 2020, 2021, 2022, 2023, 2024, 2025, 2026.

**Y-axis:** Dependency depth. Top level = integration products (CESM
releases, CTSM releases, Docker containers). Lower levels = the
components they contain. Arrows or lines flow downward from parent
to children.

**Two horizontal bands:**

- **Upper band:** CESM releases (full Earth system). These are the
  larger, heavier assemblies with many components.
- **Lower band:** CTSM releases and Docker containers (land-only).
  These are lighter with fewer components.

This separation avoids visual clutter while keeping the time axis
shared.

## Nodes and Their Component Trees

### Upper band: CESM releases

**CESM 2.2.0** (positioned at ~2020)
```
CESM 2.2.0
├── CLM clm5.0 (green)
├── CIME 5.x (blue)
├── CAM (gray)
├── POP (gray)
├── CICE (gray)
├── CISM (gray)
├── MOSART (gray)
└── NEON: none (red X or absent)
```

**CESM 2.2.2** (positioned at mid-2021)
```
CESM 2.2.2
├── CLM clm5.0 (green)
├── CIME 5.x (blue)
├── CAM (gray)
├── POP (gray)
├── CICE (gray)
├── CISM (gray)
├── MOSART (gray)
└── NEON: none (red X or absent)
```
Note near this node: "Fixes GitHub SVN removal"

Connect CESM 2.2.0 to 2.2.2 with a horizontal arrow (version
progression).

**CESM 3.x** (positioned at ~2026, dashed border = not released)
```
CESM 3.x (beta, not released)
├── CLM 6.0 (green)
├── CIME 6.x (blue)
├── CAM7 (gray)
├── MOM6 (gray, replaces POP)
├── CICE6 (gray)
├── MOSART (gray)
├── NEON (purple, via CTSM)
└── CMEPS/NUOPC coupler (gray)
```

Connect CESM 2.2.2 to CESM 3.x with a dashed horizontal arrow
(long gap, version jump).

### Lower band: CTSM releases and containers

**escomp/cesm-lab-neon** (positioned at Oct 2022, orange border)
```
escomp/cesm-lab-neon (Docker)
├── CESM 2.2 framework (dashed line, gray)
│   ├── CIME 5.x
│   └── build system
└── dev CTSM branch (dashed line, red)
    ├── CLM ~5.1 dev
    └── NEON usermods (~47 sites)
```
Label: "Custom hybrid build. amd64 only. Not a standard release."

**CTSM 5.2.005** (positioned at Aug 2024)
```
ctsm5.2.005
├── CLM 5.1 (green)
├── CIME 6.0 (blue)
│   └── note: Python 3.13 incompatible
├── NEON ~47 sites (purple)
├── DATM/CDEPS (gray)
├── MOSART (gray)
└── CMEPS coupler (gray)
```

**CTSM 5.3.021** (positioned at Jan 2025, smaller node)
```
ctsm5.3.021
├── (similar to 5.2, not expanded)
```

**CTSM 5.4.002** (positioned at Dec 2025, prominent node)
```
ctsm5.4.002
├── CLM 6.0 (green)
├── CIME 6.1 (blue)
│   └── note: Python 3.12+ OK
├── NEON 48 sites (purple)
├── DATM/CDEPS (gray)
├── MOSART (gray)
├── CMEPS coupler (gray)
├── ParallelIO 2.6 (gray)
└── CMIP7 datasets (red, dashed)
    └── NOT PUBLISHED on public servers
```

**ExSOIL Container** (positioned at Jun 2026, bold border, wraps
CTSM 5.4.002)

This should visually enclose or extend CTSM 5.4.002, showing that
it inherits everything from CTSM and adds project-specific layers:

```
ExSOIL Container
└── CTSM 5.4.002 (everything above)
    + Ubuntu 24.04 / arm64 + amd64
    + conda-forge Python 3.13
    + xarray, cartopy, matplotlib, scipy
    + JupyterLab
    + analytics_modules (Kalman filter, misfit)
    + run_neon_v2 (perturbation experiments)
    + project notebooks
```

The key visual: ExSOIL contains CTSM 5.4, which contains CLM + CIME +
NEON + etc. The inheritance flows through CTSM, not directly from
individual components.

Connect CTSM releases left-to-right with horizontal arrows (version
progression): 5.2 -> 5.3 -> 5.4 -> ExSOIL.

### Shared components across trees

Where the same component appears in multiple trees, use the same
color and show that they are the same thing at different versions:

- **CLM green nodes:** clm5.0 (in CESM 2.2.x) vs clm6.0 (in CTSM
  5.4 and CESM 3.x). These are different versions of the same thing.
  A faint horizontal line connecting them across the time axis would
  show the version progression.

- **CIME blue nodes:** cime5.x (in CESM 2.2.x and early CTSM) vs
  cime6.1 (in CTSM 5.4 and CESM 3.x). Same progression.

- **NEON purple nodes:** appears in CTSM 5.2+, CTSM 5.4, ExSOIL
  (through CTSM), and CESM 3.x (through CTSM). Does NOT appear in
  CESM 2.2.x.

## Visual callouts

1. **"NOT CONNECTED" or red X** between CESM 2.2.x and NEON. This is
   the most important gap to communicate: NEON was never in CESM 2.x.

2. **Red dashed "NOT PUBLISHED"** on the CMIP7 data node under CTSM
   5.4. This is the current blocker. A callout or annotation: "Input
   data not on public servers. Blocks live simulations."

3. **Dashed lines** on the escomp Docker image's component connections,
   indicating it was an unofficial hybrid.

4. **The ExSOIL container** should be the most visually prominent node
   (boldest border, largest). It's what this project produces.

## Color key

| Color | Component type |
|-------|---------------|
| Dark gray (#282728) | CESM (full Earth system) |
| Red (#c5050c) | CTSM (standalone land) |
| Green (#3d7a38) | CLM (land model code) |
| Blue (#0479a8) | CIME (build/run system) |
| Purple (#9b59b6) | NEON (tower workflow) |
| Orange (#e67e22) | Docker containers |
| Light gray (#888) | Other components (CAM, POP, MOSART, etc.) |
| Red dashed | Missing / not published / blocker |

## Data access evolution (CMIP generations)

Add a data lane at the bottom showing the CMIP data generations as
horizontal bars, with connection lines up to the releases that use
each generation. This explains the current blocker.

**CMIP6 bar:** Solid, green, spanning 2020 through present. Label:
"Fully published on all NCAR servers." Connection arrows up to:
- CESM 2.2.0 and 2.2.2 (these use CMIP6 datasets)
- CTSM 5.2 (uses CMIP6 datasets)
- Older NEON runs (CMIP6 SSP3-7.0 forcing covers 2015-2100)

**CMIP7 bar:** Two segments:
- **Historical segment** (solid, covers 1850-2023): Label "Published."
  Connection up to CTSM 5.4 CLM 6.0 physics.
- **SSP/future segment** (red dashed or empty, covers 2024+): Label
  "NOT YET PRODUCED." This is the gap.

**The critical annotation:** NEON tower simulations cover 2018-2021.
The historical period in CMIP ends around 2014. So NEON runs need
SSP-era forcing data to cover 2015-2021. With CMIP6, this data
exists (SSP3-7.0 files are published). With CMIP7, it does not.

Show this as:
```
NEON run period: 2018-2021
                    |
         Falls in SSP era (post-2014)
                    |
    CMIP6 SSP: available ✓     CMIP7 SSP: not produced ✗
         |                              |
    CTSM 5.2 works              CTSM 5.4 blocked
```

This makes the data gap concrete: it's not that NCAR forgot to
upload files. It's that CMIP7 only covers the historical period so
far, and NEON runs need SSP-era coverage that CMIP7 hasn't produced.

## What this diagram should communicate at a glance

1. CESM and CTSM are both assemblies of components, with CTSM being
   a subset focused on land
2. The specific versions of CLM, CIME, and NEON that ship in each
   release
3. NEON is in CTSM (and future CESM 3.x) but NOT in CESM 2.x
4. The ExSOIL container builds on CTSM 5.4 and inherits all its
   components
5. The old escomp image was a non-standard hybrid of two product lines
6. CMIP7 data is the one missing piece blocking simulations
