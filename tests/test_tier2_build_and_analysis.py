"""
Tier 2: Build and scientific analysis tests.

Validates that:
1. CESM case.build compiles a land-only case on this architecture.
2. The Python scientific stack can perform the analysis workflows
   taught in CESM tutorial diagnostics notebooks.

Reference:
- NCAR/CESM-Tutorial basics_clm.ipynb, basics_cam.ipynb
- CESM tutorial Python diagnostics exercises

Expected runtime: 5-20 minutes (mostly case.build compilation).
"""

import os
import subprocess
import numpy as np
import pytest

pytestmark = pytest.mark.tier2


def run(cmd: list[str], timeout: int = 600, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, **kwargs,
    )


# ── CESM case.build ─────────────────────────────────────────────────────

class TestCaseBuild:
    """
    Build a land-only CLM case (I2000Clm50Sp at f19_g17).
    This is the lightest full CESM build and validates that the
    Fortran compiler, MPI, NetCDF, and CESM build system all
    work together on this architecture.
    """

    COMPSET = "I2000Clm50Sp"
    RES = "f19_g17"

    @pytest.fixture(scope="class")
    def built_case(self, cesm_root, scratch_dir):
        case_path = scratch_dir / "test_build_i2000"
        create_script = os.path.join(cesm_root, "cime", "scripts", "create_newcase")

        result = run([
            create_script,
            "--case", str(case_path),
            "--compset", self.COMPSET,
            "--res", self.RES,
            "--machine", "container",
            "--run-unsupported",
        ])
        assert result.returncode == 0, (
            f"create_newcase failed:\n{result.stdout}\n{result.stderr}"
        )

        inputdata = os.path.join(os.environ.get("CESMDATAROOT", "/home/user"), "inputdata")
        os.makedirs(inputdata, exist_ok=True)

        result = run([str(case_path / "case.setup")], cwd=str(case_path))
        assert result.returncode == 0, (
            f"case.setup failed:\n{result.stdout}\n{result.stderr}"
        )

        result = run(
            [str(case_path / "case.build")],
            cwd=str(case_path),
            timeout=1200,
        )
        assert result.returncode == 0, (
            f"case.build failed:\n{result.stdout}\n{result.stderr}"
        )
        return case_path

    def test_build_produces_executable(self, built_case):
        bld_dir = built_case / "bld"
        exes = list(bld_dir.glob("cesm.exe")) + list(bld_dir.glob("*.exe"))
        assert len(exes) > 0, f"No executable found in {bld_dir}"


# ── NetCDF read/write round-trip ─────────────────────────────────────────

class TestNetCDFRoundTrip:
    """
    Write and read a NetCDF file with xarray, verifying the full
    HDF5/NetCDF stack works. This is the foundation for all CESM
    post-processing.
    """

    def test_write_and_read_netcdf(self, tmp_path):
        import xarray as xr

        lats = np.linspace(-90, 90, 19)
        lons = np.linspace(0, 360, 36, endpoint=False)
        data = np.random.randn(19, 36).astype(np.float32)

        ds = xr.Dataset(
            {"temperature": (["lat", "lon"], data)},
            coords={"lat": lats, "lon": lons},
            attrs={"title": "test dataset"},
        )

        path = tmp_path / "test_output.nc"
        ds.to_netcdf(path)
        assert path.exists()

        ds_read = xr.open_dataset(path)
        assert "temperature" in ds_read
        np.testing.assert_array_almost_equal(
            ds_read["temperature"].values, data, decimal=5,
        )
        ds_read.close()

    def test_open_mfdataset(self, tmp_path):
        import xarray as xr

        for i in range(3):
            ds = xr.Dataset(
                {"value": (["time", "x"], np.random.randn(1, 10).astype(np.float32))},
                coords={"time": [i], "x": np.arange(10)},
            )
            ds.to_netcdf(tmp_path / f"part_{i}.nc")

        ds_multi = xr.open_mfdataset(str(tmp_path / "part_*.nc"), combine="by_coords")
        assert ds_multi.dims["time"] == 3
        ds_multi.close()


# ── Scientific analysis workflows (from CESM tutorial notebooks) ────────

