# Getting Started

## What is this?

This container is a ready-to-use environment for running land surface
simulations at NEON ecological observatory sites using CTSM, the
Community Terrestrial Systems Model. You launch the container, open
JupyterLab in your browser, and start working with climate model
simulations and real-world observational data. No software installation
beyond Docker is required.

## What is inside the container?

The container packages three layers of software so you don't have to
install or configure any of them yourself:

### CTSM (the model)

CTSM is the Community Terrestrial Systems Model, developed and
maintained by NCAR (National Center for Atmospheric Research). It
simulates what happens at and below the land surface:

- **Soil physics:** how soil heats, cools, and holds water at different
  depths
- **Vegetation:** how plants grow, photosynthesize, and exchange carbon
  dioxide with the atmosphere
- **Hydrology:** how water moves through soil, runs off into rivers,
  and evaporates
- **Snow:** how snowpack accumulates, ages, and melts
- **Carbon cycling:** how carbon moves between soil, plants, and the
  atmosphere

CTSM is written in Fortran and runs as a compiled executable. The
container includes both the source code and the compiler toolchain
needed to build it.

### NEON tower site workflow

NEON (the National Ecological Observatory Network) operates 81
instrumented field sites across the United States. Each site has a tower
that continuously measures environmental variables like air temperature,
soil moisture at multiple depths, wind speed, and carbon dioxide fluxes.

The container comes pre-configured with site-specific settings for 48
NEON tower locations. This means you can run CTSM at a real-world site
(say, Konza Prairie in Kansas or Harvard Forest in Massachusetts), feed
it the actual weather that was observed at that tower, and then compare
CTSM's predictions against what the instruments measured. This is how
researchers evaluate whether the model is getting the science right.

### Python scientific stack

The container includes a full Python environment for analyzing model
output:

- **xarray** and **netCDF4** for reading CLM output files (which are in
  NetCDF format, the standard for climate data)
- **numpy**, **scipy**, and **pandas** for numerical computation
- **matplotlib** and **cartopy** for plotting and map visualization
- **bokeh**, **holoviews**, **hvplot**, and **panel** for interactive
  dashboards
- **JupyterLab** for the notebook interface you're reading this in
- **dask** for working with datasets too large to fit in memory

## Who is this for?

This container is designed for researchers, students, and developers
who want to:

- **Run CTSM at NEON sites** to evaluate land model performance against
  real observations
- **Analyze CLM output** with Python without worrying about Fortran
  compilation, library dependencies, or environment configuration
- **Develop and test perturbation experiments** (e.g., "what happens to
  soil carbon if precipitation increases by 10%?")
- **Reproduce results** across different machines (Intel/AMD desktops,
  Apple Silicon Macs, cloud servers) using the same container image

You do not need to know Fortran. The notebooks handle model execution
through wrapper scripts; your interaction is primarily through Python
and JupyterLab.

## How to run it

### Start the container

```bash
docker run --rm -p 8888:8888 exsoil-arm64-test
```

This starts JupyterLab inside the container. Copy the URL printed in
the terminal (it looks like `http://127.0.0.1:8888/lab?token=...`) and
open it in your browser.

### Open the getting started notebook

In JupyterLab's file browser, open `notebooks/Getting_Started_CTSM_NEON.ipynb`.
Run each cell in order. This notebook walks through the Python
environment, NetCDF I/O, map rendering, and NEON site setup without
requiring any credentials or data downloads.

### Run with S3 credentials (for full workflows)

The project's analysis notebooks (Data_Hub, Design_Hub, Modeling_Hub)
download forcing data and model output from S3 cloud storage. To use
them, create a `.env` file with your credentials and pass it to the
container:

```bash
docker run --rm -p 8888:8888 --env-file .env exsoil-arm64-test
```

The `.env` file should contain:

```
COS_ACCESS_KEY_ID=your-access-key
COS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-east-1
```

### Persist your work

By default, files created inside the container are lost when the
container stops. To keep your notebooks and output between sessions,
mount a local directory:

```bash
docker run --rm -p 8888:8888 \
  -v $(pwd)/my-work:/home/user/my-work \
  exsoil-arm64-test
```

Files saved under `/home/user/my-work` inside the container will appear
in the `my-work/` directory on your host machine.

## How the pieces fit together

```
You (browser)
    |
    v
JupyterLab (port 8888)
    |
    +--- Python notebooks
    |       |
    |       +--- xarray / matplotlib / cartopy (analysis + visualization)
    |       |
    |       +--- run_neon_v2.py (orchestrates CTSM runs)
    |
    +--- CTSM source tree (/opt/ncar/ctsm)
    |       |
    |       +--- CIME (build system: create_newcase, case.setup, case.build)
    |       |
    |       +--- CLM Fortran code (compiled at runtime via case.build)
    |       |
    |       +--- NEON usermods (48 site configurations)
    |
    +--- conda-forge libraries
            |
            +--- MPICH, HDF5, NetCDF, PNetCDF (I/O and parallel computing)
            +--- gfortran, gcc (compilers for building CLM)
```

The typical workflow is:

1. **Choose a NEON site** (e.g., KONZ for Konza Prairie)
2. **Create a case** using CIME's `create_newcase` with the site's usermods
3. **Set up the case** (`case.setup` generates namelists and build scripts)
4. **Build the model** (`case.build` compiles the Fortran code, ~2 min)
5. **Run the simulation** (`case.submit` executes CLM, minutes to hours
   depending on run length)
6. **Analyze output** in Python using xarray to load the NetCDF history
   files and matplotlib/cartopy to visualize results

Steps 2-5 are handled by the `run_neon_v2` wrapper script in the
project's notebooks, so you typically don't need to run CIME commands
directly.

## Project notebooks

| Notebook | What it does | Requires credentials? |
|----------|-------------|----------------------|
| `Getting_Started_CTSM_NEON` | Environment check, NEON site discovery, case creation demo | No |
| `Data_Hub` | Load and visualize CLM output from S3, soil profile plots | Yes |
| `Design_Hub_v2` | Run CTSM at NEON sites with perturbation experiments | Yes |
| `Modeling_Hub` | Full modeling workflow with parameter sensitivity analysis | Yes |
| `pft_perturbation_comparison` | Compare control and perturbed PFT simulations | Yes |

Start with `Getting_Started_CTSM_NEON` to verify the container is
working, then move to the other notebooks once you have S3 credentials
configured.

## Further reading

- [CTSM Documentation](https://escomp.github.io/CTSM/) -- official
  CTSM user guide covering model physics, configuration, and output
- [NCAR CTSM Tutorial](https://github.com/NCAR/CTSM-Tutorial) --
  hands-on tutorial notebooks from NCAR
- [NEON Data Portal](https://data.neonscience.org/) -- browse and
  download observational data from NEON tower sites
- [xarray Documentation](https://docs.xarray.dev/) -- the primary
  tool for working with CLM NetCDF output in Python
