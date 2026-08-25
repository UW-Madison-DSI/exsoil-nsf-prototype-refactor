"""Plots built on CTSM history output.

Split out of data_access, which exists to locate and open files and had
accumulated ~200 lines of rendering. Mixed responsibility is how sixty lines
of unreachable code survived review there: `plot_soil_profile_timeseries`
had a local-file branch that never executed, because `is_s3` was derived
from a literal assigned four lines above it.

The dependency runs one way: visualization imports data_access, never the
reverse.

Note this does **not** yet stop matplotlib being loaded by anything that
imports the package: `analytics_modules/__init__.py` imports this module and
`neon_eval_utils` eagerly, and both pull matplotlib. Making that lazy is
tracked separately.
"""

import time

import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import tqdm
import xarray as xr
import fsspec

from .data_access import (
    _engine_for_local,
    find_ctsm_hist_files,
    get_s3_client,
    get_storage_options,
    list_objects_under_prefix,
    resolve_source,
)

# Static soil-property fields repeated in every history file. Dropping them
# keeps a multi-file open from carrying redundant copies.
SOIL_PROFILE_DROP_VARS = [
    "ZSOI", "DZSOI", "WATSAT", "SUCSAT", "BSW", "HKSAT",
    "ZLAKE", "DZLAKE", "PCT_SAND", "PCT_CLAY",
]


def truncate_colormap(cmap, minval=0.0, maxval=1.0, n=100):
    """Return a sub-range of an existing matplotlib colormap.

    Soil profile plots use a slice of a colormap rather than the whole thing,
    so the extremes stay legible against the axes.
    """
    new_cmap = mcolors.LinearSegmentedColormap.from_list(
        f"trunc({cmap.name},{minval:.2f},{maxval:.2f})",
        cmap(np.linspace(minval, maxval, n)),
    )
    return new_cmap