class TestXarrayAnalysis:
    """
    Operations from CESM tutorial diagnostics: weighted averages,
    groupby, calculated fields, subsetting. These exercise the
    xarray/numpy/dask stack on patterns students actually use.
    """

    @pytest.fixture
    def sample_clm_dataset(self):
        import xarray as xr
        import pandas as pd

        times = pd.date_range("2000-01-01", periods=12, freq="MS")
        lats = np.linspace(-90, 90, 19)
        lons = np.linspace(0, 360, 36, endpoint=False)
        np.random.seed(42)

        return xr.Dataset(
            {
                "TSA": (
                    ["time", "lat", "lon"],
                    260 + 30 * np.random.rand(12, 19, 36).astype(np.float32),
                ),
                "RAIN": (
                    ["time", "lat", "lon"],
                    np.random.exponential(1e-6, (12, 19, 36)).astype(np.float32),
                ),
                "FSDS": (
                    ["time", "lat", "lon"],
                    200 + 100 * np.random.rand(12, 19, 36).astype(np.float32),
                ),
                "FSR": (
                    ["time", "lat", "lon"],
                    50 + 30 * np.random.rand(12, 19, 36).astype(np.float32),
                ),
                "landfrac": (["lat", "lon"], np.random.rand(19, 36).astype(np.float32)),
                "area": (["lat", "lon"], np.ones((19, 36), dtype=np.float32)),
            },
            coords={"time": times, "lat": lats, "lon": lons},
        )

    def test_weighted_spatial_mean(self, sample_clm_dataset):
        """Tutorial exercise: area-weighted global mean temperature."""
        ds = sample_clm_dataset
        weights = ds["landfrac"] * ds["area"]
        weighted_mean = (ds["TSA"] * weights).sum(["lat", "lon"]) / weights.sum()
        assert weighted_mean.dims == ("time",)
        assert len(weighted_mean) == 12
        assert 260 < float(weighted_mean.mean()) < 300

    def test_monthly_climatology(self, sample_clm_dataset):
        """Tutorial exercise: groupby monthly climatology."""
        ds = sample_clm_dataset
        clim = ds["TSA"].groupby("time.month").mean("time")
        assert "month" in clim.dims
        assert clim.sizes["month"] == 12

    def test_zonal_mean(self, sample_clm_dataset):
        """Tutorial exercise: zonal mean (average over longitude)."""
        ds = sample_clm_dataset
        zonal = ds["TSA"].mean(dim=["time", "lon"])
        assert zonal.dims == ("lat",)
        assert len(zonal) == 19

    def test_albedo_calculation(self, sample_clm_dataset):
        """Tutorial exercise: albedo = FSR / FSDS where FSDS > 0."""
        ds = sample_clm_dataset
        albedo = ds["FSR"] / ds["FSDS"].where(ds["FSDS"] > 0)
        assert not albedo.isnull().all()
        assert float(albedo.mean()) > 0


class TestCartopyPlotting:
    """
    Cartopy map projections used in CESM tutorial diagnostic plots.
    Validates that projections instantiate and transforms work,
    without rendering to a display (headless container).
    """

    def test_platecarree_projection(self):
        import cartopy.crs as ccrs
        proj = ccrs.PlateCarree()
        assert proj

    def test_robinson_projection(self):
        import cartopy.crs as ccrs
        proj = ccrs.Robinson()
        assert proj

    def test_add_cyclic_point(self):
        from cartopy.util import add_cyclic_point
        data = np.random.randn(19, 36)
        lons = np.linspace(0, 350, 36)
        cyclic_data, cyclic_lons = add_cyclic_point(data, coord=lons)
        assert cyclic_data.shape[1] == 37
        assert len(cyclic_lons) == 37

    def test_matplotlib_agg_backend(self):
        """Headless rendering must work (no display in container)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 4, 9])
        plt.close(fig)

    def test_cartopy_map_render(self, tmp_path):
        """Render a simple map to PNG (exercises cartopy + shapefile data)."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        fig, ax = plt.subplots(subplot_kw={"projection": ccrs.PlateCarree()})
        ax.add_feature(cfeature.COASTLINE)
        ax.set_global()

        out = tmp_path / "map_test.png"
        fig.savefig(out, dpi=72)
        plt.close(fig)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_pcolormesh_on_map(self, tmp_path):
        """Tutorial pattern: pcolormesh of a 2D field on a map projection."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs

        lats = np.linspace(-90, 90, 19)
        lons = np.linspace(0, 360, 36, endpoint=False)
        data = np.random.randn(19, 36)

        fig, ax = plt.subplots(subplot_kw={"projection": ccrs.Robinson()})
        lon2d, lat2d = np.meshgrid(lons, lats)
        ax.pcolormesh(
            lon2d, lat2d, data,
            transform=ccrs.PlateCarree(), cmap="RdBu_r",
        )
        ax.set_global()

        out = tmp_path / "pcolormesh_test.png"
        fig.savefig(out, dpi=72)
        plt.close(fig)
        assert out.exists()
        assert out.stat().st_size > 5000


class TestDaskLazyIO:
    """
    CESM tutorials use xarray with Dask for lazy loading of large
    history files. Validate that chunked reads work.
    """

    def test_lazy_open_with_chunks(self, tmp_path):
        import xarray as xr

        data = np.random.randn(100, 19, 36).astype(np.float32)
        ds = xr.Dataset(
            {"TSA": (["time", "lat", "lon"], data)},
            coords={
                "time": np.arange(100),
                "lat": np.linspace(-90, 90, 19),
                "lon": np.linspace(0, 360, 36, endpoint=False),
            },
        )
        path = tmp_path / "big_file.nc"
        ds.to_netcdf(path)

        ds_lazy = xr.open_dataset(path, chunks={"time": 10})
        assert ds_lazy["TSA"].chunks is not None
        result = ds_lazy["TSA"].mean(dim="time").compute()
        assert result.shape == (19, 36)
        ds_lazy.close()
