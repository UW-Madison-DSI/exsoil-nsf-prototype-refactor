# Getting Started

## What is this?

This container gives you a pre-configured CTSM environment for running
single-point CLM simulations at NEON tower sites and analyzing the
output. Everything you need is already installed: CTSM 5.4 with NEON
usermods for 48 sites, the full CIME case management toolchain, and a
Python analysis stack (xarray, cartopy, matplotlib, and friends). You
open JupyterLab in your browser and start working.

The goal is to remove the infrastructure burden. Instead of spending
days compiling libraries, configuring compilers, and debugging Fortran
dependency chains, you spend your time on the science: designing
experiments, running simulations, and interpreting results.

![Version Lineage](ctsm-architecture-guide/lineage-chart.png)

The container is built on CTSM 5.4.002. For a detailed guide to how
all the components fit together, see the
[architecture guide](ctsm-architecture-guide/ctsm-architecture-guide.html).

## What is inside

### CTSM 5.4 with NEON usermods

The container includes CTSM at tag `ctsm5.4.002` with site-specific
usermods for 48 NEON tower locations. Each usermods directory contains
the grid cell, surface datasets, and namelist overrides needed to run
CLM at that site. You can create a point simulation at Konza Prairie or
Harvard Forest with a single command.

The CTSM source code, CIME infrastructure, and all component
dependencies (CDEPS, CMEPS, MOSART, ParallelIO) are checked out and
ready. The Fortran compilers (gfortran via conda-forge) and MPI
libraries (MPICH) are pre-installed. `case.build` compiles natively on
the container's architecture in about two minutes.

### Python analysis environment

The analysis stack is the standard set of tools you would expect for
working with CLM output:

| Purpose | Packages |
|---------|----------|
| NetCDF I/O | xarray, netCDF4, h5py, h5netcdf |
| Computation | numpy, scipy, pandas, scikit-learn |
| Visualization | matplotlib, cartopy, bokeh, holoviews, hvplot, panel |
| Geospatial | cartopy, geopandas, rasterio, gdal, shapely, esmpy |
| Large datasets | dask (chunked lazy loading) |
| Cloud data | boto3, s3fs, fsspec |

Everything is pinned via conda-lock for reproducibility across
platforms. The same versions resolve on both Intel/AMD and Apple
Silicon.

### Multi-platform support

The container runs natively on both Intel/AMD (amd64) and Apple Silicon
(arm64) machines. If you are on a newer Mac, this means no emulation
overhead and no kernel crashes during heavy cartopy rendering or Fortran
compilation. Docker selects the right architecture automatically when
you pull the image.

## Quick start

### 1. Launch the container

```bash
docker run --rm -p 8888:8888 exsoil-arm64-test
```

Copy the URL from the terminal output and open it in your browser. You
will see the JupyterLab interface.

### 2. Open the introductory notebook

Navigate to `notebooks/Getting_Started_CTSM_NEON.ipynb` and run it
cell by cell. It walks through the environment, demonstrates NetCDF I/O
and cartopy map rendering, shows you which NEON sites are available, and
creates a sample case at Konza Prairie. No credentials needed.

### 3. Read simulation output

**No credentials are needed.** The analysis helpers read the output your
own runs produce, inside the container:

```python
from analytics_modules import open_ctsm_hist

ds = open_ctsm_hist("KONZ", 2018)          # daily stream
ds = open_ctsm_hist("KONZ", stream="monthly")
```

`open_ctsm_hist` searches under `CTSM_OUTPUT_ROOT`, which defaults to
**`/home/user`** — the container home, and the directory the run wrappers
archive into. That default is why the call above needs no configuration.

It also works out the details that vary between runs, so you do not have
to: which of several archive layouts the run used (these differ between
the `run_tower` and `run_neon_v2.py` wrappers), whether the files use the
current CTSM 5.4 stream names (`h1a` daily, `h0a` monthly) or the older
`h1`/`h0`, and which NetCDF variant they are stored in. If nothing
matches, it raises and lists every path it tried rather than handing back
an empty result.

To get file paths instead of a dataset — the evaluation helpers take file
lists:

```python
from analytics_modules import find_ctsm_hist_files
files = find_ctsm_hist_files("KONZ", 2018)
```

**Running analysis outside the container.** If you copy an archive to your
own machine and analyse it there, point the reader at it:

```bash
export CTSM_OUTPUT_ROOT=~/exsoil-baseline-konz
```

The `/home/user` default is a container path and will not resolve on a
host.

