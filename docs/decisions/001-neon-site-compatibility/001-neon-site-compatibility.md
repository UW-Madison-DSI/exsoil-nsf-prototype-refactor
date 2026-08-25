# Decision Brief: NEON Site Support in CESM 2.2.2 Container

**Status:** Open for discussion
**Date:** 2026-06-03
**Author:** Steven Wangen
**Stakeholders:** ExSOIL project team

## Executive Summary

The project's Docker container was recently rebuilt from scratch on
Ubuntu 24.04 with native support for both Intel/AMD (amd64) and Apple
Silicon (arm64) processors. The multi-arch infrastructure, conda
environment, 89-test validation suite, and CESM Fortran build system
are all working. What is missing is the NEON tower site workflow, the
project's primary use case.

The previous container (`escomp/cesm-lab-neon`) was an amd64-only,
custom image that mixed the CESM 2.2 framework with a newer CTSM
development branch to get NEON support. This was a one-off build by an
NCAR developer, not part of any official CESM release. NEON support was
never part of the CESM 2.x development pipeline. It was developed
exclusively on CTSM's master branch starting in February 2021, and will
only enter CESM when version 3.x ships (currently in alpha).

Our rebuild used the official CESM 2.2.2 release, which is clean and
reproducible but does not include NEON because the 2.2 branch predates
that work entirely. We did not lose something that was there before;
the old container was a non-standard assembly.

This brief presents five options for restoring NEON functionality:

- **Options A-C** bolt NEON support onto our existing CESM 2.2.2
  container in various ways (graft configuration files from a newer
  CTSM, upgrade just the CLM component within CESM, or maintain our own
  site configurations in this repository).
- **Option D** upgrades to CESM 3.x, the next major release that will
  include NEON natively alongside the full coupled Earth system
  (atmosphere, ocean, ice, land). This is high effort and CESM 3.x is
  not yet released.
- **Option E** drops the full CESM framework and uses standalone CTSM
  instead. This is what NCAR actually built the NEON workflow for.
  Current CTSM releases have full NEON support today, available right
  now. The multi-arch Dockerfile, conda environment, and test framework
  we built carry over; only the "clone CESM" stage of the Dockerfile
  changes to "clone CTSM." The trade-off is losing the ability to run
  fully coupled atmosphere-land-ocean simulations, which the project
  does not currently use but could want in the future.

The choice depends on the project's scope, timeline, and whether fully
coupled simulations are on the roadmap.

## Background: How CESM, CLM, and NEON Fit Together

Before diving into the problem, it helps to understand the system
architecture. CESM (Community Earth System Model) is a modular climate
simulation framework maintained by NCAR. It models the entire Earth system
by coupling separate components that each handle a different domain:

| Component | Domain | What it simulates |
|-----------|--------|-------------------|
| **CAM** | Atmosphere | Weather, radiation, clouds, precipitation |
| **CLM** | Land surface | Soil temperature/moisture, vegetation, carbon cycling, snow, rivers |
| **POP** | Ocean | Ocean circulation, heat transport, biogeochemistry |
| **CICE** | Sea ice | Ice formation, melting, drift |
| **CISM** | Ice sheets | Glaciers, Greenland/Antarctic ice dynamics |
| **MOSART** | Rivers | Freshwater routing from land to ocean |

These components exchange energy, water, and momentum through a central
coupler at each time step. For a full simulation you run them all together,
but for land-focused research (like this project) you can run CLM by itself
with prescribed atmospheric forcing data, which is much cheaper
computationally.

**CLM** (Community Land Model) is the component most relevant to this
project. It simulates what happens at and below the land surface: how soil
heats and cools, how water moves through soil layers, how plants grow and
exchange carbon with the atmosphere, and how snow accumulates and melts.
**CTSM** (Community Terrestrial Systems Model) is the standalone version of
CLM, maintained in its own Git repository. The names CLM and CTSM are often
used interchangeably; technically CLM is the component within CESM and CTSM
is the broader standalone project that contains it.

