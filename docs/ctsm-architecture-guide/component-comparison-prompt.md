# Component comparison diagram: generation prompt

## What this diagram shows

Four configurations of the same modeling framework, laid out side by side.
Each configuration has the same set of component "slots." What changes is
which slots are filled with active models, which are filled with data
readers, which are stubs, and which are absent entirely.

The audience is domain experts (ecologists, soil scientists) who are not
deeply familiar with CESM internals. The diagram should make it immediately
obvious what ExSOIL keeps, what it replaces, and what it drops.

---

## Structure (four columns, one per configuration)

```
              CESM 2.x           CESM 3.x (beta)     ExSOIL v1 (old)       ExSOIL v2 (current)
              Full coupled        Full coupled         CESM 2.2 + graft      Standalone CTSM 5.4
              Earth system        Earth system         Broken container       Working container

COUPLER       MCT (legacy)        CMEPS/NUOPC          MCT (legacy)          CMEPS/NUOPC
              [active]            [active]              [active]              [active]

ATMOSPHERE    CAM                 CAM-SIMA              DATM                  DATM
              Simulated weather   Simulated weather     Reads forcing files   Reads NEON tower data
              [active-simulated]  [active-simulated]    [data-driven]         [data-driven]

LAND          CLM 5.x            CLM 6.0               CLM (~5.x dev)        CLM 6.0
              Full land model     Full land model       Dev branch graft      Full land model
              [active-simulated]  [active-simulated]    [active-simulated]    [active-simulated]

OCEAN         POP2               MOM6                   POP2 (source only)    stub (socn)
              Simulated ocean     Simulated ocean       Code present, unused  Placeholder, no-op
              [active-simulated]  [active-simulated]    [present-unused]      [stub]

SEA ICE       CICE               CICE                   CICE (source only)    stub (sice)
              Simulated ice       Simulated ice         Code present, unused  Placeholder, no-op
              [active-simulated]  [active-simulated]    [present-unused]      [stub]

ICE SHEET     CISM               CISM                   CISM (source only)    stub (sglc)
              Simulated glaciers  Simulated glaciers    Code present, unused  Placeholder, no-op
              [active-simulated]  [active-simulated]    [present-unused]      [stub]

RIVER         MOSART/RTM         MOSART                 RTM (source only)     stub (srof)
              River routing       River routing         Code present, unused  Placeholder, no-op
              [active-simulated]  [active-simulated]    [present-unused]      [stub]

WAVE          WW3                WW3                    WW3 (source only)     stub (swav)
              Wave model          Wave model            Code present, unused  Placeholder, no-op
              [active-simulated]  [active-simulated]    [present-unused]      [stub]

BUILD SYSTEM  CIME 5.x           CIME 6.x              CIME 5.x             CIME 6.1
              [active]            [active]              [active]              [active]

NEON WORKFLOW (not available)     (native in CTSM)      Grafted from dev      Native (48 sites)
                                                        branch, broken
              [absent]            [active]              [broken]              [active]

TOWER DATA    (not applicable)    (not applicable)       Unknown               NEON tower forcing
              [absent]            [absent]              [unknown]             [data-driven]

PYTHON STACK  (not included)      (not included)        Python 3.7, old pkgs  Python 3.13, current
              [absent]            [absent]              [active]              [active]
```

---

## Color coding (four states)

| State              | Color suggestion      | Meaning |
|--------------------|-----------------------|---------|
| Active (simulated) | Solid blue or teal    | Running a physics simulation |
| Data-driven        | Solid green or amber  | Reading observed data from files |
| Stub / no-op       | Light gray, dashed    | Placeholder that does nothing (required by the framework but not used) |
| Present but unused | Striped or hatched    | Source code is in the container but never runs (wasted space) |
| Absent             | Empty / white         | Not part of this configuration at all |
| Broken             | Red outline or X      | Present but non-functional |

---

## Visual layout guidance

- Four columns, one per configuration. Column headers at the top with the
  configuration name and a one-line description.
- Rows are the component slots. Each cell shows: component name, a one-line
  description, and a color fill indicating its state.
- The LAND row should be visually emphasized (heavier border, slight highlight)
  since it is the component all four share and the one ExSOIL cares about.
- The ATMOSPHERE row is the key comparison point: CAM (simulated) vs DATM
  (observed data). Consider an annotation or callout here.
- Draw the coupler as a horizontal bar across the top connecting atmosphere
  and land (and ocean/ice when active). For ExSOIL v2, the coupler bar should
  only span atmosphere and land, with stubs shown as small disconnected boxes.
- The bottom rows (NEON workflow, tower data, Python stack) are below a
  divider labeled "Application layer" to distinguish them from the modeling
  framework.
- Beneath each column, a one-line summary:
  - CESM 2.x: "Full Earth system, all components simulated"
  - CESM 3.x: "Full Earth system, modernized coupler and ocean"
  - ExSOIL v1: "Carried 3-4 GB of unused code, NEON workflow broken"
  - ExSOIL v2: "Only land + data atmosphere, everything else stubbed out"

---

## Key annotations to include on the diagram

1. Arrow from CESM 2.x ATMOSPHERE (CAM) to ExSOIL v2 ATMOSPHERE (DATM)
   with label: "Simulated weather replaced by real tower observations"

2. Arrow or note on the ocean/ice/glacier rows in ExSOIL v2:
   "Stubs: required by the framework but do nothing. No source code shipped."

3. Note on ExSOIL v1 ocean/ice rows:
   "Source code present (~3-4 GB) but never executed"

4. Callout on ExSOIL v2 NEON workflow:
   "48 pre-configured NEON sites. Single command: run_tower --neon-sites KONZ"

---

## Style notes

- Use the DSI design system palette: bone (#F7F3EC) background, ink (#1C1A19)
  text, Badger Red (#C5050C) for emphasis/highlights, slate (#2E4756) for
  active components, mist (#D7D1C4) for borders and stubs.
- Red Hat Display for headings, Red Hat Text for body, JetBrains Mono for
  component names and code.
- No gradients, no 3D effects, no glow. Flat, clean, technical.
- No emoji.
