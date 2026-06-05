# Draft GitHub Issue for ESCOMP/CTSM

**Title:** Help finding input data for ctsm5.4.002 NEON single-point runs (external to NCAR)

---

Hi,

I'm working on setting up a containerized CTSM environment for running NEON tower site simulations (using Docker, outside of NCAR infrastructure). I've been able to build and configure cases successfully with ctsm5.4.002, but I'm running into trouble at the `check_input_data` stage when trying to run a KONZ transient case.

Several input files don't seem to be available on the public data servers listed in `config_inputdata.xml`. I wanted to check whether I might be misconfiguring something, or whether there's a different data source I should be pointing at.

I noticed a few related issues that suggest this area is actively being worked on:
- #2994 (proposed CI check for inputdata on SVN server)
- #4072 (recent CMIP7 CO2 data issue)
- #3966 (CMIP7 data download access)

So apologies if this is already known or in progress.

### What I'm doing

```
./create_newcase --case KONZ --compset IHist1PtClm60Bgc \
  --res CLM_USRDAT --machine container \
  --user-mods-dirs cime_config/usermods_dirs/clm/NEON/KONZ
./case.setup
./case.build   # succeeds
./case.submit  # fails during check_input_data
```

### Files that aren't found

Some examples of files that `check_input_data` reports as missing on all servers (FTP, SVN, and the NEON-specific server at storage.neonscience.org):

- `lnd/clm2/surfdata_esmf/NEON/ctsm5.4.0/surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.nc`
- `lnd/clm2/paramdata/clm60_params.ctsm6_li2024.c250822.nc`
- `lnd/clm2/firedata/clmforc.Li_2025_CMIP7_SSP3CMIP6_hdm_0.5x0.5_simyr1850-2100_c250717.nc`
- `lnd/clm2/snicardata/snicar_optics_5bnd_c013122.nc`
- `cdeps/datm/ozone/O3_surface.f09_g17.CMIP6-SSP3-7.0-WACCM.001.monthly.201501-210012.nc`

There are about 20 files total across surface data, parameter files, forcing data (ozone, ndep, aerosol, population density), crop calendars, and a few others.

The bulk of the inputdata downloads fine (around 5-7 GB downloaded successfully before it hits the missing files).

### What I've tried

- Verified that `config_inputdata.xml` includes the standard NCAR servers plus the NEON-specific server at storage.neonscience.org
- Tried setting `CLM_CMIP_ERA=cmip6` in case the default `cmip7` was requesting files that aren't available yet (didn't resolve it)
- Checked the NEON server directly via HTTP: the `surfdata_1x1_NEON_KONZ...ctsm5.4.0` file returns 404

### My setup

- CTSM tag: `ctsm5.4.002`
- Running in Docker (Ubuntu 24.04, arm64)
- Compilers and libraries from conda-forge (gfortran, MPICH, NetCDF, HDF5)
- `case.build` completes successfully

### Questions

1. Is there a different data server or download method I should be using for ctsm5.4 NEON input data? I noticed the EMBER Tutorial mentions pre-staged data on the CTSM JupyterHub, so I'm wondering if these files are available through a different path.

2. Is there a recommended CTSM tag for NEON single-point runs that has all its input data available on the public servers? I'd be happy to use an older tag if that's more straightforward.

3. Is there anything in my configuration that might be causing the namelist generator to request files that shouldn't be needed for a basic NEON transient run?

Any pointers would be really helpful. Thank you!