**NEON** (National Ecological Observatory Network) operates 81 instrumented
field sites across the United States. Each site has a tower equipped with
sensors that continuously measure things like air temperature, humidity,
wind speed, soil temperature at multiple depths, soil moisture, and carbon
dioxide fluxes between the land and atmosphere. These measurements provide
ground truth for testing whether CLM's predictions match reality at
specific locations.

**The NEON tower workflow** connects CLM to these real-world observations.
The idea is: take CLM, configure it for a specific NEON tower site (telling
it the exact grid cell, soil properties, vegetation type, and local
conditions), feed it observed meteorological data from that tower as
atmospheric forcing, run the simulation, then compare CLM's predicted soil
temperatures, moisture, and carbon fluxes against what the tower actually
measured. This is the primary use case for this project's notebooks.

**CIME** (Common Infrastructure for Modeling the Earth) is the build and
case management system that orchestrates all of this. When you run commands
like `create_newcase`, `case.setup`, and `case.build`, you are using CIME.
It handles the Fortran compilation, namelist generation, MPI configuration,
and job submission. CIME is shared across all CESM components and lives
inside the CESM source tree.

**Usermods** are per-site configuration bundles that tell CIME how to set up
CLM for a specific NEON tower location. Each site's usermods directory
(e.g., `NEON/ABBY/`, `NEON/BART/`) contains files that specify the grid
cell coordinates, surface dataset paths, and namelist overrides for that
site. Without usermods, you would have to manually configure all of these
details every time you create a case for a NEON site.

### History: When and where NEON support was developed

The NEON tower workflow was **never part of any CESM 2.x release**. It
was developed specifically for standalone CTSM, on a separate development
branch, after the CESM 2.2 release line had already been cut.

The timeline:

- **CESM 2.2 released.** Its `Externals.cfg` pins CLM to the tag
  `release-cesm2.2.04`, which is part of the `release-clm5.0` maintenance
  line. This tag contains no NEON support.
