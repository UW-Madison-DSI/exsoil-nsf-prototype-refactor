# Refinement Prompt v2 for Version Lineage Diagram

Starting from the current diagram. These are specific corrections and
one structural fix. The overall layout, colors, and information
architecture are good. Do not change the general structure.

## Corrections (factual errors)

1. **Ubuntu version in ExSOIL box:** Change "Ubuntu 20.04" to
   "Ubuntu 24.04"

2. **Python version in ExSOIL box:** Change "Xorg/Proton 13.3" to
   "Python 3.13"

3. **escomp/cesm-lab-neon date:** Change "Oct 2021" to "Oct 2022"

4. **ExSOIL container CTSM version:** Change "INCLUDES CTSM 5.4.002"
   to "INCLUDES CTSM 5.4.043". Also update the ExSOIL date from
   "Jan 2026 (planned)" to "Jun 2026"

5. **Tools list in ExSOIL box:** Change "cantera + obspy" to
   "cartopy, matplotlib, scipy"

## Structural fix: remove the escomp-to-ctsm5.2 line

There is a dashed line from the escomp/cesm-lab-neon box to
ctsm5.2.005 labeled "Grafts in dev CTSM branch (NEON work in
progress)." This line is incorrect. The escomp image (Oct 2022)
grafted a dev CTSM branch from circa 2022. It has no relationship
to ctsm5.2.005 (Aug 2024), which was released two years later.

Remove this line entirely. The escomp image should only connect to:
- CESM 2.2 (upward, dashed: "Uses CESM 2.2 framework/CIME")
- The CTSM development line at approximately 2022 (leftward or
  downward from the NEON evolution line, dashed: "Custom graft of
  dev CTSM branch circa 2022")

## Update: resolve the data blocker

The "BLOCKS & SIMULATIONS" red marker between ctsm5.4.002 and the
ExSOIL container is now outdated. We resolved the data issue by
upgrading to ctsm5.4.043, which uses the new GDEX server.

Options:
- Remove the red blocker indicator entirely
- Or change it to a green resolved indicator: "Resolved: ctsm5.4.043
  uses GDEX server"
- Keep the note in the data lane that ctsm5.4.002 pointed at old
  servers and ctsm5.4.043 uses GDEX (this is still useful context)

## Do NOT change

- The two-band layout (CESM top, CTSM/containers bottom)
- The component evolution lines (CLM, CIME, NEON)
- The "Not in CESM 2.x (never connected)" callout
- The component flow direction (up into CTSM/CESM)
- The data lane at the bottom
- The Key Takeaways section
- The color coding scheme
- The Component Key and Line Style Key
