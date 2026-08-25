# Revision Notes for Version Lineage Diagram

Based on review of `lineage_chart.png`. The diagram's layout and
swim-lane structure is good. These revisions focus on making the
ExSOIL container's relationship to CTSM 5.4 clearer and correcting
a few factual details.

## Priority 1: Make ExSOIL container visually part of CTSM 5.4

The current diagram shows the ExSOIL container as a separate node on
the Docker lane that happens to be near CTSM 5.4 in time. It should
communicate that the ExSOIL container IS CTSM 5.4.002 repackaged for
arm64 with project-specific tools added on top.

Suggested approach: instead of two separate nodes, show the ExSOIL
container as a wrapper or extension of the CTSM 5.4.002 node. Options:

- **Concentric boxes:** CTSM 5.4.002 as an inner box, ExSOIL container
  as an outer box that encloses it, with labels for the added layers
  (arm64 support, Python analysis stack, project notebooks)
- **Stacked:** CTSM 5.4.002 node with the ExSOIL container directly
  on top/below, connected by a thick solid line or "contains" arrow
- **Annotation:** A bold callout arrow from ExSOIL to CTSM 5.4 that
  says "= CTSM 5.4.002 + arm64 build + Python analysis tools"

The key message: ExSOIL is not a fork or a separate product. It's
CTSM 5.4.002 in a Docker container with our analysis code on top.

## Priority 2: Show NEON connecting to CTSM releases

The NEON swim lane should connect upward to each CTSM release that
includes it (ctsm5.1.dev114, ctsm5.2, ctsm5.3, ctsm5.4), not just
to the escomp Docker image. NEON is a feature of CTSM, and every
CTSM release since 5.1.dev114 includes it. The connection lines
from NEON to each CTSM node make this clear.

Also connect NEON to CESM 3.x (dashed) since it will arrive there
via CTSM.

## Priority 3: Show CTSM development starting before the first tagged release

The CTSM swim lane currently starts at ctsm5.1.dev114 (Nov 2022),
which makes it look like CTSM development began after the escomp
Docker image. Add a point or line segment starting around early 2021
labeled "CTSM dev branch" to show that development was underway
before the first NEON-tagged release. The escomp Docker image was
built FROM a development snapshot of CTSM, not the other way around.

## Priority 4: Show what the data gap blocks

The CMIP7 "not published" indicator at bottom right is good but
should connect specifically to CTSM 5.4 (and by extension the ExSOIL
container) with a label like "blocks live simulations" or "input data
not yet on public servers." This is the single remaining blocker.

## Minor corrections

- The escomp/cesm-lab-neon image should show connections to BOTH
  CESM 2.2 (for the framework/CIME) AND a dev CTSM branch (for the
  NEON capability). It was a hybrid. Currently it looks connected
  only to CESM.

- CESM 3.x should be more clearly visible in the top right. It's
  the future convergence point where CTSM's NEON work enters the
  full Earth system model.

## Priority 5: Components flow UP into integration products

The inheritance direction matters. CLM, CIME, and NEON are components
that get assembled into integration products (CTSM releases, CESM
releases). Docker containers build on top of those integration
products. The flow is:

```
Components:     CLM 6.0 ──┐
                CIME 6.1 ──┼──> CTSM 5.4.002 ──> ExSOIL Container
                NEON 48  ──┘

                CLM clm5.0 ──┐
                CIME 5.x   ──┼──> CESM 2.2.x ──> escomp/cesm-lab-neon
                CAM, POP...──┘         (+ custom CTSM graft)
```

Connection lines from the CLM, CIME, and NEON lanes should go UP
into the CTSM and CESM release nodes. The ExSOIL container should
NOT have separate connection lines down to CLM or CIME. It inherits
them through CTSM 5.4. This makes the assembly relationship clear:
components are composed into releases, releases are packaged into
containers.

## What the revised diagram should make immediately obvious

A reader glancing at this diagram should understand in 5 seconds:

1. The ExSOIL container is built on CTSM 5.4.002
2. CTSM 5.4.002 includes the NEON tower workflow
3. There is a data availability gap blocking simulations
4. The old escomp image was a non-standard hybrid
5. CESM 3.x will eventually bring everything together
