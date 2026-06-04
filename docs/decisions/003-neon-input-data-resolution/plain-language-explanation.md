# Why the Container Can't Run Simulations Yet (Plain Language)

## The short version

The container has everything installed and working except for one
problem: when CLM tries to start a simulation, it needs to download
several large data files from NCAR's servers. Some of those files
don't exist on the servers yet. We know why, and we have a fix to
try.

## How a simulation gets its data

When you tell CLM "run a simulation at the Konza Prairie NEON site
for the years 2018-2021," it needs several kinds of input data:

**Surface data files (surfdata):**
- Soil properties (clay, sand, loam fractions), vegetation type
  (PFTs), topography, and land use history for the grid cell

**Atmospheric forcing data (DATM inputs):**
- Temperature, humidity, wind speed, precipitation, and solar
  radiation for every time step of the simulation, typically from
  the NEON tower's own gap-filled observations

**Global forcing and boundary data:**
- Nitrogen deposition (ndep), aerosol deposition (presaero),
  ozone concentrations (preso3), population density (for the fire
  model), crop calendars, and CO2 concentrations

CLM can't run without all of these. Before a simulation starts,
a script called `check_input_data` goes through the list and
downloads anything that's missing from NCAR's public file servers.

## What goes wrong

The download script checks NCAR's servers and several files come
back as "not found." The simulation stops before it even begins.

The files that are missing are the ones describing the global
background: nitrogen deposition, aerosols, ozone, population
density, and a few others. The site-specific files and weather
data are also missing, but for a related reason.

## Why the files are missing

This requires understanding one piece of climate modeling context:

Climate models use standardized sets of input data that correspond
to different "eras" of climate research. Right now there are two
relevant ones:

- **CMIP6** data: the established set, used for the last several
  years of research. All of these files exist on NCAR's servers.

- **CMIP7** data: the new set, currently being prepared for the
  next generation of climate projections. Some of these files exist
  (the ones covering the historical period, 1850-2023), but files
  covering future scenarios do not exist yet.

CTSM 5.4 introduced a setting called `CLM_CMIP_ERA` that controls
which set of files the model asks for. It's supposed to work like
this:

- If you're running a **future scenario** simulation (called SSP):
  use CMIP6 data (because CMIP7 future data doesn't exist yet)

- If you're running a **historical** simulation: use CMIP7 data
  (because it's newer and better for the historical period)

The NEON tower workflow falls into a gap between these two categories.

## The gap

NEON simulations cover 2018-2021. The historical period in climate
modeling ends around 2014. So NEON runs extend into the "future
scenario" time range, even though they're really just running through
recent observed years.

To get data covering 2018-2021, the NEON configuration tells the
model to use "SSP3-7.0" scenario data (this is just one specific
future scenario that happens to have data files covering recent years).

Here's the problem: the `CLM_CMIP_ERA` auto-detection looks at
the simulation type, not the forcing dates. NEON uses a simulation
type called "IHist" (historical with single-point data). Since
"IHist" doesn't have "SSP" in its name, the auto-detection says
"this is a historical run, use CMIP7 data."

But the model then tries to find CMIP7 versions of the SSP3-7.0
forcing files. Those CMIP7 SSP files don't exist. They haven't
been created yet.

If the auto-detection had recognized that the NEON case needs
SSP-period data and switched to CMIP6, it would find the files
just fine. The CMIP6 versions of all these SSP files are on the
servers and have been for years.

## The diagram

```
What the NEON case requests:        What auto-detection chooses:
  Simulation type: IHist        -->   CLM_CMIP_ERA = cmip7  (because IHist != SSP)
  Forcing dates: 2018-2021      -->   Look for CMIP7 SSP files
  Forcing scenario: SSP3-7.0         CMIP7 SSP files don't exist --> FAIL

What should happen:
  Forcing dates: 2018-2021      -->   These dates need SSP scenario data
  SSP scenario data             -->   CLM_CMIP_ERA should be cmip6
  CMIP6 SSP files exist         -->   SUCCESS
```

## The fix

Tell the model explicitly: "use CMIP6 data for this run." One line:

```
./xmlchange CLM_CMIP_ERA=cmip6
```

This isn't a workaround or a hack. The CTSM 5.4 release notes
themselves say that SSP-period data should use CMIP6. The
auto-detection just doesn't cover the specific case where a
non-SSP simulation type uses SSP-era forcing dates.

## What we still don't know

The `CLM_CMIP_ERA=cmip6` fix should resolve most of the missing
files (aerosols, ozone, nitrogen deposition, population density).
We haven't tested it yet.

There's one file that might not be resolved: the NEON site-specific
surface dataset (`surfdata_1x1_NEON_KONZ_...`). This file has
"ctsm5.4.0" in its name, and there may not be a CMIP6-era
equivalent. If this file is also missing after the fix, we'll need
to investigate whether it's available on the NEON-specific data
server or needs to be generated.

## What works right now

Everything except running the actual simulation:

- The container builds and runs on both Intel/AMD and Apple Silicon
- JupyterLab starts, notebooks load
- All Python packages work (xarray, cartopy, matplotlib, etc.)
- CLM compiles from Fortran source (case.build produces an executable)
- The NEON site workflow can create and configure cases for 48 sites
- The Getting Started notebook runs completely
- 90 automated tests pass

The model is ready to go. It just can't fetch its input data because
of this configuration mismatch.
