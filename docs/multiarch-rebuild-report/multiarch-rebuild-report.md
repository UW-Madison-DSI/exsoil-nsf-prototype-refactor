# Multi-Platform Container Rebuild Report

## Section 1: Overview

### What was rebuilt and why

This project runs the NCAR CESM (Community Earth System Model) climate modeling framework inside a Docker container. Researchers pull the container image, launch it, and open JupyterLab in their browser to run analysis notebooks against CESM simulation data. The container packages everything needed: an operating system, scientific Fortran/C libraries, the CESM source code and build system, a full Python scientific stack (NumPy, xarray, cartopy, etc.), and JupyterLab itself.

The original container image (`escomp/cesm-lab-neon`) was built three years ago on CentOS 8 (which lost security support in December 2021) and only supported Intel/AMD processors. It shipped Python 3.7 (end-of-life since June 2023) and hundreds of outdated packages. Most critically, it could not run natively on Apple Silicon Macs (M1/M2/M3/M4), which use a different processor architecture called ARM64. Team members on these machines had to run the container through a translation layer that was 2-3x slower and crashed frequently during computationally intensive operations like cartopy map rendering and CESM model compilation. The container was rebuilt from scratch on Ubuntu 24.04, with native support for both processor architectures, modern packages, and a reproducible build system.

### What multi-platform support means

A Docker image is compiled code, and compiled code is specific to a processor architecture. An image built for Intel/AMD (called "amd64" or "x86_64") contains machine instructions that ARM processors cannot execute directly, and vice versa. When you run an amd64 image on an ARM Mac, Docker uses a technology called QEMU emulation to translate instructions on the fly. This works, but it is slow, uses more memory, and can trigger subtle bugs in complex software.

Multi-platform support means publishing a single image tag (like `latest`) that actually contains two architecture-specific images behind the scenes, organized in what Docker calls a "manifest list." When someone runs `docker pull`, their Docker client automatically selects the correct image for their machine. An engineer on an Intel Linux server gets the amd64 image. An engineer on an M3 MacBook gets the arm64 image. Neither needs to know or care about the other architecture. The image tag, the `docker run` command, and all the documentation stay identical.

### The approach

Rather than cross-compiling the old image, the team rebuilt the entire stack on a new foundation. The original image compiled five scientific libraries (MPICH, HDF5, NetCDF-C, NetCDF-Fortran, PNetCDF) from Fortran and C source code inside the container, a process that took 30-45 minutes and was architecture-specific. The rebuild replaced all of this with pre-built binary packages from conda-forge, a community package repository that publishes builds for both amd64 and arm64. This reduced build time to about five minutes and eliminated the most complex source of architecture-dependent code.

The project also upgraded the CESM version from 2.2.0 to 2.2.2, trimmed the Python environment from approximately 400 packages to 35 direct dependencies, introduced reproducible lockfiles for both architectures, and created a three-tier automated test suite that validates the container on each platform.

### What changed for downstream consumers

Nothing, operationally. The image is published to the same GitHub Container Registry address. `docker pull` and `docker run` commands are unchanged. On Apple Silicon Macs, the container now runs natively instead of through emulation, so it is faster, more stable, and does not crash during heavy computation. On Intel/AMD machines, the container works as before, with updated package versions. The only user-visible difference is that Python is now 3.11 (up from 3.7), JupyterLab is version 4 (up from 2), and package versions have jumped by 4-6 years. Notebooks that relied on APIs that changed between those versions may need minor updates.

---

## Section 2: Technical Detail

### Base image selection

**Decision:** `ubuntu:24.04` (untagged digest, pulled at build time).

**Rationale (documented in [ADR-0001](adr/0001-arm64-base-image.md)):** The upstream image used CentOS 8 (EOL). Six alternatives were evaluated:

| Option | Multi-arch | Compressed size | EOL | Community fit |
|--------|-----------|-----------------|-----|---------------|
| Ubuntu 24.04 | amd64, arm64 + 4 more | ~29 MB | Apr 2029 (free), 2036 (ESM) | Pangeo, Jupyter Stacks |
| AlmaLinux 9 | amd64, arm64 | ~30 MB | May 2032 | CERN, Fermilab |
| Rocky Linux 9 | amd64, arm64 | ~44 MB | May 2032 | CIQ HPC |
| Debian 12 | amd64, arm64 | ~47 MB | Jun 2028 (LTS) | Less common for HPC |
| jupyter/scipy-notebook | amd64, arm64 | ~1.5 GB | Follows Ubuntu | Jupyter community |
| condaforge/miniforge3 | amd64, arm64 | ~148 MB | Follows Ubuntu | Pangeo pattern |

