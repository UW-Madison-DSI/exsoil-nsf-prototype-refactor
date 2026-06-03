# Decision Brief: NEON Site Support in CESM 2.2.2 Container

**Status:** Open for discussion
**Date:** 2026-06-03
**Author:** Steven Wangen
**Stakeholders:** ExSOIL project team

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

### Root cause

`run_neon_v2.py` discovers available NEON sites by looking for per-site
configuration directories (called "usermods") inside the CLM source tree:

```python
valid_neon_sites = sorted([
    v.split("/")[-1]
    for v in glob.glob(
        os.path.join(cesmroot, "cime_config", "usermods_dirs", "NEON", "[!d]*")
    )
])
```

In the original `escomp/cesm-lab-neon` container, these directories existed
because ESCOMP built the image with a CLM/CTSM version that included the
NEON tower workflow (added circa 2021). However, the standard CESM 2.2.2
release (which we now use) ships an older CLM that predates NEON usermods
support. The directory `cime_config/usermods_dirs/NEON/` does not exist in
the CLM component tree.

This means the NEON site workflow (the primary use case for this project)
is non-functional in the rebuilt container.

### Scope

This affects:
- All Design_Hub and Modeling_Hub notebook cells that invoke `run_neon_v2`
- Any workflow that creates NEON site-specific CLM cases
- The `--neon-sites` CLI argument

This does NOT affect:
- General CESM case creation (I2000Clm50Sp, B1850, etc.) -- these work fine
- The Python scientific stack, JupyterLab, or analysis workflows
- The multi-arch (arm64/amd64) build infrastructure

## Options

### Option A: Graft NEON usermods from a newer CTSM release

Copy the `usermods_dirs/NEON/` directory from a recent CTSM release (e.g.,
`ctsm5.2` or the CTSM `main` branch) into the CESM 2.2.2 CLM tree during
the Docker build. This is the approach the original ESCOMP image likely used.

**Pros:**
- Minimal disruption to the rest of the CESM source tree
- The NEON usermods are mostly configuration files (XML, shell scripts), not
  compiled code, so cross-version compatibility is plausible
- Can be done with a few COPY lines in the Dockerfile

**Cons:**
- The usermods may reference CLM namelist options or surface datasets that
  don't exist in CESM 2.2.2's CLM
- Compatibility is not guaranteed; could cause subtle case configuration
  errors that are hard to diagnose
- Creates a maintenance burden: need to track which CTSM version the
  usermods came from

**Effort:** Low (hours), but validation risk is moderate.

### Option B: Pin the CLM component to a newer CTSM tag

Override just the CLM/CTSM component in the CESM checkout to use a newer
tag (e.g., `ctsm5.2.005`) while keeping the rest of CESM at 2.2.2.
CESM's `Externals.cfg` allows per-component tag overrides.

**Pros:**
- Gets the full NEON workflow as designed, including usermods, surface
  datasets, and any associated code fixes
- Officially supported CLM version
- Likely forward-compatible with future NEON site additions

**Cons:**
- Newer CTSM may have API incompatibilities with CESM 2.2.2's CIME,
  coupler, or data atmosphere components
- Could break the `case.build` compilation we just got working (89/89 tests)
- The `run_neon_v2.py` script was written against a specific CTSM version;
  API drift is possible
- Mixing component versions is officially unsupported by ESCOMP

**Effort:** Medium (days). Requires rebuilding, recompiling, and re-testing.

### Option C: Bundle NEON site configs in this repository

Create a `neon-sites/` directory in this repository containing the
per-site usermods (shell_commands, user_nl_clm, etc.) and copy them
into the CLM tree during the Docker build. Maintain them independently
of any CTSM release.

**Pros:**
- Full control over site configurations
- Can tailor to the specific sites the project uses (not all 81 NEON sites)
- No dependency on CTSM version compatibility
- Easy to add custom sites or modify existing ones

**Cons:**
- Significant upfront effort to create/port the usermods for each site
- Must maintain surface dataset references, domain files, and DIN_LOC_ROOT
  paths manually
- Diverges from the community-maintained CTSM NEON workflow

**Effort:** Medium-high (days to week), depending on how many sites are needed.

### Option D: Upgrade to CESM 3.x / CTSM 6.x

Move to a current CESM release that natively includes the NEON workflow.
This would resolve the compatibility issue at its root and also fix the
Python 3.11 pin (CIME in CESM 3.x supports Python 3.12+).

**Pros:**
- Resolves the NEON issue, the Python version pin, and other CESM 2.2.x
  limitations in one move
- Aligns with the community's current supported version
- Future-proofs the container

**Cons:**
- Major version upgrade; potentially breaking changes across all components
- `run_neon_v2.py` was written against 2.2.x APIs; significant rewrite
  likely needed
- All 89 tests would need to be re-validated
- CESM 3.x may have different machine configuration requirements

**Effort:** High (weeks). Essentially a second rebuild.

## Questions for Discussion

1. **Which NEON sites does the project actively use?** If it's only 3-5
   sites, Option C becomes more attractive. If it's many, Option A or B
   scales better.

2. **How tightly coupled is `run_neon_v2.py` to CESM 2.2.x internals?**
   If it mostly uses CIME's public API (create_newcase, xmlchange), a
   component upgrade (Option B) may be safe. If it patches internal CIME
   files, it's riskier.

3. **Is there appetite for a CESM 3.x migration?** If the project plans
   to upgrade eventually, doing it now (Option D) avoids a throwaway
   intermediate step. If 2.2.x is the target for the foreseeable future,
   a lighter option (A or C) makes more sense.

4. **Did the original ESCOMP container use a custom CTSM branch?** If we
   can identify exactly which CLM/CTSM version the `escomp/cesm-lab-neon`
   image used, we can replicate its approach precisely.

## Recommendation

No recommendation at this time. This brief is intended to frame the
discussion. The choice depends on the project's timeline, the number of
NEON sites needed, and the team's appetite for a larger CESM version
upgrade.

## Related

- [ADR-0002: Build Strategy](../adr/0002-arm64-build-strategy.md) --
  documents the CESM 2.2.2 choice and the compatibility fixes applied
- [arm64-container-rebuild.md](../arm64-container-rebuild.md) --
  overview of the rebuild work
