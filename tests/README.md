# Container Validation Tests

These tests verify that the multi-arch Docker image provides the functionality
required to run CESM tutorials, CTSM/NEON workflows, and scientific Python
analysis. They are designed to catch architecture-specific failures (amd64 vs
arm64) and dependency breakage after environment updates.

## Test Tiers

Tests are organized into tiers by execution time and what they validate:

### Tier 0: Smoke Tests (< 30 seconds)

Quick checks that the container environment is correctly assembled.

| Category | What it validates | Based on |
|----------|------------------|----------|
| Python imports | All packages from CESM tutorial notebooks import | CESM tutorial diagnostics (basics_clm.ipynb, basics_cam.ipynb) |
| CESM/CTSM modules | `ctsm`, `CIME` Python packages importable | CTSM run_neon workflow |
| Compilers | gfortran, gcc, g++, cmake, make present and functional | CESM case.build requirements |
| MPI | mpiexec runs, mpif90 compiles Fortran+MPI | CESM parallel execution |
| NetCDF libraries | libnetcdf, libhdf5, libpnetcdf present | CESM I/O layer |
| CESM install | Source tree, scripts, machine configs in place | CESM tutorial quickstart |
| Environment | PROJ_DATA, CONDA_PREFIX, PYTHONPATH set correctly | Container configuration |
| Regression | Bundled six.py removed, dateutil works | Known build issue (see ADR-0002) |

### Tier 1: Case Creation (< 2 minutes)

Validates the CIME case management workflow without building or running.

| Test | What it validates | Based on |
|------|------------------|----------|
| query_config --compsets | Compset database is accessible | CESM tutorial step 1 |
| query_config --grids | Grid database is accessible | CESM tutorial step 1 |
| create_newcase | Case directory created for I2000Clm50Sp/f19_g17 | CESM tutorial practical |
| case.setup | Generates build scripts and namelists | CESM tutorial practical |
| xmlchange / xmlquery | Can modify and read case XML variables | CESM tutorial practical |
| run_neon_v2 --help | NEON wrapper script parses arguments | Project-specific tool |

### Tier 2: Build and Analysis (5-20 minutes)

Validates that the Fortran build system and scientific Python analysis
stack work end-to-end.

| Test | What it validates | Based on |
|------|------------------|----------|
| case.build | Full CESM compilation (I2000Clm50Sp) | CESM tutorial build step |
| NetCDF round-trip | Write/read NetCDF with xarray | Foundation for all analysis |
| open_mfdataset | Multi-file lazy loading | CESM history file analysis |
| Weighted spatial mean | area * landfrac weighting | CLM diagnostics notebook |
| Monthly climatology | groupby('time.month').mean() | CLM diagnostics notebook |
| Zonal mean | Mean over longitude | CAM diagnostics notebook |
| Albedo calculation | FSR / FSDS with masking | CLM diagnostics notebook |
| Cartopy projections | PlateCarree, Robinson | Tutorial map plots |
| Map rendering | Coastlines, pcolormesh to PNG | Tutorial diagnostic figures |
| Dask lazy I/O | Chunked reads with .compute() | Large file analysis pattern |

## Running Tests

### Quick: smoke tests only

```bash
./tests/run_container_tests.sh tier0
```

### Full suite

```bash
./tests/run_container_tests.sh
```

### Specific tiers

```bash
./tests/run_container_tests.sh tier0 tier1
```

### Custom image name

```bash
./tests/run_container_tests.sh --image ghcr.io/uw-madison-dsi/exsoil-nsf-prototype-refactor:latest tier0
```

### Running inside an already-running container

```bash
docker exec <container> pytest /workspace/tests/ -m tier0 -v
```

## Adding Tests

1. Place new test files in `tests/` following the naming convention
   `test_tier{N}_{description}.py`.
2. Mark every test with the appropriate tier: `pytestmark = pytest.mark.tier{N}`.
3. Use fixtures from `conftest.py` for shared paths (`cesm_root`, `conda_prefix`,
   `scratch_dir`).
4. Keep tier 0 tests fast (no network, no compilation, no disk-heavy I/O).
5. Document what CESM tutorial exercise or workflow each test validates.