Ubuntu was selected because both Pangeo and Jupyter Docker Stacks have standardized on it, it has the longest free support window, and its `apt` ecosystem has the best-documented path for Fortran/C scientific library compilation. AlmaLinux would have been appropriate if HPC cluster binary compatibility were needed, but this is a JupyterHub teaching/analysis platform.

No tag pinning beyond the major release (`24.04`) is used. *Inferred:* the team accepts minor Ubuntu patch drift between builds since the conda-forge lockfile controls the scientific stack versions.

### Build tooling

**CI engine:** GitHub Actions (`ubuntu-latest` runners).

**Multi-arch mechanism:** QEMU user-mode emulation via `docker/setup-qemu-action@v3`, with Buildx (`docker/setup-buildx-action@v3`) managing the multi-platform build. There are no dedicated ARM64 runners or remote builders; the arm64 image is built under QEMU on amd64 CI hardware.

```yaml
# .github/workflows/docker-publish.yml (line 59)
platforms: linux/amd64,linux/arm64
```

**Layer cache:** GitHub Actions cache backend (`type=gha`, `mode=max`). This persists Docker layer cache across CI runs, so only changed layers rebuild.

**Registry:** GHCR at `ghcr.io/${{ github.repository }}`, authenticated via `GITHUB_TOKEN`.

### Dockerfile structure

The Dockerfile (`./Dockerfile`, 174 lines) uses a three-stage build, all stages deriving from the first:

```
Stage 1 ("base")   FROM ubuntu:24.04
Stage 2 ("cesm")   FROM base
Stage 3 ("app")    FROM cesm        <-- final image
```

This is a linear chain, not a parallel multi-stage build. There is no separate builder stage; compilation tools (gfortran, gcc, cmake) remain in the final image because CESM's `case.build` workflow requires them at runtime.

#### Stage 1: base (~6 min cold, cached thereafter)

1. `apt-get` installs system packages: compilers (`build-essential`, `gfortran`), build tools (`cmake`, `m4`, `make`), version control (`git`, `subversion`), Perl XML processing (`perl`, `libxml-libxml-perl`), and utilities.

2. Miniforge installer detects architecture automatically:
   ```dockerfile
   RUN wget -qO /tmp/miniforge.sh \
       "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh"
   ```
   This resolves to `Miniforge3-Linux-x86_64.sh` on amd64 and `Miniforge3-Linux-aarch64.sh` on arm64. No `TARGETARCH` or `TARGETPLATFORM` Buildx variables are used; the build relies on the emulated `uname -m` reporting correctly under QEMU.

3. Conda environment installed from explicit lockfiles. The architecture selection happens at runtime within the `RUN` command:
   ```dockerfile
   RUN ARCH=$(uname -m) \
       && if [ "$ARCH" = "aarch64" ]; then LOCKFILE=/tmp/conda-linux-aarch64.lock; \
          else LOCKFILE=/tmp/conda-linux-64.lock; fi \
       && mamba install --name base --file "$LOCKFILE" --yes --quiet
   ```
   Pip-only packages (openai, jiter, distro) are extracted from `# pip` comment lines in the lockfile and installed separately with `--no-deps`.

4. Optional Dask layer controlled by build arg:
   ```dockerfile
   ARG INSTALL_DASK_DISTRIBUTED=false
   ```

#### Stage 2: cesm (~2 min, network-bound)

1. Clones CESM 2.2.2 with `--depth 1` and runs `checkout_externals` to pull ~15 component repositories.

2. Patches PIO2 Fortran source to disable filter APIs incompatible with modern NetCDF-C:
   ```dockerfile
   && for f in .../pio_nf.F90 .../pio.F90; do \
        sed -i 's/PIO_HAS_PAR_FILTERS/DISABLED_PIO_HAS_PAR_FILTERS/g' "$f"; \
        sed -i 's/NC_HAS_MULTIFILTERS/DISABLED_NC_HAS_MULTIFILTERS/g' "$f"; \
        sed -i 's/NC_HAS_QUANTIZE/DISABLED_NC_HAS_QUANTIZE/g' "$f"; \
        sed -i 's/NC_HAS_ZSTD/DISABLED_NC_HAS_ZSTD/g' "$f"; \
        sed -i 's/NC_HAS_BZ/DISABLED_NC_HAS_BZ/g' "$f"; \
      done
   ```

3. Installs custom machine configuration XML files that point CESM's build system at `$CONDA_PREFIX` library paths instead of `/usr/local`.

4. `chown -R user:cesm` transfers ownership of the entire CESM tree to the runtime user. This adds ~10 seconds and an extra layer but is required because CESM creates build artifacts in-tree.

#### Stage 3: app (seconds, rebuilds on code changes)

