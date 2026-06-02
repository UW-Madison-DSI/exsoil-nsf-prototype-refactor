"""
Tier 0: Smoke tests.

Validates that the container environment has all required components
installed and accessible. Based on the import sets and toolchain used
in CESM/CTSM tutorials (https://www.cesm.ucar.edu/events/tutorials).

Expected runtime: < 30 seconds total.
"""

import os
import shutil
import subprocess
import pytest

pytestmark = pytest.mark.tier0


# ── Python imports (from CESM tutorial diagnostics notebooks) ────────────

class TestPythonImports:
    """Every package used in CESM tutorial Python exercises must import."""

    def test_numpy(self):
        import numpy
        assert numpy.__version__

    def test_scipy(self):
        import scipy
        assert scipy.__version__

    def test_pandas(self):
        import pandas
        assert pandas.__version__

    def test_xarray(self):
        import xarray
        assert xarray.__version__

    def test_netcdf4(self):
        import netCDF4
        assert netCDF4.__version__

    def test_h5py(self):
        import h5py
        assert h5py.__version__

    def test_matplotlib(self):
        import matplotlib
        assert matplotlib.__version__

    def test_cartopy(self):
        import cartopy
        assert cartopy.__version__

    def test_cartopy_crs(self):
        import cartopy.crs as ccrs
        assert ccrs.PlateCarree()

    def test_cartopy_feature(self):
        import cartopy.feature as cfeature
        assert cfeature.COASTLINE

    def test_dask(self):
        import dask
        assert dask.__version__

    def test_bokeh(self):
        import bokeh
        assert bokeh.__version__

    def test_holoviews(self):
        import holoviews
        assert holoviews.__version__

    def test_hvplot(self):
        import hvplot
        assert hvplot.__version__

    def test_panel(self):
        import panel
        assert panel.__version__

    def test_geoviews(self):
        import geoviews
        assert geoviews.__version__

    def test_jupyterlab(self):
        import jupyterlab
        assert jupyterlab.__version__

    def test_ipykernel(self):
        import ipykernel
        assert ipykernel.__version__

    def test_esmpy(self):
        import esmpy
        assert esmpy.__version__

    def test_gdal(self):
        from osgeo import gdal
        assert gdal.VersionInfo()

    def test_rasterio(self):
        import rasterio
        assert rasterio.__version__

    def test_geopandas(self):
        import geopandas
        assert geopandas.__version__

    def test_shapely(self):
        import shapely
        assert shapely.__version__

    def test_fiona(self):
        import fiona
        assert fiona.__version__

    def test_sklearn(self):
        import sklearn
        assert sklearn.__version__

    def test_openai(self):
        import openai
        assert openai.__version__

    def test_boto3(self):
        import boto3
        assert boto3.__version__

    def test_s3fs(self):
        import s3fs
        assert s3fs.__version__


# ── CESM/CTSM Python modules ────────────────────────────────────────────

class TestCESMPythonModules:
    """CESM and CTSM Python packages must be importable."""

    def test_ctsm_import(self):
        from ctsm import add_cime_to_path
        assert add_cime_to_path

    def test_ctsm_path_utils(self):
        from ctsm.path_utils import path_to_ctsm_root
        assert path_to_ctsm_root

    def test_cime_import(self):
        import CIME
        assert CIME

    def test_cime_case(self):
        from CIME.case import Case
        assert Case

    def test_cime_utils(self):
        from CIME.utils import run_cmd_no_fail
        assert run_cmd_no_fail


# ── Compilers and MPI ───────────────────────────────────────────────────