def plot_soil_profile_timeseries(neon_site, var, year=None, *,
                                 source=None,
                                 output_root=None,
                                 stream: str = "daily",
                                 stream_token: str = "h1",
                                 input_label: str = "transient",
                                 endpoint_url="https://campus.s3.wisc.edu",
                                 storage_options=None):
    """Plot a soil profile against time and return the dataset behind it.

    Samples one timestep per file at roughly midday, so it is meant for the
    daily stream. Reads locally by default; S3 is opt-in through the same
    source resolution the rest of the module uses.

    Args:
        neon_site: NEON site code, e.g. "KONZ". Also used in the plot title.
        var: Variable to plot, "TSOI" (soil temperature, converted to °C) or
            "H2OSOI" (volumetric soil water).
        year: Year to filter on. None reads every year present.
        source: "local" (default) or "s3". Falls back to CTSM_DATA_SOURCE.
        output_root: Local search root. Defaults to CTSM_OUTPUT_ROOT.
        stream: "daily" or "monthly", used on the local path where the token
            is discovered from disk.
        stream_token: Stream token for the **S3 path only**, where nothing is
            on local disk to probe. Defaults to the unsuffixed "h1" because
            the S3 fixtures predate the CTSM 5.4 rename. Matches
            open_ctsm_hist_from_s3 and neon_notebook_wrapper.list_sim_files_s3.
        input_label: Case label, normally "transient".
        endpoint_url: S3 endpoint for non-AWS services.
        storage_options: fsspec/s3fs options; built from COS credentials if
            omitted, and only on the S3 path.

    Returns:
        xr.Dataset: the loaded data, for further analysis.

    Raises:
        FileNotFoundError: on the local path when nothing matches, listing
            the paths tried.
        RuntimeError: on the S3 path when no keys match.
    """

    # ---------------------------------------------------
    # Plot styling
    # ---------------------------------------------------
    time_0 = time.time()
    plt.rcParams["font.weight"] = "bold"
    plt.rcParams["axes.labelweight"] = "bold"
    font = {'weight': 'bold', 'size': 15}
    matplotlib.rc('font', **font)

    year_str = str(year) if year is not None else "*"
    case_name = f"{neon_site}.{input_label}.clm2"

    # ---------------------------------------------------
    # 1) Determine if S3 or local, find files
    # ---------------------------------------------------
    is_s3 = resolve_source(source) == "s3"
    sim_path = f"s3://clm-demonstration/archive_1/{neon_site}.{input_label}/lnd/hist/"

    if not is_s3:
        # ---- LOCAL ----
        # Delegated so this picks up every archive layout and both stream
        # naming conventions, and raises with what it tried instead of
        # returning an empty list.
        sim_files = find_ctsm_hist_files(
            neon_site, year, output_root=output_root,
            stream=stream, input_label=input_label,
        )
        print(f"All Simulation files: [{len(sim_files)} files]")

    else:
        # ---- S3 ----
        # Parse "s3://bucket/prefix/..."
        _p = sim_path[len("s3://"):]
        bucket_name, _, prefix = _p.partition("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        # Get or create S3 client
        s3_client = get_s3_client()

        # Get storage options
        if storage_options is None:
            storage_options = get_storage_options(endpoint_url=endpoint_url)

        # List all keys under prefix using framework function
        keys = list_objects_under_prefix(s3_client, bucket_name, prefix)

        # Filter matching files
        fname_prefix = (f"{case_name}.{stream_token}.{year_str}" if year
                        else f"{case_name}.{stream_token}.")
        sim_keys = sorted(
            k for k in keys
            if k.startswith(prefix + fname_prefix) and k.endswith(".nc")
        )

        print(f"All Simulation files: [{len(sim_keys)} files]")

        # Turn into S3 URIs
        sim_files = [f"s3://{bucket_name}/{k}" for k in sim_keys]

    if not sim_files:
        year_msg = f"year={year_str}" if year else "any year"
        raise RuntimeError(f"No simulation files found for case={case_name}, {year_msg}")

    # ---------------------------------------------------
    # 2) Read datasets into ds_ctsm
    # ---------------------------------------------------
    start = time.time()

    drop_vars = SOIL_PROFILE_DROP_VARS

    ds_all = []

    if not is_s3:
        # ---- LOCAL ----
        engine = _engine_for_local(sim_files[0])
        for f in tqdm.tqdm(sim_files, desc="Reading files"):
            ds_tmp = xr.open_dataset(f, engine=engine, drop_variables=drop_vars)
            # One sample per file at midday; daily streams carry 48 half-hourly
            # steps, so clamp rather than assume the file is full-length.
            ds_all.append(ds_tmp.isel(time=min(24, ds_tmp.sizes["time"] - 1)))
        ds_ctsm = xr.concat(ds_all, dim="time")

    else:
        # ---- S3: NetCDF-3 with engine="scipy" ----
        for uri in tqdm.tqdm(sim_files, desc="Reading files"):
            with fsspec.open(uri, mode="rb", **storage_options) as fo:
                ds_tmp = xr.open_dataset(
                    fo,
                    engine="scipy",
                    drop_variables=drop_vars
                )
                ds_slice = ds_tmp.isel(time=24).load()
                ds_all.append(ds_slice)

        ds_ctsm = xr.concat(ds_all, dim="time")

    end = time.time()
    print(f"Reading all simulation files [{len(sim_files)} files] took: {end - start:.2f}s")

    # Optional: subset by year if dataset spans multiple years
    if year is not None:
        try:
            ds_ctsm = ds_ctsm.sel(time=str(year))
            print(f"Subsetted to year {year}")
        except (KeyError, ValueError):
            print(f"Warning: Could not subset to year {year}, using all available data")

    # ---------------------------------------------------
    # 3) Plotting
    # ---------------------------------------------------
    if var == "TSOI":
        tsoi = ds_ctsm[var].isel(levgrnd=(slice(0, 9)))
        x = tsoi.time.values
        y = -tsoi.levgrnd.values
        plot_var = tsoi[:, :, 0].values.transpose()
        plot_var = plot_var - 273.15

        cmap = "YlOrRd"
        var_name = "Soil Temperature"
        var_unit = "[°C]"

    elif var == "H2OSOI":
        h2o_soi = ds_ctsm[var].isel(levsoi=(slice(0, 15)))
        x = h2o_soi.time.values
        y = -h2o_soi.levsoi.values
        plot_var = h2o_soi[:, :, 0].values.transpose()

        var_name = "Soil Moisture"
        var_unit = "[mm3/mm3]"

        cmap = plt.get_cmap("gist_earth_r")
        cmap = truncate_colormap(cmap, 0.15, 0.9)

    else:
        raise ValueError("Please choose either 'TSOI' or 'H2OSOI' for plotting.")

    X, Y = np.meshgrid(x, y)
    fig = plt.figure(num=None, figsize=(15, 5), facecolor="w", edgecolor="k")

    ax = plt.gca()
    cs = ax.contourf(X, Y, plot_var, cmap=cmap, extend="both")
    plt.xticks(rotation=30)
    plt.ylabel("Soil Depth [m]")
    plt.xlabel("Time")

    year_label = f" ({year})" if year else ""
    plt.title(f"Time-Series of {var_name} Profile at {neon_site}{year_label}",
              fontweight="bold")

    cbar = fig.colorbar(cs, ax=ax, shrink=0.9)
    cbar.ax.set_ylabel(f"{var_name} {var_unit}")

    time_1 = time.time()
    print(f"Making this plot took {time_1 - time_0:.2f}s")

    return ds_ctsm