Copies project-specific code: analytics modules, run_neon_v2 wrapper, notebooks. Removes CESM's bundled `six.py` files that shadow the conda-forge version. Sets `PYTHONPATH` to include four CESM/CTSM module directories.

### Cross-compilation strategy

There is no cross-compilation. Both architectures build natively (amd64 on native hardware, arm64 under QEMU emulation on the CI runner). This is viable because:

- **No source compilation of Fortran/C libraries in the image build.** All scientific libraries (MPICH, HDF5, NetCDF, PNetCDF) come from conda-forge pre-built binaries. The old approach of compiling these from source would have been prohibitively slow under QEMU.
- **The Miniforge installer and conda-forge lockfiles are architecture-specific.** Each architecture gets its own resolved dependency graph with platform-appropriate binary packages.
- **CESM Fortran compilation happens at runtime (`case.build`), not during the Docker build.** The image ships source code and a toolchain; the user compiles when they create a case. This was tested and confirmed working on native arm64 in 78 seconds.

*Inferred:* The QEMU-emulated arm64 conda install takes roughly 2-3x longer than native, but since it is a pure package download-and-extract (no compilation), this is acceptable for CI. A full rebuild is estimated at 10-15 minutes under QEMU.

### Manifest list publishing

The `docker/build-push-action@v6` with `platforms: linux/amd64,linux/arm64` produces an OCI manifest list automatically. Each tag in the registry (`:latest`, `:main`, `:sha-<short>`, semver tags) points to a manifest list containing both platform-specific images. No manual `docker manifest create` or `docker manifest push` is needed.

**Tagging strategy** (from `docker/metadata-action@v5`):

| Trigger | Tags produced |
|---------|---------------|
| Push to `main` | `:latest`, `:main`, `:sha-<7chars>` |
| Semver tag `v1.2.3` | `:1.2.3`, `:1.2`, `:1`, `:sha-<7chars>` |
| Pull request | `:pr-<n>` (built, not pushed) |
| Manual dispatch | Same as branch push |

### Image size and layers

| Metric | Value |
|--------|-------|
| Uncompressed size (arm64) | 6.83 GB |
| Layer count | 28 |
| Dominant layers | conda environment (~800 MB packages), CESM source tree (~2 GB with all component repos), Ubuntu base + apt packages (~550 MB) |

The image is large because it includes the full CESM source tree (12+ component repositories with git history) and a comprehensive scientific Python stack. The `--depth 1` clone limits git history, but the source tree itself is substantial. There is no slim or distroless variant; the runtime requires compilers, make, and the full conda environment for `case.build`.

*Inferred:* Compressed/pushed size to GHCR is likely 2.5-3.5 GB per architecture. With two architectures, total registry storage per tag is roughly 5-7 GB.

### Dependency management and reproducibility

The project uses a three-file system documented in [ADR-0003](adr/0003-conda-environment-strategy.md):

