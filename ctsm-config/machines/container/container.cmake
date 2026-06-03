# Container-specific cmake macros for CTSM with conda-forge libraries.
# Overlays ccs_config's default container.cmake to:
#   1. Remove x86-only GPTL flags (HAVE_NANOTIME, BIT64) for arm64 compat
#   2. Point library paths at $CONDA_PREFIX instead of /usr/local
#   3. Add _FillValue compat define for NetCDF-C version differences

if (COMP_NAME STREQUAL gptl)
  string(APPEND CPPDEFS " -DHAVE_VPRINTF -DHAVE_BACKTRACE -DHAVE_SLASHPROC -DHAVE_COMM_F2C -DHAVE_TIMES -DHAVE_GETTIMEOFDAY")
endif()
set(NETCDF_PATH "$ENV{CONDA_PREFIX}")
set(PNETCDF_PATH "$ENV{CONDA_PREFIX}")
string(APPEND LDFLAGS " -L$ENV{CONDA_PREFIX}/lib")
string(APPEND SLIBS " -lnetcdf -lnetcdff -llapack -lblas")
string(APPEND CFLAGS " -D_FillValue=NC_FillValue")
