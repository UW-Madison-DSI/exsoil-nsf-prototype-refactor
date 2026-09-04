"""Locating and opening CTSM history output.

This module is the boundary between simulation output in storage and data an
analysis notebook can work with. It answers two questions and deliberately
little else: **where are the history files, and how do I open them?**
Everything above this layer works in xarray Datasets and stays ignorant of
paths, buckets, and file formats.

A CTSM run does not produce one result file. It produces thousands of
*history* files -- NetCDF holding modelled state and fluxes, one per simulated
day for the daily stream and one per month for the monthly stream. (History is
output you analyse; *restart* files exist only so a run can resume.) The KONZ
baseline alone is 5,415 files. Turning those into one continuous time series
means knowing three things that all vary, which is why this is a module and
not a one-line glob:

1. **Stream naming.** CTSM 5.4 renamed the streams: daily h1 -> h1a, monthly
   h0 -> h0a. The S3 fixtures and the reference copies used as a validation
   oracle predate that rename and keep the old names. Both conventions must
   stay readable -- this is not a migration that finishes -- so the token is
   discovered from disk rather than configured. See STREAM_TOKENS.

2. **Archive layout.** Where output lands depends on which wrapper ran the
   simulation: run_tower archives a single case flat, while run_neon_v2.py
   (what the Hubs drive) inserts site and experiment segments so a perturbed
   run and its control stay separate. The reference copies arrived in a third
   shape. See _candidate_hist_dirs.

3. **On-disk format.** Live CTSM 5.4 output is CDF-5, which the scipy engine
   cannot read and h5netcdf cannot either, since CDF-5 is not HDF5. The older
   fixtures are CDF-2, which scipy handles. The engine is chosen per file from
   its magic number. See _engine_for_local.

Layout
------
- S3 plumbing: get_s3_client, test_s3_connection, list_objects_under_prefix,
  get_storage_options, list_keys, download_keys
- Reading history: open_ctsm_hist_from_s3 (remote), find_ctsm_hist_files and
  open_ctsm_hist_local (local)
- Choosing a source: resolve_source, open_ctsm_hist -- the entry point most
  callers want. Local by default so a fresh container works with no
  credentials; S3 is opt-in via CTSM_DATA_SOURCE or an explicit argument.

Plotting lives in the sibling `visualization` module. This module no longer
imports matplotlib itself, but note that importing the *package* still does:
`__init__` loads `neon_eval_utils` and `visualization` eagerly, and both pull
matplotlib. Deferring that is tracked separately. The two plotting names that
used to live here are still importable from this module for compatibility --
see the end of the file.

Environment
-----------
CTSM_DATA_SOURCE   "local" (default) or "s3"
CTSM_OUTPUT_ROOT   root under which local output is searched
COS_ACCESS_KEY_ID / COS_SECRET_ACCESS_KEY
                   read lazily, and only on the S3 path
"""

# ============================================================
# 0. Imports
# ============================================================

import os
import re
import time
from typing import Iterable, List, Optional
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import fsspec
import numpy as np
import xarray as xr
from glob import glob


# ============================================================
# 1. Create S3 client
# ============================================================

def get_s3_client(endpoint_url: str = "https://campus.s3.wisc.edu"):
    """Build a boto3 client for the UW campus S3 endpoint.

    Credentials come from COS_ACCESS_KEY_ID / COS_SECRET_ACCESS_KEY. boto3
    does not validate them here, so a missing credential surfaces as an
    authentication error on first use rather than on construction.

    Path-style addressing is required: the endpoint is not AWS and does not
    serve virtual-host-style bucket URLs.
    """
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("COS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("COS_SECRET_ACCESS_KEY"),
        endpoint_url=endpoint_url,
        config=Config(s3={"addressing_style": "path"}),
    )


# ============================================================
# 2. Test S3 connection (list_objects_v2)
# ============================================================

