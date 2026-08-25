# Refinement Prompt for Version Lineage Diagram

Starting from the current diagram (lineage_chart.png), make these
specific changes:

## 1. escomp/cesm-lab-neon needs more space and clearer hybrid lines

The escomp Docker image box is small and cramped. Enlarge it slightly
and make its two dependency connections more prominent:
- A dashed line UP to CESM 2.2 (it used the CESM 2.2 framework/CIME)
- A dashed line ACROSS to a point on the CTSM development line circa
  2022 (it grafted in a dev CTSM branch for NEON capability)
These dashed lines communicate that it was an unofficial hybrid of
two product lines.

## 2. Show component version progression horizontally

CLM evolves from clm5.0 (in CESM 2.2.x) to clm6.0 (in CTSM 5.4 and
CESM 3.x). CIME evolves from 5.x to 6.1. Add faint horizontal
connecting lines or arrows between the same component at different
versions across the release boxes. This lets the reader track a single
component's evolution through time. Use matching colors (green for CLM,
blue for CIME).

## 3. Show CESM 3.x getting NEON through CTSM

CESM 3.x includes NEON, but it gets it through CTSM (CTSM's CLM/NEON
work flows into CESM 3.x). Add a dashed connection line from the CTSM
lane up into CESM 3.x, labeled "CTSM work incorporated into CESM 3.x"
or similar. This is the convergence point where the two bands reconnect.

## 4. Update the data lane (revised)

The data situation has been resolved through investigation. Replace the
previous "NOT PUBLISHED" framing with an accurate picture of the data
infrastructure.

The data lane should show three things:

**Data servers (infrastructure migration):**
- Old servers (FTP, SVN): solid bar through ~2025, label "CMIP6 data,
  used by CESM 2.2.x and earlier CTSM"
- New server (NCAR GDEX): starts ~2025, label "CMIP7 data + migrated
  CMIP6, used by CTSM 5.4.043+"
- Show the transition: ctsm5.4.002 still pointed at old servers,
  ctsm5.4.043 updated to new GDEX server

**NEON tower observations (from storage.neonscience.org):**
- Small, fast: 150 KB/month per site, 84 months (2018-2024)
- All 48 sites through Dec 2024
- Served from Google Cloud, downloads in seconds

**Practical note:** Global input data (~6 GB) is static per CTSM
version, downloaded once and cached. NEON tower data (~12 MB per site)
is trivial. The bottleneck was GDEX CDN reliability, not missing data.

## 5. Components flow UP into integration products

CLM, CIME, and NEON are components that get assembled into integration
products (CTSM releases, CESM releases). Docker containers build on
top of those integration products. The flow is:

```
Components:     CLM 6.0 ──┐
                CIME 6.1 ──┼──> CTSM 5.4.002 ──> ExSOIL Container
                NEON 48  ──┘

                CLM clm5.0 ──┐
                CIME 5.x   ──┼──> CESM 2.2.x ──> escomp/cesm-lab-neon
                CAM, POP...──┘         (+ custom CTSM graft)
```

Connection lines from CLM, CIME, and NEON lanes should go UP into the
CTSM and CESM release nodes. The ExSOIL container should NOT have
separate connection lines down to CLM or CIME. It inherits them
through CTSM 5.4.

## 6. Slightly expand ctsm5.2 component list if space allows

Show "CLM 5.1, CIME 6.0 (Python 3.13 issue), NEON ~47 sites" inside
the ctsm5.2 box so the reader can see why we didn't use it.

## Do NOT change

- The two-band layout (CESM top, CTSM/containers bottom) works well
- The ExSOIL container wrapping CTSM 5.4 is clear
- The "NOT CONNECTED" callout between CESM 2.x and NEON is effective
- The Key Takeaways section at the bottom
- The color coding scheme
