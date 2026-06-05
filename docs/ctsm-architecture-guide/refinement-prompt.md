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

## 4. Connect the data gap to ExSOIL with a concrete label

The "NOT PUBLISHED" CMIP7 marker should have a line or annotation
connecting it to the ExSOIL container with the label "blocks live
simulations" or "input data not on public servers." Make the
consequence explicit.

## 5. Add CMIP data evolution

Add a data lane at the bottom showing two bars:

**CMIP6:** Solid green bar spanning the full width. Label: "Fully
published. All servers." Draw thin connection arrows up to CESM 2.2.x
and CTSM 5.2 (these use CMIP6 data). Note: "CMIP6 SSP data available
(covers 2015-2100)."

**CMIP7:** Bar starting around 2025. Split into two segments:
- Left segment (solid): "Historical (1850-2023). Published."
- Right segment (red dashed): "SSP/future. NOT YET PRODUCED."
Draw connection arrow up to CTSM 5.4 with annotation: "CTSM 5.4
defaults to CMIP7, but NEON runs need SSP-era data (2018+) which
CMIP7 hasn't produced."

This explains the blocker: NEON simulations cover 2018-2021, which
falls after the historical period ends (~2014), so they need SSP
forcing data. CMIP6 has it. CMIP7 doesn't, yet.

## 6. Slightly expand ctsm5.2 component list if space allows

Show "CLM 5.1, CIME 6.0 (Python 3.13 issue), NEON ~47 sites" inside
the ctsm5.2 box so the reader can see why we didn't use it.

## Do NOT change

- The two-band layout (CESM top, CTSM/containers bottom) works well
- The ExSOIL container wrapping CTSM 5.4 is clear
- The "NOT CONNECTED" callout between CESM 2.x and NEON is effective
- The Key Takeaways section at the bottom
- The color coding scheme
