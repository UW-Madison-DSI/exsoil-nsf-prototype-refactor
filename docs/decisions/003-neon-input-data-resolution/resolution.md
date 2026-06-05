# Resolution: NEON Input Data Availability

**Date:** 2026-06-05
**Status:** Fix identified, testing in progress

## Root cause (revised)

The input data for CTSM 5.4 was never missing. NCAR migrated their
data infrastructure between the ctsm5.4.002 release (December 2025)
and the current development branch (ctsm5.4.043, June 2026).

**Old infrastructure** (used by ctsm5.4.002):
- `ftp.cgd.ucar.edu` (FTP/wget)
- `svn-ccsm-inputdata.cgd.ucar.edu` (SVN)
- `storage.neonscience.org` (NEON-specific)

**New infrastructure** (used by ctsm5.4.043):
- `osdf-data.gdex.ucar.edu` (NCAR GDEX/OSDF data exchange)
- Redirects through `unl-cache.nationalresearchplatform.org` CDN

The data files that 5.4.002 referenced (parameter files, NEON surface
datasets, CMIP7 forcing) were generated and published to NCAR's new
GDEX server, but the `config_inputdata.xml` in 5.4.002 still pointed
at the old servers. The development branch (5.4.043) updated
`config_inputdata.xml` to use the new server, and also updated several
filenames (e.g., adding `.no_nan_fill` suffixes to surface datasets,
new parameter file timestamps).

## What this means

Our earlier diagnosis was partially wrong:
- We thought NCAR hadn't published the data. They had, just on a
  different server.
- We thought the CLM_CMIP_ERA flag was the issue. It wasn't; the
  server configuration was.
- We thought ctsm5.4.002 was a complete release with missing data.
  It was a release that shipped before the data infrastructure
  migration was reflected in the config files.

## The fix

Use **ctsm5.4.043** (or a recent development tag) instead of
ctsm5.4.002. The newer tag:
- Points `config_inputdata.xml` at NCAR's new GDEX server
- References updated filenames that exist on that server
- Includes 41 additional point releases of bugfixes and data updates

## Test status

A container built with ctsm5.4.043 is currently downloading input
data from `osdf-data.gdex.ucar.edu`. The files are returning HTTP 200
(verified via curl). The download is slow (CDN redirect chain) but
progressing. Waiting for completion to confirm all files resolve.

## Impact on the GitHub issue draft

The issue draft (`docs/ctsm-issue-draft.md`) may no longer be needed
if ctsm5.4.043 resolves the problem. If we do still file it, the
question changes from "where is the data?" to "should ctsm5.4.002's
config_inputdata.xml be updated to point at the GDEX server, or is
the recommendation to use a newer tag?"

## Impact on the decision trail

This adds a tenth step to the decision trail
(`docs/decisions/000-full-decision-trail.md`):

**Step 10: Data infrastructure migration.** The input data existed on
NCAR's new GDEX server all along. The ctsm5.4.002 release shipped
with `config_inputdata.xml` pointing at the old FTP/SVN servers.
Development tags (5.4.003 through 5.4.043) updated the config to
point at the new server and also updated several data filenames.
Using ctsm5.4.043 resolves the data download issue.

## Lessons

1. When a data download fails, the problem may be the server
   configuration rather than the data's existence. We spent
   significant time investigating CMIP era flags, version fallbacks,
   and data pipeline timelines when the actual issue was simpler:
   the config file pointed at the wrong server.

2. Development tags between releases contain important infrastructure
   changes, not just code fixes. The 41 point releases between
   5.4.002 and 5.4.043 included a data server migration that was
   invisible from the release notes.

3. Checking what changed in newer tags (`gh api repos/.../compare`)
   is a powerful diagnostic tool for "it worked for them but not
   for me" problems.
