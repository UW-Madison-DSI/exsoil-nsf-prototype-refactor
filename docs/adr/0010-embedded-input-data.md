# ADR-0010: Embed CTSM input data in Docker image via GitHub Release assets

**Status:** Accepted
**Date:** 2026-06-17
**Deciders:** Steven Wangen

## Context

CTSM requires ~7.9 GB of global input data (30 NetCDF files) to run
simulations: parameter files, atmospheric forcing scenarios, nitrogen
deposition, mesh files, surface datasets, and more. This data is static
per CTSM version.

Previously, this data was downloaded at runtime from NCAR's servers via
a pre-download script. NCAR's GDEX CDN is unreliable (3-hop redirect
chain, intermittent failures), making the download take 10-15 minutes
and sometimes fail entirely. This was the single worst first-run
experience for researchers.

## Decision

Store the input data as compressed tarballs and split raw files on a
GitHub Release (`inputdata-v5.4.043`) and fetch them during the Docker
build. The data ships as a Docker layer in the image.

**Assets on the release:**
- `ctsm-inputdata-atm-v5.4.043.tar.zst` (870 MB) -- atmosphere, ozone,
  aerosols, CO2, topography, meshes
- `ctsm-inputdata-lnd-v5.4.043.tar.zst` (103 MB) -- land surface data
  (excluding nitrogen deposition)
- `ctsm-inputdata-ndep1-v5.4.043.tar.zst` (192 MB) -- nitrogen
  deposition, small file
- `ctsm-inputdata-ndep2-v5.4.043.{aa,ab,ac}` (4.4 GB total) --
  nitrogen deposition, large file split into <2 GB parts

The large nitrogen deposition file (4.4 GB, barely compresses) is split
as raw bytes rather than as a compressed tarball, because zstd
decompression of a reassembled split stream proved unreliable.

**Build arg:** `EMBED_INPUTDATA=true` (default). Set to `false` for
lightweight development builds that don't need simulation data.

**CI behavior:** Tag and main pushes embed data. PR builds skip it
(faster feedback).

## Consequences

- Image size increased from ~7 GB to ~14.7 GB uncompressed.
- Researchers pull a larger image but never wait for NCAR downloads.
  The trade-off: ~4 extra minutes of pull time eliminates 10-15 minutes
  of unreliable runtime setup.
- GitHub's CDN is fast and reliable. Public repos have no bandwidth
  limits on release asset downloads.
- The data layer caches in Docker. Subsequent builds that only change
  notebooks or scripts do not re-download data.
- One GitHub Release per CTSM version. When upgrading CTSM, create a
  new release with new tarballs and update the Dockerfile `ARG`.

**What still downloads at runtime:**
- NEON tower forcing (~150 KB/month per site, from Google Cloud). Small,
  fast, site-specific.
- NEON terrestrial observations (for model-data comparison, on demand).

## Supporting artifacts

- `scripts/download-release-data.sh` -- called by the Dockerfile during
  build
- `scripts/create-inputdata-release.sh` -- helper to regenerate
  tarballs and upload a new release
- `scripts/pre-download-inputdata.sh` -- retained as fallback and for
  collecting files when creating new tarballs
- Decision doc: `docs/decisions/004-input-data-caching.md`