1. **`environment.yml`** (human-maintained): ~35 direct dependencies with loose version constraints. Pins `python >=3.11,<3.12` (CIME 2.2.x uses `import imp`, removed in Python 3.12) and `cmake >=3.28,<4` (CESM's PIO uses `cmake_minimum_required(VERSION 3.0.2)` incompatible with cmake 4.x).

2. **`conda-lock.yml`** (generated, 409 KB): Unified lockfile produced by `conda-lock lock -f environment.yml -p linux-64 -p linux-aarch64 --mamba`. Contains exact versions and hashes for both platforms.

3. **`conda-linux-{64,aarch64}.lock`** (generated, ~54 KB each): Explicit lockfiles rendered from `conda-lock.yml` via `conda-lock render`. These are what `mamba install --file` consumes at build time.

Update workflow: edit `environment.yml`, run `conda-lock lock`, run `conda-lock render` for both platforms, commit all four files.

### CESM build compatibility fixes

Six compatibility issues were discovered and resolved to make CESM 2.2.2 compile with conda-forge's modern GCC (15.x) and NetCDF-C (4.9+) on arm64. These are documented in [ADR-0002 Implementation Notes](adr/0002-arm64-build-strategy.md):

| Issue | Root cause | Fix | Location |
|-------|-----------|-----|----------|
| `rdtsc` asm error in GPTL | x86-only instruction (`HAVE_NANOTIME`) | Removed `-DHAVE_NANOTIME -DBIT64` from GPTL CPPDEFS | `config_compilers.xml` |
| MPI type mismatch in `perf_utils.F90` | GCC 10+ strict type checking | `-fallow-argument-mismatch` | `config_compilers.xml` |
| BOZ hex literal error in CLM | GCC 10+ strict BOZ checking | `-fallow-invalid-boz` | `config_compilers.xml` |
| `_FillValue` undeclared in PIO2 | NetCDF-C renamed macro to `NC_FillValue` | `-D_FillValue=NC_FillValue` | `config_compilers.xml` |
| PIO2 filter API mismatch | NetCDF headers advertise filter functions PIO2 doesn't implement | `sed` patches on `pio_nf.F90`, `pio.F90` | `Dockerfile` |
| `cmake_minimum_required(VERSION 3.0.2)` | cmake 4.x removed compat with <3.5 | Pin `cmake >=3.28,<4` in `environment.yml` | `environment.yml` |

Additional non-compilation fixes: CESM 2.2.0 to 2.2.2 (SVN deprecation), Python 3.12 to 3.11 (CIME `import imp`), bundled `six.py` removal, `XML::LibXML` Perl module addition, `USER` env var, `standard_script_setup.py` PYTHONPATH, `ctsm.download_utils` fallback.

### Testing strategy

A three-tier pytest framework runs inside the container via `tests/run_container_tests.sh`:

```bash
./tests/run_container_tests.sh                    # all tiers
./tests/run_container_tests.sh tier0              # smoke only (~7s)
./tests/run_container_tests.sh tier0 tier1        # smoke + case creation (~10s)
./tests/run_container_tests.sh tier2              # includes case.build (~90s)
```

| Tier | Tests | Runtime | What it validates |
|------|-------|---------|-------------------|
| 0 | 63 | ~4s | Python imports (28 packages), CIME/CTSM module imports, gfortran/gcc/mpiexec presence and functionality, Fortran+MPI compilation, NetCDF library presence, CESM install integrity, env vars, dateutil/six regression |
| 1 | 12 | ~3s | `query_config --compsets/--grids`, `create_newcase` (I2000Clm50Sp/f19_g17), `case.setup`, `xmlchange`/`xmlquery` round-trip, `run_neon_v2 --help` |
| 2 | 14 | ~85s | Full `case.build` producing `cesm.exe` (78s compilation), NetCDF read/write round-trip, `open_mfdataset`, weighted spatial mean, monthly climatology, zonal mean, albedo calculation, cartopy map rendering (PlateCarree, Robinson, pcolormesh), Dask chunked lazy I/O |

**Result:** 89/89 pass on native arm64 in 94 seconds.

Tests are based on CESM tutorial exercises from [cesm.ucar.edu/events/tutorials](https://www.cesm.ucar.edu/events/tutorials), covering the standard workshop workflow (create case, setup, build) and Python diagnostic patterns (xarray weighted averages, cartopy map plots).

The test runner mounts `tests/` read-only into the container and installs pytest at runtime (`pip install -q pytest`). *Inferred:* pytest is not included in the image to avoid bloating it for non-testing use.

Currently, CI does not run the test suite automatically. The tests are designed for manual validation after a rebuild or before a release. *Inferred:* Adding a test job to the GitHub Actions workflow that runs at least tier0+tier1 on both architectures would be a natural follow-up.

### Known limitations and follow-ups

1. **No CI test integration.** The test suite exists but is not wired into the GitHub Actions workflow. The `case.build` test (tier 2) takes ~90 seconds per architecture, which is reasonable for CI but has not been added yet.

2. **CESM model run not tested.** The tests validate that `case.build` produces `cesm.exe`, but do not execute a model run (`case.submit`). A 1-day CLM simulation would require downloading ~1 GB of input data, which is impractical in CI without a persistent data cache.

3. **amd64 not tested locally.** All local testing was on native arm64 (Apple Silicon). The amd64 path has not been validated beyond CI builds. The architecture-selection logic (`uname -m` in the Dockerfile) and the amd64 lockfile (`conda-linux-64.lock`) exist but have not been exercised through the test suite.

4. **Image size.** At ~7 GB uncompressed, the image is large. The CESM source tree (with 12+ component git repos) is the dominant contributor. A production optimization would be to separate the CESM build tools into a builder stage and copy only compiled artifacts, but CESM's in-tree build model makes this difficult.

5. **PIO2 source patches are fragile.** The `sed` replacements on PIO Fortran files disable filter APIs by renaming preprocessor macros. This works for CESM 2.2.2 but will need re-evaluation if the PIO2 or NetCDF-C versions change. A better long-term fix would be to update PIO2 to a version that properly supports modern NetCDF filter APIs.

6. **CIME Python 3.12 incompatibility.** CIME 2.2.x uses `import imp` (removed in Python 3.12), so Python is pinned to 3.11. Newer CIME versions (from CESM 3.x) have fixed this, but upgrading CIME independently of CESM is nontrivial.

7. **No `--mount=type=cache` for conda.** The Dockerfile does not use BuildKit cache mounts for the conda package cache. Adding `--mount=type=cache,target=/opt/conda/pkgs` to the `mamba install` step could speed up cache-miss rebuilds.
