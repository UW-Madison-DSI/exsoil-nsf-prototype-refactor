# ADR-0008: Patch NEON usermods to remove MPILIB=mpi-serial

**Status:** Accepted
**Date:** 2026-06-05
**Deciders:** Steven Wangen

## Context

The NEON tower workflow usermods
(`cime_config/usermods_dirs/clm/NEON/defaults/shell_commands`) set
`MPILIB=mpi-serial` on every case. This tells CIME to build CLM
against its own serial MPI stub library instead of a real MPI
implementation.

In a conda-forge environment, the real MPICH shared libraries
(`libmpich.so`, `libmpifort.so`) are always on the linker path via
`$CONDA_PREFIX/lib`. When CIME builds with mpi-serial, the resulting
binary statically links the CIME serial stubs but dynamically links
against the real MPICH library at runtime (because it's on the path).
The two conflict: MPICH's initialization check fires before the
stubs call `MPI_Init`, producing "Attempting to use an MPI routine
before initializing MPICH" and the model crashes immediately.

## Decision

Patch the NEON usermods in the Dockerfile to remove the
`MPILIB=mpi-serial` line:

```dockerfile
RUN sed -i '/MPILIB=mpi-serial/d' \
    ${CTSM_ROOT}/cime_config/usermods_dirs/clm/NEON/defaults/shell_commands
```

Cases then inherit the machine default (`mpich` from
`config_machines.xml`), which builds against the real MPICH library
and runs correctly via `mpiexec -n 1`.

A safety-net `mpirun mpilib="mpi-serial"` entry was also added to
`config_machines.xml` (uses `mpiexec -n 1`) in case any code path
still sets mpi-serial.

## Consequences

- End-to-end NEON simulations work (validated at KONZ, 1-day
  transient).
- This is a container-level workaround, not an upstream fix. Any
  CTSM upgrade will overwrite the usermods, so the `sed` patch must
  be reapplied.
- The workaround is specific to conda-forge environments where real
  MPICH is on the library path. It would not be needed on HPC systems
  where mpi-serial is isolated from system MPI.
- We have not yet reported this to ESCOMP/CTSM. Whether it belongs
  upstream depends on whether NCAR considers conda-forge a supported
  environment.
