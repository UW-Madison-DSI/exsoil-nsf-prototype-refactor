# ADR-0007: QEMU emulation for multi-architecture CI builds

**Status:** Accepted
**Date:** 2026-06-17
**Deciders:** Steven Wangen

## Context

The ExSOIL container must build for two processor architectures: amd64
(Intel/AMD servers, most cloud infrastructure) and arm64 (Apple Silicon
Macs, newer cloud instances). Docker images contain compiled code that
is specific to a processor architecture, so a separate build is needed
for each.

GitHub Actions runners are amd64. To build arm64 images on these
runners, we need some form of cross-architecture execution.

## Decision

Use QEMU user-mode emulation on amd64 GitHub Actions runners to build
arm64 images. This is configured via `docker/setup-qemu-action@v3` in
the CI workflow.

## How QEMU works

QEMU translates instructions from one architecture to another at
runtime. When the CI runner builds the arm64 image, every arm64
instruction that build processes execute gets translated to equivalent
amd64 instructions on the fly. The actual CPU only sees native amd64
instructions.

This is analogous to a simultaneous interpreter: the build "speaks"
arm64, QEMU translates to amd64 in real time, and the host CPU executes
the translated instructions. It works, but it adds overhead.

**What QEMU handles well:** I/O-bound operations. Downloading files,
extracting archives, installing pre-built packages. The CPU spends most
of its time waiting for network or disk, so the translation overhead is
negligible.

**What QEMU handles poorly:** CPU-intensive computation. Compiling large
codebases, running numerical simulations, heavy memory operations. The
per-instruction translation overhead becomes dominant. This is why the
old amd64-only container crashed on Apple Silicon Macs: scientific
computation (cartopy rendering, model compilation) through QEMU's
emulation layer was slow and unstable.

## Why this works for our build

The Docker build is mostly I/O:
- `apt-get install`: downloading and unpacking .deb packages
- `mamba install`: downloading and extracting conda-forge binaries
- `git clone` + `git-fleximod update`: network-bound
- `wget` + `tar`: downloading and extracting input data tarballs

No Fortran compilation happens during the Docker build. CTSM's
`case.build` (which compiles CLM from source, ~100 seconds on native
arm64) runs at container runtime on the user's own hardware, not during
the image build. This is the key architectural choice that makes QEMU
viable: we ship source code and a toolchain, not compiled binaries.

## Alternatives considered

| Option | Pros | Cons |
|--------|------|------|
| **QEMU on amd64 runners (chosen)** | Zero cost, zero configuration beyond the setup action, works with standard GitHub Actions | arm64 build is 2-3x slower than native, memory-intensive operations can be unstable |
| **Native arm64 GitHub runners** | Fast, no emulation overhead | GitHub's `ubuntu-24.04-arm` runners are available but may require org-level configuration; third-party runners (Actuated, Buildjet) cost money |
| **Cross-compilation** | Build on native amd64, produce arm64 binaries | Not viable for our build. Conda-forge packages are pre-built per-architecture; the lockfile install must run on the target architecture to select the right binaries. |
| **Separate CI jobs per architecture** | Each job runs natively on its own runner type | Requires arm64 runner access, doubles CI configuration complexity |

## Risks

- **Disk space on CI runners.** GitHub runners have ~14 GB free. Our
  image is ~14.7 GB uncompressed. Building both architectures needs
  working space for intermediate layers. This is tight and may require
  pruning Docker cache before the build step.

- **Memory pressure.** The conda/mamba solver under QEMU uses more
  memory than native. GitHub runners have ~7 GB RAM. Large dependency
  solves can fail under emulation.

- **Build time.** A cold multi-arch build with embedded input data
  (5.5 GB download per architecture) can take 1-2 hours. The GitHub
  Actions cache mitigates this for subsequent builds (only changed
  layers rebuild).

- **Intermittent QEMU failures.** QEMU user-mode emulation occasionally
  hits edge cases in complex software. If the arm64 build starts
  failing intermittently, switching to native arm64 runners is the fix.

## When to revisit

- If arm64 CI builds become unreliable or take more than 2 hours
- If GitHub makes arm64 runners available at no additional cost for
  the org
- If we add Fortran compilation to the Docker build (currently runtime
  only)

## References

- Docker multi-platform builds: https://docs.docker.com/build/building/multi-platform/
- QEMU user-mode emulation: https://www.qemu.org/docs/master/user/main.html
- GitHub arm64 runners: https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories/
