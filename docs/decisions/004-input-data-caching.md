# Decision: Input data caching via GitHub Release assets

**Status:** Proposed
**Date:** 2026-06-17
**Context:** The ~6 GB of global input data required by CTSM is currently downloaded at runtime from NCAR's GDEX CDN, which is unreliable (3-hop redirect chain, intermittent failures). This adds 10-15 minutes of setup time on every fresh container run and makes the build non-deterministic.

---

## Problem

Every time a researcher starts the container for the first time (or on a fresh volume), the pre-download script fetches 31 files totaling ~6 GB from NCAR's servers. This is:

1. **Slow.** 10-15 minutes even when everything works.
2. **Unreliable.** NCAR's GDEX CDN intermittently fails. The pre-download script retries up to 5 times per file with server fallback (GDEX, SVN, FTP), but any single download can stall for minutes.
3. **A barrier to adoption.** A researcher who pulls the container and tries to run a simulation immediately hits a 15-minute wait with opaque wget output. This is the worst possible first experience.
4. **A CI risk.** If we bake data into the image, the build depends on NCAR's servers. A flaky CDN means flaky builds.

## Proposed approach: GitHub Release assets

Store the input data as compressed tarballs attached to a GitHub Release in the project repository. The Dockerfile fetches from GitHub's CDN during the build, so the data ships as a Docker layer.

### How it works

**One-time setup:**

1. Download all 31 input data files using the existing pre-download script (already validated, 100% success rate with retries).
2. Organize into 2-3 compressed tarballs grouped by category:
   - `ctsm-inputdata-params-v5.4.043.tar.zst` -- parameter files, snow optics, mesh files (~1.5 GB compressed)
   - `ctsm-inputdata-forcing-v5.4.043.tar.zst` -- atmospheric forcing scenarios, nitrogen deposition, aerosols (~2 GB compressed)
   - `ctsm-inputdata-land-v5.4.043.tar.zst` -- urban, crop, fire, dust, surface data (~0.5 GB compressed)
3. Create a GitHub Release (e.g., `inputdata-v5.4.043`) and upload the tarballs as release assets.
4. Record the download URLs (stable, versioned, served by GitHub's CDN).

**In the Dockerfile:**

```dockerfile
# Stage 2: after CTSM clone, before app layer
ARG INPUTDATA_RELEASE=https://github.com/UW-Madison-DSI/exsoil-nsf-prototype-refactor/releases/download/inputdata-v5.4.043

RUN mkdir -p /home/user/inputdata \
    && for f in ctsm-inputdata-params-v5.4.043.tar.zst \
                ctsm-inputdata-forcing-v5.4.043.tar.zst \
                ctsm-inputdata-land-v5.4.043.tar.zst; do \
         wget -q -O /tmp/$f "${INPUTDATA_RELEASE}/$f" \
         && tar --zstd -xf /tmp/$f -C /home/user/inputdata \
         && rm /tmp/$f; \
       done
```

**Layer caching behavior:**

- The data layer is built once and cached. Subsequent builds that only change notebooks or scripts reuse it.
- Changing the CTSM version means creating a new release (`inputdata-v5.4.044`) and updating the `ARG`. This triggers a rebuild of the data layer only.

### Why GitHub Release assets

| Option | Pros | Cons |
|--------|------|------|
| **GitHub Release assets** | Fast CDN, no extra infrastructure, versioned per CTSM tag, no bandwidth metering on public repos, 2 GB per file limit is manageable with splitting | Need to manually upload when CTSM version changes; release assets are immutable (good for reproducibility) |
| **Git LFS** | Integrated with the repo, automatic on clone | 1 GB free storage (we need 6 GB), bandwidth metered ($5/month for 50 GB), slow build context with large files |
| **University S3** | Fastest on campus, no external dependency | Requires infrastructure coordination, not accessible off-campus without VPN, another system to maintain |
| **NCAR GDEX (current)** | No storage cost, always up-to-date | Unreliable, slow, 3-hop redirect chain, builds are non-deterministic |

GitHub Release assets are the best fit because: public repos have no bandwidth limits on release downloads, the URLs are stable and versioned, GitHub's CDN is fast globally, and it requires no infrastructure beyond what we already use.

### Size estimates

The 31 files total ~6 GB uncompressed. Zstandard compression on NetCDF data typically achieves 40-60% reduction:

| Category | Uncompressed | Estimated compressed | Files |
|----------|-------------|---------------------|-------|
| Parameters + mesh + snow | ~2.5 GB | ~1.2 GB | 12 files |
| Atmospheric forcing + N-dep | ~3.0 GB | ~1.5 GB | 8 files |
| Land surface (urban, crop, fire, dust) | ~0.5 GB | ~0.3 GB | 11 files |
| **Total** | **~6 GB** | **~3 GB** | **31 files** |

Each tarball stays under GitHub's 2 GB per-asset limit. Total release size: ~3 GB.

### Image size impact

| Configuration | Uncompressed | Compressed (registry) |
|--------------|-------------|----------------------|
| Current (no data) | ~7 GB | ~3 GB |
| With embedded data | ~13 GB | ~5-6 GB |
| Per architecture in registry | -- | ~5-6 GB each |
| Total registry storage per tag | -- | ~10-12 GB |

### What still downloads at runtime

Embedding the global data eliminates the 10-15 minute first-run download. Two categories still require runtime network access:

- **NEON tower forcing** (~150 KB/month per site). Downloaded when a researcher picks a site. Fast (Google Cloud), small, site-specific. No change needed.
- **NEON terrestrial observations** (for model-data comparison). Fetched on demand by `download_eval_files`. Variable size, not needed for simulation itself.

### Versioning strategy

One GitHub Release per CTSM version:

- `inputdata-v5.4.043` -- current
- `inputdata-v5.4.044` -- when/if we upgrade

The release tag matches the CTSM tag. The Dockerfile's `ARG INPUTDATA_RELEASE` points at the right one. Old releases stay available for reproducibility.

### Maintenance

When upgrading CTSM:

1. Run the pre-download script against the new version to identify any changed files.
2. Rebuild the tarballs.
3. Create a new GitHub Release with the new tag.
4. Update the `ARG` in the Dockerfile.
5. The next build pulls from the new release; old data layer is invalidated.

This is a manual step, but CTSM upgrades are infrequent (we've done one in the entire project lifetime) and the process is straightforward.

### Risks

- **GitHub rate limits on release downloads.** Public repos are generous, but a CI pipeline that rebuilds both architectures frequently could hit limits. Mitigation: Docker layer caching means the download happens once per CTSM version, not per build.
- **2 GB per-file limit.** Splitting into 3 tarballs handles this comfortably. If a future CTSM version has much larger data requirements, we may need more splits.
- **GitHub availability.** If GitHub is down, the build fails. This is true of any external dependency, and GitHub's uptime is better than NCAR's GDEX.

### Implementation steps

1. Run the pre-download script in a container to collect all 31 files.
2. Compress into 2-3 zstd tarballs by category.
3. Create a GitHub Release `inputdata-v5.4.043` and upload the tarballs.
4. Add the `RUN wget + tar` block to the Dockerfile (Stage 2, as its own layer).
5. Remove the pre-download script from the runtime startup path (keep it as a fallback tool).
6. Rebuild, test tier0+tier1+tier2, run end-to-end simulation.
7. Update documentation.