class TestToolchain:
    """Fortran/C toolchain and MPI (required for CESM case.build)."""

    def test_gfortran_exists(self):
        assert shutil.which("gfortran"), "gfortran not found on PATH"

    def test_gcc_exists(self):
        assert shutil.which("gcc"), "gcc not found on PATH"

    def test_gxx_exists(self):
        assert shutil.which("g++"), "g++ not found on PATH"

    def test_cmake_exists(self):
        assert shutil.which("cmake"), "cmake not found on PATH"

    def test_make_exists(self):
        assert shutil.which("make"), "make not found on PATH"

    def test_mpiexec_exists(self):
        assert shutil.which("mpiexec"), "mpiexec not found on PATH"

    def test_gfortran_compiles(self, tmp_path):
        src = tmp_path / "hello.f90"
        exe = tmp_path / "hello"
        src.write_text('program hello\n  print *, "ok"\nend program hello\n')
        result = subprocess.run(
            ["gfortran", "-o", str(exe), str(src)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"gfortran failed: {result.stderr}"
        assert exe.exists()

    def test_mpi_runs(self):
        result = subprocess.run(
            ["mpiexec", "-n", "2", "hostname"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"mpiexec failed: {result.stderr}"

    def test_fortran_mpi_compiles(self, tmp_path):
        src = tmp_path / "mpi_hello.f90"
        exe = tmp_path / "mpi_hello"
        src.write_text(
            "program mpi_hello\n"
            "  use mpi\n"
            "  integer :: ierr, rank\n"
            "  call MPI_Init(ierr)\n"
            "  call MPI_Comm_rank(MPI_COMM_WORLD, rank, ierr)\n"
            '  print *, "rank", rank\n'
            "  call MPI_Finalize(ierr)\n"
            "end program mpi_hello\n"
        )
        result = subprocess.run(
            ["mpif90", "-o", str(exe), str(src)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"mpif90 failed: {result.stderr}"


# ── NetCDF / HDF5 libraries ─────────────────────────────────────────────

class TestNetCDFLibraries:
    """Conda-forge NetCDF/HDF5 libraries must be present and linked."""

    def test_nc_config(self, conda_prefix):
        nc_config = os.path.join(conda_prefix, "bin", "nc-config")
        if os.path.exists(nc_config):
            result = subprocess.run(
                [nc_config, "--version"], capture_output=True, text=True,
            )
            assert result.returncode == 0
        else:
            pytest.skip("nc-config not found")

    def test_nf_config(self, conda_prefix):
        nf_config = os.path.join(conda_prefix, "bin", "nf-config")
        if os.path.exists(nf_config):
            result = subprocess.run(
                [nf_config, "--version"], capture_output=True, text=True,
            )
            assert result.returncode == 0
        else:
            pytest.skip("nf-config not found")

    def test_libnetcdf_exists(self, conda_prefix):
        lib = os.path.join(conda_prefix, "lib", "libnetcdf.so")
        assert os.path.exists(lib), f"{lib} not found"

    def test_libhdf5_exists(self, conda_prefix):
        lib = os.path.join(conda_prefix, "lib", "libhdf5.so")
        assert os.path.exists(lib), f"{lib} not found"

    def test_libpnetcdf_exists(self, conda_prefix):
        lib = os.path.join(conda_prefix, "lib", "libpnetcdf.so")
        assert os.path.exists(lib), f"{lib} not found"


# ── CESM directory structure ─────────────────────────────────────────────

class TestCESMInstall:
    """CESM source tree and scripts must be in the expected locations."""

    def test_cesmroot_set(self):
        assert os.environ.get("CESMROOT"), "CESMROOT not set"

    def test_cime_machine_set(self):
        assert os.environ.get("CIME_MACHINE") == "container"

    def test_cesmdataroot_set(self):
        assert os.environ.get("CESMDATAROOT"), "CESMDATAROOT not set"

    def test_create_newcase_exists(self, cesm_root):
        script = os.path.join(cesm_root, "cime", "scripts", "create_newcase")
        assert os.path.exists(script)

    def test_query_config_exists(self, cesm_root):
        script = os.path.join(cesm_root, "cime", "scripts", "query_config")
        assert os.path.exists(script)

    def test_config_machines_xml(self, cesm_root):
        path = os.path.join(
            cesm_root, "cime", "config", "cesm", "machines", "config_machines.xml",
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "container" in content

    def test_config_compilers_xml(self, cesm_root):
        path = os.path.join(
            cesm_root, "cime", "config", "cesm", "machines", "config_compilers.xml",
        )
        assert os.path.exists(path)
        content = open(path).read()
        assert "CONDA_PREFIX" in content


# ── Environment and paths ────────────────────────────────────────────────

class TestEnvironment:
    """Container environment variables and paths must be set correctly."""

    def test_proj_data_set(self):
        proj_data = os.environ.get("PROJ_DATA")
        assert proj_data, "PROJ_DATA not set"
        assert os.path.isdir(proj_data), f"PROJ_DATA dir missing: {proj_data}"

    def test_conda_prefix_set(self):
        assert os.environ.get("CONDA_PREFIX"), "CONDA_PREFIX not set"

    def test_pythonpath_includes_analytics(self):
        pythonpath = os.environ.get("PYTHONPATH", "")
        assert "analytics_modules" in pythonpath

    def test_analytics_modules_importable(self):
        import analytics_modules
        assert analytics_modules

    def test_run_neon_on_path(self):
        assert shutil.which("run_neon_v2"), "run_neon_v2 not on PATH"

    def test_jupyter_on_path(self):
        assert shutil.which("jupyter"), "jupyter not on PATH"


# ── Dateutil / six regression ────────────────────────────────────────────

class TestDateutilRegression:
    """Bundled six.py in CESM tree must not shadow conda-forge six."""

    def test_dateutil_tz_imports(self):
        from dateutil.tz import tz
        assert tz

    def test_six_moves_imports(self):
        from six.moves import _thread
        assert _thread

    def test_six_resolves_to_conda(self, conda_prefix):
        import six
        assert "site-packages" in six.__file__, (
            f"six resolved to {six.__file__}, expected conda site-packages"
        )