- **February 2021:** NEON usermods development began on CTSM's `master`
  branch ([PR #1278](https://github.com/ESCOMP/CTSM/pull/1278): "Adds
  support for NEON tower data sites"). Merged May 2021.
- **2021-2022:** Active NEON development continued across multiple PRs:
  surface datasets ([#1375](https://github.com/ESCOMP/CTSM/pull/1375)),
  batch wrapper ([#1444](https://github.com/ESCOMP/CTSM/pull/1444)),
  UI improvements ([#1467](https://github.com/ESCOMP/CTSM/pull/1467)),
  and others.
- **November 2022:** First NEON-tagged CTSM release (`ctsm5.1.dev114`),
  described as "NEON release: Some NEON updates fixing AG sites."
- **CESM 2.2.x was never updated** to incorporate any of this work. No
  GitHub issues or PRs in the CESM repository discuss backporting NEON
  support to 2.x. The `release-clm5.0` line continued to receive
  maintenance patches (latest: `release-clm5.0.37`, May 2024) but none
  included NEON usermods.

The NEON workflow will arrive in CESM when version 3.x ships (currently
in alpha: `cesm3_0_alpha01a` through `cesm3_0_alpha05a`). Until then,
NCAR's official documentation and tutorials frame it exclusively as a
[standalone CTSM feature](https://escomp.github.io/CTSM/users_guide/running-single-points/supported-tower-sites.html).
The [NCAR CTSM Tutorial](https://github.com/NCAR/CTSM-Tutorial)
(including a `NEON_Tutorial_2023` branch) teaches NEON as a CTSM
standalone workflow, not as part of CESM.

### How the original container worked

The original `escomp/cesm-lab-neon` Docker image (published on Docker Hub
by NCAR developer `bdobbins` around 2022, 1.72 GB, amd64-only) was a
**custom assembly** that does not correspond to any standard CESM release.
It was not built from the
[ESCOMP-Containers](https://github.com/ESCOMP/ESCOMP-Containers)
repository (which has no NEON references). It appears to have been built
separately using a development CTSM branch with NEON support baked in,
layered onto a CESM 2.2-era framework. NCAR's
[ncar-neon-books](https://github.com/NCAR/ncar-neon-books) documentation
references `docker pull escomp/cesm-lab-neon` but does not document which
CTSM tag was used inside.

The `run_neon.py` script (and our extended `run_neon_v2.py`) was designed
to work with this custom setup: it scans the usermods directory to discover
available sites, then orchestrates case creation, configuration, build,
and run for whichever site the user selects.

### What changed in the rebuild

When we rebuilt the container for multi-architecture (arm64 + amd64)
support, we replaced the old custom ESCOMP image with a clean CESM 2.2.2
checkout from GitHub. This is a reproducible, officially tagged release,
but its CLM component (`release-cesm2.2.04`) is part of the
`release-clm5.0` line that predates NEON development entirely. The
directory `cime_config/usermods_dirs/NEON/` does not exist and was never
intended to exist in this branch.

We did not lose something that was there before. The old container was a
non-standard build that mixed components from different version lines.
Our rebuild used a clean checkout, which is better for maintainability and
reproducibility but does not include the NEON customization that was
grafted onto the old image.

## Problem

The `run_neon_v2.py` wrapper script cannot find any valid NEON site codes
(ABBY, BART, KONZ, etc.) in the rebuilt container. Running a notebook cell
like:

```bash
run_neon_v2 --neon-sites ABBY --output-root $output_root --overwrite
```

fails with:

```
run_neon_v2: error: argument --neon-sites: invalid choice: 'ABBY' (choose from 'all')
```

### How the script discovers sites

`run_neon_v2.py` discovers available NEON sites by scanning a specific
directory in the CLM source tree at startup:

```python
valid_neon_sites = sorted([
    v.split("/")[-1]
    for v in glob.glob(
        os.path.join(cesmroot, "cime_config", "usermods_dirs", "NEON", "[!d]*")
    )
])
```

In the original container, this glob matched 81 directories (one per NEON
site). In our CESM 2.2.2 container, the `NEON/` directory does not exist,
so the glob returns nothing. The script then tells argparse that the only
valid choice is `'all'` (which maps to an empty list), and any specific
site code gets rejected before the script even starts doing real work.

### What this breaks

This affects:
- All Design_Hub and Modeling_Hub notebook cells that invoke `run_neon_v2`
- Any workflow that creates NEON site-specific CLM cases
- The `--neon-sites` CLI argument (no site codes are valid)

This does NOT affect:
- General CESM case creation (compsets like I2000Clm50Sp, B1850, etc.
  all work fine)
- The CESM Fortran compilation (`case.build` produces `cesm.exe` in 78s
  on arm64)
- The Python scientific stack, JupyterLab, or post-processing analysis
  workflows
- The multi-arch (arm64/amd64) build infrastructure

## Options

### Option A: Graft NEON usermods from a newer CTSM release

Copy the `usermods_dirs/NEON/` directory from a recent CTSM release (e.g.,
`ctsm5.2` or the CTSM `main` branch) into the CESM 2.2.2 CLM tree during
the Docker build. This is likely the approach the original ESCOMP image
used, though we have not confirmed that.

Each NEON site's usermods directory is a small collection of text files:
a `shell_commands` script that runs `xmlchange` to set grid and compset
options, and a `user_nl_clm` file that overrides CLM namelist parameters
for that location. These are configuration files, not compiled code, so
cross-version compatibility is plausible but not guaranteed.

**Pros:**
- Minimal disruption to the rest of the CESM source tree
- Small file footprint (a few KB per site)
- Can be implemented with a few lines in the Dockerfile

**Cons:**
- The usermods may reference CLM namelist options or surface datasets that
  don't exist in CESM 2.2.2's CLM (newer CTSM versions add new namelist
  variables that older CLM won't recognize)
- Compatibility is not guaranteed; could cause subtle case configuration
  errors that are hard to diagnose
- Creates a maintenance burden: need to track which CTSM version the
  usermods came from

**Effort:** Low (hours to implement), but validation risk is moderate.

### Option B: Pin the CLM component to a newer CTSM tag

CESM uses a configuration file called `Externals.cfg` to specify which
Git tag of each component to check out. You can override individual
components without changing the rest. This option would pin just the
CLM/CTSM component to a newer tag (e.g., `ctsm5.2.005`) while keeping
CESM's framework, coupler, atmosphere, ocean, and ice components at 2.2.2.

This gives you the full NEON workflow exactly as the CTSM developers
designed it: usermods, surface datasets, and any associated bug fixes.
However, mixing component versions is not something ESCOMP officially
supports, because the components are tested together at specific
version combinations.

**Pros:**
- Gets the full NEON workflow as designed, including usermods, surface
  datasets, and any associated code fixes
- Officially supported CLM version with community testing
- Likely forward-compatible with future NEON site additions

**Cons:**
- Newer CTSM may have API incompatibilities with CESM 2.2.2's CIME,
  coupler, or data atmosphere components
- Could break the `case.build` compilation we just got working (89/89
  tests pass currently)
- The `run_neon_v2.py` script was written against a specific CTSM version;
  API drift is possible
- Mixing component versions is officially unsupported by ESCOMP

**Effort:** Medium (days). Requires rebuilding, recompiling, and
re-testing the full 89-test suite.

### Option C: Bundle NEON site configs in this repository

Create a `neon-sites/` directory in this repository containing the
per-site usermods and copy them into the CLM tree during the Docker build.
Maintain them independently of any CTSM release.

This decouples the project from CTSM versioning entirely. You would author
(or port from a CTSM release) the `shell_commands` and `user_nl_clm`
files for each site the project needs. You could also add custom sites or
modify existing ones freely. The trade-off is that you take on the
maintenance responsibility that CTSM's developers would otherwise handle.

**Pros:**
- Full control over site configurations
- Can tailor to the specific sites the project uses (not all 81 NEON sites)
- No dependency on CTSM version compatibility
- Easy to add custom sites or modify existing ones

**Cons:**
- Significant upfront effort to create or port the usermods for each site
- Must maintain surface dataset references, domain files, and input data
  paths manually
- Diverges from the community-maintained CTSM NEON workflow; harder to
  benefit from upstream improvements

**Effort:** Medium-high (days to a week), depending on how many sites
are needed.

### Option D: Upgrade to CESM 3.x / CTSM 6.x

Move to a current CESM release that natively includes the NEON workflow.
CESM 3.x represents a significant architecture change from 2.x: it uses
a new coupling framework (NUOPC instead of MCT), a newer CIME, and
current versions of all components. This would resolve the NEON
compatibility issue at its root and also fix several other limitations
we worked around during the rebuild (the Python 3.11 pin, PIO2 source
patches, and GCC compatibility flags).

**Pros:**
- Resolves the NEON issue, the Python version pin, and other CESM 2.2.x
  limitations in one move
- Aligns with the community's current supported version
- Future-proofs the container for years

**Cons:**
- Major version upgrade; CESM 3.x uses a different coupling framework
  (NUOPC vs MCT), which means the build system, machine configs, and
  component interfaces are all different
- `run_neon_v2.py` was written against 2.2.x's CIME APIs; significant
  rewrite likely needed
- All 89 container tests would need to be re-validated
- The 13 compatibility fixes we applied for the current build may be
  irrelevant, but new ones would likely surface

**Effort:** High (weeks). Essentially a second rebuild effort.

### Option E: Replace CESM with standalone CTSM

Rather than working around the version mismatch, drop the full CESM
checkout entirely and replace it with a standalone CTSM checkout. CTSM
has its own `Externals.cfg` that pulls in only what it needs to run:
CIME (build system), DATM (data atmosphere for forcing), MOSART (river
routing), and stub components for ocean/ice/wave. It does not pull in
CAM, POP, CICE, CISM, or WW3.

Current CTSM releases include the NEON tower workflow natively, which
is the feature we need. This option reframes the question: instead of
"how do we get NEON support into CESM 2.2.2," it asks "do we actually
need CESM, or is CTSM sufficient for what this project does?"

**What CTSM standalone includes:**

| Component | Purpose | Needed by this project? |
|-----------|---------|------------------------|
| CLM/CTSM | Land model (soil, vegetation, carbon) | Yes, this is the core |
| CIME | Build system, case management | Yes |
| DATM | Data atmosphere (feeds observed weather to CLM) | Yes |
| MOSART | River routing | Yes (used in I-compset runs) |
| Stubs (SICE, SOCN, SWAV) | Placeholder ocean/ice/wave | Yes (do nothing, but needed by the coupler) |
| FATES | Vegetation demographics (optional) | Possibly, for future work |

**What would be lost:**

| Component | What it does | Impact of losing it |
|-----------|-------------|---------------------|
| CAM | Full atmospheric simulation | None for current workflows. The project uses observed forcing data (DATM), not a simulated atmosphere. CAM would only be needed for coupled atmosphere-land experiments where CLM feeds back into the atmosphere. |
| POP | Ocean circulation | None. The project has no ocean modeling component. Even in CESM, the NEON tower workflow uses a stub ocean. |
| CICE | Sea ice dynamics | None. Not relevant to land surface research at NEON tower sites. |
| CISM | Ice sheet dynamics | None. Greenland/Antarctic ice sheet modeling is outside the project's scope. |
| WW3 | Surface wave modeling | None. |
| Fully coupled simulations | Running all components together so atmosphere, land, ocean, and ice interact with each other | This is the most significant loss. With standalone CTSM, you cannot run experiments where changes to the land surface (e.g., deforestation, irrigation) feed back into the atmosphere and alter precipitation patterns. The land model receives prescribed weather data and cannot influence it. For the current NEON tower workflow, this is fine: you are comparing the model against tower observations under known atmospheric conditions. But if the project ever expands to studying land-atmosphere feedbacks, regional climate impacts of land use change, or paleoclimate scenarios, you would need the full CESM coupling. |

In practical terms: the project currently runs CLM in "I-compset" mode
(land-only with data atmosphere), which is exactly what standalone CTSM
is designed for. The full CESM components (CAM, POP, CICE, CISM) are
present in the current container but never compiled or executed. They
consume ~3-4 GB of source code in the image for no functional benefit.

The decision to move to CTSM standalone would be a statement about the
project's scope: "we are a land surface modeling project, not a coupled
climate modeling project." If that scope might expand in the future,
keeping the full CESM framework preserves optionality, even if unused
today.

**Pros:**
- NEON tower workflow included natively; this is what CTSM is built for
- Dramatically smaller image (~3-4 GB less source code)
- Current CTSM versions support Python 3.12+; no need for the 3.11 pin
- Newer PIO and CIME; the source patches and GCC workarounds we applied
  may be unnecessary
- Aligns with how NCAR actually recommends running NEON tower experiments
- Simpler dependency tree; fewer components means fewer version conflicts

**Cons:**
- Loses the ability to run fully coupled simulations (atmosphere-land-ocean
  interaction) if the project scope ever expands
- `run_neon_v2.py` resolves paths relative to `CESMROOT`; these would need
  updating to CTSM's directory layout
- Machine configs (`config_machines.xml`, `config_compilers.xml`) would
  need porting to CTSM's version of CIME
- The GCC compatibility flags we debugged may or may not still be needed;
  requires testing
- The 89-test suite would need re-validation against the new layout
- Different community support model: CTSM issues go to CTSM GitHub, not
  CESM forums

**Effort:** Medium (days). Comparable to Option B, but with a cleaner
result. The Dockerfile stages and conda environment carry over unchanged;
only the CESM clone stage and machine configs need rework.

## Comparison

|  | A: Graft usermods | B: Newer CLM tag | C: Bundle in repo | D: CESM 3.x | E: CTSM standalone |
|--|-------------------|------------------|--------------------|-------------|---------------------|
| Effort | Low | Medium | Medium-high | High | Medium |
| NEON sites work | Likely | Yes | Yes | Yes | Yes |
| Existing 89 tests pass | Yes | Unknown | Yes | Must re-validate | Must re-validate |
| Fixes Python 3.11 pin | No | No | No | Yes | Likely |
| Fixes PIO2 patches | No | No | No | Yes | Likely |
| Community-maintained | Partial | Yes | No | Yes | Yes |
| Risk to current build | Low | Moderate | Low | High | Moderate |
| Image size reduction | None | None | None | None | ~3-4 GB smaller |
| Coupled simulations | Preserved | Preserved | Preserved | Preserved | Lost |

## Questions for Discussion

1. **Which NEON sites does the project actively use?** If it's only 3-5
   sites, Option C becomes more attractive. If it's many, Options A, B,
   or E scale better.

2. **How tightly coupled is `run_neon_v2.py` to CESM 2.2.x internals?**
   If it mostly uses CIME's public API (create_newcase, xmlchange), a
   component upgrade (Option B) or CTSM switch (Option E) may be safe.
   If it patches internal CIME files, it's riskier.

3. **Is there appetite for a CESM 3.x migration?** If the project plans
   to upgrade eventually, doing it now (Option D) avoids a throwaway
   intermediate step. If 2.2.x is the target for the foreseeable future,
   a lighter option makes more sense.

4. **Does the project ever need fully coupled simulations?** If the
   answer is "no, we only run CLM against observed forcing data," then
   Option E (CTSM standalone) is arguably the most natural fit. If
   coupled experiments are on the roadmap, Options A-D preserve that
   capability.

5. **Did the original ESCOMP container use a custom CTSM branch?** If we
   can identify exactly which CLM/CTSM version the `escomp/cesm-lab-neon`
   image used, we can replicate its approach precisely.

## CESM 3.x Release Timeline

For context on Option D: CESM 3.x was officially targeted for **spring
2026** (per the [CESM3 Plans page](https://www.cesm.ucar.edu/news/community-earth-system-model-3-cesm3-plans-progress-timelines),
last updated November 2025). As of June 2026, that target has slipped.
The latest beta tag on GitHub (`beta08`) was published April 2, 2026,
following a steady progression (`beta03` Oct 2024 through `beta08` Apr
2026). The February 2026 CESM newsletter referenced "finalization and
release of CESM3 later this year." No revised release date has been
published. The release is tied to CMIP7 forcing data availability, an
external dependency.

Best estimate: **late 2026**, but this is speculative. The project's
NEON notebooks need to work now, not in 3-6 months.

## Recommendation

**Option E (standalone CTSM)** is recommended. See
[ADR-0005](../../adr/0005-standalone-ctsm.md) for the full rationale.

In brief: NCAR built the NEON workflow for standalone CTSM, not for
CESM. Current CTSM releases have full NEON support available today.
The multi-arch infrastructure, conda environment, and test framework
from the rebuild carry over unchanged. The project runs land-only
simulations with data atmosphere, which is exactly what standalone CTSM
is designed for. The trade-off (losing coupled simulation capability)
does not affect current workflows and can be revisited if scope expands.

## Related

- [ADR-0002: Build Strategy](../../adr/0002-arm64-build-strategy.md) --
  documents the CESM 2.2.2 choice and the compatibility fixes applied
- [Rebuild report](../../multiarch-rebuild-report/multiarch-rebuild-report.md) --
  full technical detail on the multi-arch rebuild