**Reading the shared S3 fixtures (optional, legacy).** Earlier sample data
lives in a UW-restricted S3 bucket. It is not needed for normal use and is
slated for removal. To reach it, set credentials in a `.env` file:

```
COS_ACCESS_KEY_ID=your-access-key
COS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-east-1
CTSM_DATA_SOURCE=s3
```

```bash
docker run --rm -p 8888:8888 --env-file .env exsoil-arm64-test
```

Credentials are read only on the S3 path, so leaving them unset costs you
nothing.

### 4. Save your work

**Files inside the container are lost when it exits.** This matters more
than it sounds: a multi-year run takes hours and a full seven-year site
run produces roughly 119 MB of history files plus about 200 MB of logs.
Losing that to a `docker run --rm` is a bad afternoon.

Mount a local folder over the container home so cases, archives, and
notebooks persist:

```bash
docker run --rm -p 8888:8888 \
  -v $(pwd)/my-work:/home/user/my-work \
  exsoil-arm64-test
```

Anything saved under `my-work/` inside JupyterLab appears in `my-work/` on
your machine.

If you want simulation output to land in a mounted directory while keeping
the default reader configuration, pass `--output-root` to the run wrapper
and set `CTSM_OUTPUT_ROOT` to match:

```bash
docker run --rm -p 8888:8888 \
  -v $(pwd)/runs:/home/user/runs \
  -e CTSM_OUTPUT_ROOT=/home/user/runs \
  exsoil-arm64-test
```

## Typical workflow

1. **Choose a NEON site.** The container has usermods for 48 sites.
   Run the Getting Started notebook to see the full list, or check the
   [NEON site map](https://www.neonscience.org/field-sites/explore-field-sites).

2. **Create and configure a case.** The `run_neon_v2` wrapper handles
   CIME case creation, namelist configuration, and site-specific setup
   in one command. The project's notebooks call this for you.

3. **Build the model.** CIME's `case.build` compiles CLM from Fortran
   source for the specific case configuration. This takes about two
   minutes on a modern laptop and only needs to happen once per
   compset/resolution combination.

4. **Run the simulation.** CLM executes with the site's observed
   atmospheric forcing data. Run length depends on the experiment:
   a single year at one NEON site takes a few minutes; a multi-decade
   transient run takes longer.

5. **Analyze output.** CLM writes history files in NetCDF format. Load
   them with xarray, compute diagnostics (soil temperature profiles,
   carbon fluxes, water balance), compare against NEON tower
   observations, and visualize with matplotlib or cartopy.

The project's notebooks automate steps 2-4 through the `run_neon_v2`
wrapper script, so the typical interaction is: choose a site, choose
a perturbation (or none for a control run), execute the notebook cells,
and analyze the output.

## Project notebooks

| Notebook | Purpose | Needs credentials? |
|----------|---------|-------------------|
| **Getting_Started_CTSM_NEON** | Verify the environment, explore NEON sites, create a sample case | No |
| **Data_Hub** | Load CLM output, visualize soil profiles and time series | Yes, for now |
| **Design_Hub_v2** | Run CLM at NEON sites with forcing perturbations (precipitation scaling, temperature offsets, etc.) | Yes, for now |
| **Modeling_Hub** | Full modeling workflow with parameter sensitivity experiments | Yes, for now |
| **pft_perturbation_comparison** | Compare control and perturbed plant functional type simulations | Yes, for now |

> **"Yes, for now" is transitional.** The analysis library reads local
> output without credentials (see step 3 above), but these notebooks still
> contain their own S3 calls and, in Data_Hub's case, a cell that refuses
> to proceed without `COS_*` set. Repointing them at the local reader is
> tracked as Phase 2 onward of the hub integration work. Until then they
> need the S3 setup even though the code underneath them does not.

Start with **Getting_Started_CTSM_NEON** to confirm the container is
working on your machine. The other notebooks build on it.

## Where to learn more

- [CTSM User's Guide](https://escomp.github.io/CTSM/) -- model
  physics, configuration options, and output variables
- [NCAR CTSM Tutorial](https://github.com/NCAR/CTSM-Tutorial) --
  step-by-step tutorial notebooks from NCAR, including NEON exercises
- [NEON Data Portal](https://data.neonscience.org/) -- browse and
  download tower observations for model-data comparison
- [CLM Technical Note](https://escomp.github.io/ctsm-docs/) --
  detailed description of CLM's biogeophysics, biogeochemistry, and
  numerical methods
- [xarray Documentation](https://docs.xarray.dev/) -- the primary
  tool for working with NetCDF model output in Python