def test_s3_connection(s3, bucket_name: str, prefix: str) -> bool:
    """Report whether a bucket prefix is reachable, printing the outcome.

    Distinguishes three states a notebook user cares about: reachable with
    data, reachable but empty (usually the wrong prefix rather than a broken
    connection), and refused. Returns True for both reachable cases, so a
    True result does not imply the prefix contains anything.

    Intended for interactive use; it prints rather than raising.
    """
    try:
        resp = s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=1,
        )

        if "Contents" in resp:
            print(f"✅ Connected to {bucket_name}/{prefix}")
        else:
            print(f"⚠️ Connected, but prefix is empty: {bucket_name}/{prefix}")

        return True

    except ClientError as e:
        print("❌ S3 access failed")
        print(e)
        return False


# ============================================================
# 3. List objects under a prefix
# ============================================================

def list_objects_under_prefix(
    s3,
    bucket_name: str,
    prefix: str,
    dry_run: bool = False,
) -> List[str]:
    """List every object key under a prefix, following pagination.

    S3 returns at most 1000 keys per response, and a site-year of history
    easily exceeds that, so this follows continuation tokens until the
    listing is exhausted. Returns sorted keys, which matters because
    downstream readers concatenate files in listing order to build the time
    axis.

    Args:
        dry_run: Stop after the first page. Useful for checking a prefix
            resolves without paging through thousands of keys.
    """
    keys: List[str] = []
    token = None

    while True:
        kwargs = {"Bucket": bucket_name, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token

        resp = s3.list_objects_v2(**kwargs)

        if "Contents" in resp:
            keys.extend(obj["Key"] for obj in resp["Contents"])

        if resp.get("IsTruncated"):
            token = resp["NextContinuationToken"]
        else:
            break

        if dry_run:
            break

    return sorted(keys)


# ============================================================
# 4. Helper: default storage_options for fsspec/s3fs
# ============================================================

def get_storage_options(
    endpoint_url: str = "https://campus.s3.wisc.edu",
) -> dict:
    """Build fsspec/s3fs options for the non-AWS endpoint.

    Separate from get_s3_client because xarray reads through fsspec file
    objects rather than boto3, and the two want credentials in different
    shapes.

    This is the one place that requires COS credentials eagerly, and it is
    only reached on the S3 path -- local reads never call it. That is what
    lets a fresh container work with no credentials configured.

    Raises:
        RuntimeError: if either COS_* variable is unset.
    """
    key = os.getenv("COS_ACCESS_KEY_ID")
    secret = os.getenv("COS_SECRET_ACCESS_KEY")

    if not key or not secret:
        raise RuntimeError(
            "Missing COS credentials in environment. "
            "Set COS_ACCESS_KEY_ID and COS_SECRET_ACCESS_KEY."
        )

    return {
        "key": key,
        "secret": secret,
        "client_kwargs": {"endpoint_url": endpoint_url},
        "config_kwargs": {"s3": {"addressing_style": "path"}},
    }


# ============================================================
# 5. Main function: open CTSM hist files from S3 as xarray
# ============================================================

def open_ctsm_hist_from_s3(
    input_label,
    s3_client,
    bucket_name: str,
    neon_site: str,
    year: str,
    *,
    storage_options: Optional[dict] = None,
    endpoint_url: str = "https://campus.s3.wisc.edu",
    engine: str = "scipy",               # ✅ NetCDF-3 reader (CDF\x01/CDF\x02)
    stream_token: str = "h1",            # S3 fixtures predate the h1a/h0a rename
    decode_times: bool = True,
    combine: str = "by_coords",
    parallel: bool = False,              # ✅ safer for remote file handles
    chunks=None,                         # keep None unless you really want dask
    preview_n: int = 10,
    variables=None,
) -> xr.Dataset:
    """
    List CTSM 'hist' NetCDF files in S3 for a NEON site/year and open as xarray Dataset.

    This is compatible with your existing framework and avoids the h5netcdf error
    when files are NetCDF-3 (magic number b'CDF\\x02').

    Returns:
        ds_ctsm: xarray.Dataset
    """

    if input_label == 'transient':
        sim_path = f"archive_1/{neon_site}.transient/lnd/hist/"
        fname_prefix = f"{neon_site}.transient.clm2.{stream_token}.{year}"

    if input_label == 'evaluation':
        sim_path = f"evaluation_files/{neon_site}/{neon_site}_eval_{year}"
        fname_prefix = f""

    # list keys
    keys = list_objects_under_prefix(s3_client, bucket_name, sim_path)

    # filter keys
    sim_keys = sorted(
        k for k in keys
        if k.startswith(sim_path + fname_prefix) and k.endswith(".nc")
    )

    print(f"All Simulation files: [{len(sim_keys)} files]")

    if preview_n and sim_keys:
        print("First files:")
        for k in sim_keys[:preview_n]:
            print(" ", k)

    if not sim_keys:
        raise RuntimeError(
            f"No NetCDF files found for site={neon_site}, year={year} under s3://{bucket_name}/{sim_path}"
        )

    # build s3 uris
    sim_uris = [f"s3://{bucket_name}/{k}" for k in sim_keys]

    # storage options
    if storage_options is None:
        storage_options = get_storage_options(endpoint_url=endpoint_url)

    # open remote handles
    ofiles = fsspec.open_files(sim_uris, mode="rb", **storage_options)
    fileobjs = [f.open() for f in ofiles]

    # Same selection as the local reader, so open_ctsm_hist(variables=...)
    # means one thing regardless of which source resolves.
    variables = _as_variable_list(variables)
    preprocess = _select_variables(variables) if variables is not None else None

    start = time.time()
    try:
        ds_ctsm = xr.open_mfdataset(
            fileobjs,
            engine=engine,
            preprocess=preprocess,
            decode_times=decode_times,
            combine=combine,
            parallel=parallel,
            chunks=chunks,
        )
    finally:
        # Always close remote handles
        for fo in fileobjs:
            try:
                fo.close()
            except Exception:
                pass

    print(f"Reading all simulation files took: {time.time() - start:.2f} seconds.")
    if variables is not None:
        _check_requested_variables(ds_ctsm, variables)
    return ds_ctsm


# ============================================================
# 5b. Local (in-container / native) CTSM history access
# ============================================================

# Kept regardless of a `variables` selection: dropping the time axis to a
# variable filter is never what the caller meant.
TIME_BOOKKEEPING = frozenset({"time", "time_bounds", "mcdate", "mcsec"})

# CTSM stamps a monthly file at the start of the *next* month: h0a.2018-07.nc
# holds July but reports mcdate 20180801. The filename is the only place the
# month the data belongs to is recorded, so it is read from there.
MONTH_STAMP = re.compile(r"\.h0a?\.(\d{4}-\d{2})\.nc$")

# CTSM 5.4 writes suffixed stream names: h0a monthly, h1a daily. Older output
# -- including the S3 fixtures and the reference copies used as a validation
# oracle -- uses unsuffixed h0/h1. Both have to stay readable, so the token is
# discovered from what is actually on disk rather than assumed. Newest naming
# is tried first so a directory holding both resolves to the current run.
STREAM_TOKENS = {
    "daily": ("h1a", "h1"),
    "monthly": ("h0a", "h0"),
}

# Where in-container output lands by default. Override per-environment with
# CTSM_OUTPUT_ROOT; on a dev host this is typically a baseline archive dir.
DEFAULT_OUTPUT_ROOT = "/home/user"


def get_output_root() -> Path:
    """Root under which local CTSM output is searched.

    Reads CTSM_OUTPUT_ROOT, falling back to DEFAULT_OUTPUT_ROOT. The default
    is correct inside the container and wrong on a development host, where it
    should point at a completed run's directory -- set the variable there.
    User home shorthand (~) is expanded.
    """
    return Path(os.path.expanduser(os.getenv("CTSM_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT)))


def _candidate_hist_dirs(root: Path, neon_site: str, input_label: str) -> List[Path]:
    """Directories that have all held CTSM history output at some point.

    The project accumulated several archive layouts and none is going away:
    run_tower archives a single case flat, run_neon_v2 inserts site and
    experiment segments so perturbed and control runs stay separate, and the
    reference copies arrived in the S3 per-site shape. Probing is cheaper than
    making every caller know which tool produced the data it is reading.
    """
    case = f"{neon_site}.{input_label}"
    fixed = [
        root / "lnd" / "hist",                                  # root is already an archive
        root / "archive" / "lnd" / "hist",                      # run_tower
        root / "archive" / case / "lnd" / "hist",               # S3 shape, staged locally
        root / case / "lnd" / "hist",
        root / "reference-output" / case / "lnd" / "hist",      # validation oracle
    ]
    # run_neon_v2 writes archive/<site>/<control|VAR_VALUE>/lnd/hist
    globbed = sorted(root.glob(f"archive/{neon_site}/*/lnd/hist"))
    return fixed + globbed


def find_ctsm_hist_files(
    neon_site: str,
    year=None,
    *,
    output_root=None,
    stream: str = "daily",
    input_label: str = "transient",
) -> List[str]:
    """Locate local CTSM history files for a site, returning sorted paths.

    Handles both stream naming conventions and every archive layout in use.
    Returns paths rather than a Dataset because the evaluation and comparison
    helpers in neon_eval_utils consume file lists.

    Args:
        neon_site: NEON site code, e.g. "KONZ".
        year: Restrict to one year. None means every year present.
        output_root: Search root. Defaults to CTSM_OUTPUT_ROOT.
        stream: "daily" (h1a/h1) or "monthly" (h0a/h0).
        input_label: Case label, normally "transient".

    Raises:
        FileNotFoundError: with the directories and patterns tried, since a
            silent empty list is the failure mode that wastes the most time.
    """
    if stream not in STREAM_TOKENS:
        raise ValueError(f"stream must be one of {sorted(STREAM_TOKENS)}, got {stream!r}")

    root = Path(output_root).expanduser() if output_root else get_output_root()
    year_glob = f"{year}*" if year is not None else "*"
    case_name = f"{neon_site}.{input_label}.clm2"

    tried = []
    for hist_dir in _candidate_hist_dirs(root, neon_site, input_label):
        for token in STREAM_TOKENS[stream]:
            pattern = f"{case_name}.{token}.{year_glob}.nc"
            tried.append(str(hist_dir / pattern))
            matches = sorted(glob(str(hist_dir / pattern)))
            if matches:
                return matches

    raise FileNotFoundError(
        f"No CTSM {stream} history files for site={neon_site}, "
        f"year={year if year is not None else 'any'} under {root}.\n"
        "Tried:\n  " + "\n  ".join(tried)
    )


def _as_variable_list(variables):
    """Normalise a `variables` argument.

    A bare string is the most likely mistake -- `variables="GPP"` -- and
    `set("GPP")` is {"G", "P"}, which would select nothing and raise nothing.
    """
    if variables is None:
        return None
    if isinstance(variables, str):
        return [variables]
    return list(variables)


def _select_variables(variables):
    """Build an open_mfdataset preprocess that keeps `variables` plus time bookkeeping."""
    keep = set(variables) | TIME_BOOKKEEPING

    def _select(dataset):
        return dataset[[name for name in dataset.data_vars if name in keep]]

    return _select


def _check_requested_variables(dataset, variables) -> None:
    """Raise if any requested variable matched nothing.

    A filter that matches nothing returns a dataset with a correct time axis
    and no data, which downstream reads as "no data for that period" rather
    than as a typo. That is the silent-empty failure this module exists to
    prevent, so it is an error.
    """
    missing = sorted(set(variables) - set(dataset.variables))
    if missing:
        raise KeyError(
            f"Requested variables not present in the history files: {missing}. "
            "Check the spelling, and whether the variable is on this stream -- "
            "several water-flux variables are monthly-only (see docs/data-contract.md)."
        )


def _label_months(dataset):
    """Attach a `month` coordinate ('YYYY-MM') read from the file the data came from.

    Only the monthly filenames carry the stamp; anything else passes through
    unchanged. Attached as a coordinate so it travels with the values through
    combine="by_coords", instead of being zipped on afterwards from a
    separately ordered file list.
    """
    match = MONTH_STAMP.search(str(dataset.encoding.get("source", "")))
    if match is None or "time" not in dataset.sizes:
        return dataset
    labels = np.array([match.group(1)] * dataset.sizes["time"])
    return dataset.assign_coords(month=("time", labels))


def _engine_for_local(path: str) -> str:
    """Pick an xarray engine from the file's magic number.

    CTSM 5.4 writes CDF-5 (b'CDF\\x05', 64-bit offsets), which scipy cannot
    read -- and h5netcdf cannot either, since CDF-5 is not HDF5. The older
    fixtures are CDF-2, which scipy handles. netcdf4 reads all of them, so it
    is the safe default; scipy is kept for CDF-1/2 because it avoids the
    heavier dependency when the lighter one is sufficient.
    """
    with open(path, "rb") as handle:
        magic = handle.read(4)
    return "scipy" if magic in (b"CDF\x01", b"CDF\x02") else "netcdf4"


def open_ctsm_hist_local(
    neon_site: str,
    year=None,
    *,
    output_root=None,
    stream: str = "daily",
    input_label: str = "transient",
    variables=None,
    drop_variables=None,
    decode_times: bool = True,
    combine: str = "by_coords",
    parallel: bool = False,
    chunks=None,
) -> xr.Dataset:
    """Open local CTSM history output as a single xarray Dataset.

    Locates files with find_ctsm_hist_files, so it inherits the stream and
    layout discovery described in the module docstring, then concatenates
    them along time. The reader engine is chosen from the first file's magic
    number rather than assumed.

    Args:
        neon_site: NEON site code, e.g. "KONZ".
        year: Restrict to one year. None reads every year present.
        output_root: Search root. Defaults to CTSM_OUTPUT_ROOT.
        stream: "daily" (h1a/h1) or "monthly" (h0a/h0).
        input_label: Case label, normally "transient".
        variables: Keep only these, discarding the rest as each file opens.
            Worth using on the monthly stream, which carries 623 variables per
            file: selecting three takes ~10 s where reading everything takes
            ~117 s. Time bookkeeping (time, time_bounds, mcdate, mcsec) is
            always retained, since losing the time axis to a variable
            selection is never what the caller meant. A single name may be
            passed as a string. A name that matches nothing raises KeyError
            rather than returning a dataset with no data.
        drop_variables: Passed to xarray. Useful for skipping the large
            static soil-property fields repeated in every file.

    Returns:
        xr.Dataset spanning all matched files. On the monthly stream it carries
        a `month` coordinate ('YYYY-MM') along time, read from each filename,
        because `mcdate` on those files is stamped at the start of the *next*
        month and would shift a month index forward by one.

    Raises:
        FileNotFoundError: if nothing matches, listing the paths tried.
        KeyError: if a requested variable is absent from the files.
    """
    sim_files = find_ctsm_hist_files(
        neon_site, year, output_root=output_root, stream=stream, input_label=input_label
    )
    print(f"All Simulation files: [{len(sim_files)} files]")

    variables = _as_variable_list(variables)
    steps = []
    if variables is not None:
        steps.append(_select_variables(variables))
    if stream == "monthly":
        steps.append(_label_months)

    def preprocess(dataset):
        for step in steps:
            dataset = step(dataset)
        return dataset

    start = time.time()
    # This emits a FutureWarning about the `data_vars` default. Do not silence
    # it by pinning the concat kwargs: `data_vars="minimal"` alone is safe, but
    # adding `compat="override"` and `coords="minimal"` -- which xarray then
    # demands in turn -- reads without error and leaves 82 of 83 months as NaN.
    # Correct shape, correct time axis, no exception, no data. See issue #28.
    ds_ctsm = xr.open_mfdataset(
        sim_files,
        engine=_engine_for_local(sim_files[0]),
        preprocess=preprocess,
        drop_variables=drop_variables,
        decode_times=decode_times,
        combine=combine,
        parallel=parallel,
        chunks=chunks,
    )
    print(f"Reading all simulation files took: {time.time() - start:.2f} seconds.")
    if variables is not None:
        _check_requested_variables(ds_ctsm, variables)
    return ds_ctsm


def resolve_source(source=None) -> str:
    """Decide whether to read locally or from S3.

    Precedence: explicit argument, then CTSM_DATA_SOURCE, then "local".
    Local is the default so a freshly pulled container works without
    credentials or configuration; reaching the shared S3 fixtures is a
    deliberate opt-in.

    Returns:
        Either "local" or "s3".

    Raises:
        ValueError: on any other value, rather than silently falling back --
            a typo'd source should not quietly read the wrong data.
    """
    resolved = (source or os.getenv("CTSM_DATA_SOURCE") or "local").lower()
    if resolved not in {"local", "s3"}:
        raise ValueError(f"source must be 'local' or 's3', got {resolved!r}")
    return resolved


def open_ctsm_hist(
    neon_site: str,
    year=None,
    *,
    source=None,
    output_root=None,
    stream: str = "daily",
    input_label: str = "transient",
    bucket_name: str = "clm-demonstration",
    **kwargs,
) -> xr.Dataset:
    """Open CTSM history output regardless of where it lives.

    Local by default so a fresh container works with no credentials; pass
    source="s3" (or set CTSM_DATA_SOURCE=s3) for the original fixtures. S3
    credentials are only required on the S3 path.
    """
    if stream not in STREAM_TOKENS:
        raise ValueError(f"stream must be one of {sorted(STREAM_TOKENS)}, got {stream!r}")

    if resolve_source(source) == "s3":
        # The S3 copies predate the CTSM 5.4 rename, so the public stream name
        # maps to the legacy token -- otherwise stream="monthly" would silently
        # read daily files. An explicit stream_token still wins.
        kwargs.setdefault("stream_token", STREAM_TOKENS[stream][-1])
        # The S3 reader interpolates year straight into the key prefix, so
        # year=None has to become an empty string (match every year) rather
        # than the string "None", which matches nothing.
        return open_ctsm_hist_from_s3(
            input_label, get_s3_client(), bucket_name, neon_site,
            "" if year is None else str(year), **kwargs
        )
    return open_ctsm_hist_local(
        neon_site, year, output_root=output_root, stream=stream,
        input_label=input_label, **kwargs
    )


# ============================================================
# 7. Bulk download from S3
# ============================================================

def list_keys(bucket: str, prefix: str, s3, suffix: str) -> list[str]:
    """List object keys under a prefix, skipping directory placeholders.

    Overlaps with list_objects_under_prefix; this one filters by suffix and
    drops the zero-byte "directory" keys some tools create, which is what the
    bulk-download helpers want. Prefer list_objects_under_prefix when reading
    history files.

    Args:
        suffix: Keep only keys ending with this, e.g. ".nc" or ".log".
            Falsy values keep everything.
    """
    paginator = s3.get_paginator("list_objects_v2")
    out = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if suffix and not key.endswith(suffix):
                continue
            out.append(key)
    return out


def download_keys(bucket: str, keys: Iterable[str], local_root: str, s3, strip_prefix: str):
    """
    Download the given S3 keys into local_root.

    If strip_prefix is set to e.g. 'CLM-NEON/', then a key like:
      CLM-NEON/ABBY.transient/run/cesm.log
    is saved as:
      /root/CLM-NEON/ABBY.transient/run/cesm.log
    """
    local_root = Path(local_root)
    local_root.mkdir(parents=True, exist_ok=True)

    n = 0
    for key in keys:
        rel = key
        if strip_prefix and rel.startswith(strip_prefix):
            rel = rel[len(strip_prefix):]
        dest = local_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(dest))
        n += 1
    print(f"Downloaded {n} files into {local_root}")


# ============================================================
# 8. Backwards compatibility
# ============================================================

# plot_soil_profile_timeseries and truncate_colormap lived in this module
# until they moved to visualization.py. Both were documented and public, so
# the old import path keeps working rather than breaking callers:
#
#     from analytics_modules.data_access import plot_soil_profile_timeseries
#
# Resolved on attribute access (PEP 562) rather than by importing
# visualization at module load, so this module still does not pull matplotlib
# in on its own.
_MOVED_TO_VISUALIZATION = frozenset(
    {"plot_soil_profile_timeseries", "truncate_colormap"}
)


def __getattr__(name: str):
    if name in _MOVED_TO_VISUALIZATION:
        from . import visualization
        return getattr(visualization, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
