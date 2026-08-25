# Local Testing Review: exsoil-nsf-prototype-refactor

**Date:** 2026-05-28
**Tester:** Steven Wangen
**Machine:** Apple Silicon Mac (aarch64), Docker Desktop with Rosetta enabled
**Image:** `ghcr.io/uw-madison-dsi/exsoil-nsf-prototype-refactor:latest` (amd64-only)
**Notebook tested:** `notebooks/Data_Hub.ipynb`

## Summary

We cloned the freshly scrubbed `exsoil-nsf-prototype-refactor` repo and attempted to pull, run, and test the container image locally. The image runs under Rosetta x86 emulation on Apple Silicon. While some notebook cells execute successfully, the Jupyter kernel reliably deadlocks during heavy import or rendering cells, making local notebook testing on Apple Silicon effectively unusable.

## What worked

- Container image pulls and starts successfully under `--platform linux/amd64`
- JupyterLab UI loads and is responsive
- Simple cells (`1+1`, package verification) execute fine
- Lightweight imports and NEON API calls succeed
- S3 data access works when credentials are provided
- All problematic code runs fine from the CLI (`docker exec ... python3 -c "..."`) in under 5 seconds

## Issues found

### 1. Jupyter kernel deadlocks under Rosetta emulation (blocker)

The Jupyter kernel repeatedly hangs when executing cells that trigger multithreaded native code (numpy, matplotlib, cartopy). The deadlock pattern, captured via external `docker stats` monitoring:

- CPU spikes to 100-219%
- PIDs jump from ~2 to 17-38 (thread pool spawning)
- CPU drops to 0% and stays there (deadlock)
- Memory plateaus (kernel is not OOM-killed, just frozen)
- JupyterLab loses contact with the kernel ("File Save Error - Failed to fetch")

Thread-level inspection (`/proc/<pid>/task/*/wchan`) confirmed 7+ threads stuck on `rt_mutex_schedule`, a real-time mutex deadlock specific to Rosetta's x86 translation layer.

**Attempted mitigations (none resolved the issue):**

| Mitigation | Result |
|---|---|
| `OPENBLAS_NUM_THREADS=1` | Reduced thread count (38 -> 18) but still deadlocked |
| All threading env vars set to 1 (OMP, MKL, NUMEXPR, VECLIB, NUMBA, GOTO, BLOSC) | Same deadlock pattern |
| Pre-caching cartopy shapefiles | No effect (hang is on imports, not downloads) |
| Container restart between attempts | Temporarily clears the deadlock, but it recurs |

**Root cause:** ZMQ's IO threads (used by ipykernel for Jupyter communication) interact badly with Rosetta's mutex implementation. The same code runs flawlessly from the CLI, confirming the issue is specific to the Jupyter kernel's threaded event loop under emulation.

**Resolution path:** Build a native arm64 container image. The base image (`escomp/cesm-lab-neon:latest`) is amd64-only and does not publish an arm64 variant, so this requires either an upstream contribution or building a custom arm64 base.

### 2. PROJ warning on cartopy import (minor)

```
ERROR 1: PROJ: proj_create_from_database: Open of /opt/ncar/conda/share/proj failed
```

GDAL cannot find the PROJ database because `PROJ_DATA` is not set. The file exists at `/opt/ncar/conda/share/proj/proj.db` and cartopy still functions, but the warning is confusing.

**Fix:** Add `ENV PROJ_DATA="/opt/ncar/conda/share/proj"` to the Dockerfile. (Change made locally, not yet deployed.)

### 3. No root-level .env.example for local dev

The `.env.example` file only exists in `deploy/jupyterhub/`. For standalone `docker run` usage (local testing, development), there should be a `.env.example` at the project root documenting the required credentials:

- `COS_ACCESS_KEY_ID` (required for S3/COS data access)
- `COS_SECRET_ACCESS_KEY` (required for S3/COS data access)
- `AWS_DEFAULT_REGION` (defaults to `us-east-1`)
- `OPENAI_API_KEY` (optional, for LLM notebook)

### 4. No arm64 container image

The base image `escomp/cesm-lab-neon:latest` publishes only an amd64 manifest (single-arch, not a manifest list). The CI workflow (`.github/workflows/docker-publish.yml`) already has QEMU and Buildx configured, so adding `platforms: linux/amd64,linux/arm64` is a one-line change once a suitable arm64 base exists.

## Artifacts

- `container_profile.csv` - External resource monitoring log (CPU%, memory, PIDs sampled every ~2s during testing)
- Dockerfile changes (local, uncommitted): added `ENV PROJ_DATA`

## Recommended next steps

1. **Build arm64 image** - Either contribute arm64 support upstream to `escomp/cesm-lab-neon` or create a custom arm64-compatible base image. This is a prerequisite for local development on Apple Silicon.
2. **Test on amd64** - Until arm64 is available, validate notebooks on an amd64 machine (cloud VM, deployment server, or CI).
3. **Add root-level .env.example** - Document credentials needed for standalone container usage.
4. **Deploy PROJ_DATA fix** - Commit and push the Dockerfile change to eliminate the PROJ warning.
