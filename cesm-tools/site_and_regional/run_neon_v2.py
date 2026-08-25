#! /usr/bin/env python3
"""
run_neon_v2.py
==============
Extended CTSM NEON site wrapper with:
  1. Forcing transformation layer  (scaling / add / seasonal_scaling / noise)
  2. S3 forcing download           (non-AWS S3 via boto3 + fsspec)
  3. Soil-profile visualisation    (TSOI / H2OSOI contour plots)

Features
--------
- Creates counterfactual forcing scenarios by programmatically modifying
  meteorological inputs before simulation (variable-level scaling, seasonal
  perturbations, noise injection).
- S3 cloud storage pipeline: auto-pull forcing data from a remote object store,
  cache locally, and feed into the simulation.
- Both features work together or independently, controlled via CLI flags.

Typical usage
-------------
# Local forcing, scale precip by +10%:
python run_neon_v2.py --neon-sites ABBY --output-root ~/CLM-NEON-v2 \
    --transform-var PRECTmms --transform-method scaling --transform-value 1.1

# Pull from S3, no transform:
python run_neon_v2.py --neon-sites ABBY --output-root ~/CLM-NEON-v2 \
    --s3-input-bucket clm-demonstration --s3-input-prefix neon-forcing/

# Pull from S3 + apply seasonal scaling:
python run_neon_v2.py --neon-sites ABBY --output-root ~/CLM-NEON-v2 \
    --s3-input-bucket clm-demonstration \
    --s3-input-prefix neon-forcing/ \
    --s3-endpoint-url https://campus.s3.wisc.edu \
    --transform-var PRECTmms --transform-method seasonal_scaling \
    --seasonal-factors 0.9,0.9,1,1,1,1.2,1.2,1.2,1,1,1,0.9 \
    --transform-tag prec_seasonal

Credentials
-----------
Set these environment variables before running:
    export COS_ACCESS_KEY_ID=<your-key>
    export COS_SECRET_ACCESS_KEY=<your-secret>

For full option list:
    ./run_neon_v2.py --help
"""

# ---------------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------------
import os
import re
import sys
import glob
import time
import shutil
import logging
import argparse
import datetime
from getpass import getuser
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Third-party – numeric / IO
# ---------------------------------------------------------------------------
import numpy as np
import pandas as pd
import xarray as xr
import requests

# ---------------------------------------------------------------------------
# AWS / S3
# ---------------------------------------------------------------------------
# Shared with the analysis notebooks rather than duplicated here. Both this
# script and the package are on PYTHONPATH in the container
# (Dockerfile:149,152), so there is one implementation, not two.
from analytics_modules.data_access import (
    get_s3_client,
    list_objects_under_prefix,
)

# ---------------------------------------------------------------------------
# CTSM / CIME internals
# ---------------------------------------------------------------------------
_CTSM_PYTHON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "python")
)
sys.path.insert(1, _CTSM_PYTHON)

from ctsm import add_cime_to_path
from ctsm.path_utils import path_to_ctsm_root
try:
    from ctsm.download_utils import download_file
except ImportError:
    import urllib.request
    def download_file(url, dest):
        urllib.request.urlretrieve(url, dest)

import CIME.build as build
from standard_script_setup import *
from CIME.case import Case
from CIME.utils import safe_copy, expect, symlink_force, run_cmd_no_fail
from argparse import RawTextHelpFormatter
from CIME.locked_files import lock_file, unlock_file

logger = logging.getLogger(__name__)


# ===========================================================================
# SECTION 1 – S3 helpers
# ===========================================================================

def download_s3_forcing(
    bucket_name: str,
    prefix: str,
    site_code: str,
    local_dest: str,
    endpoint_url: str = "https://campus.s3.wisc.edu",
) -> str:
    """
    Mirror-download NEON met NetCDF forcing files from S3 to a local directory.

    Only files matching the pattern  atm/cdeps/*/<site_code>/*.nc  are
    downloaded.  Files that already exist locally and whose byte size matches
    the remote object are skipped.

    Returns the absolute path of local_dest (for convenience).
    """
    s3 = get_s3_client(endpoint_url=endpoint_url)
    dest = Path(local_dest)
    dest.mkdir(parents=True, exist_ok=True)

    keys = list_objects_under_prefix(s3, bucket_name, prefix)
    site_keys = [
        k for k in keys
        if f"/{site_code}/" in k and "atm/cdeps" in k and k.endswith(".nc")
    ]

    if not site_keys:
        raise RuntimeError(
            f"No forcing files found for site={site_code} "
            f"under s3://{bucket_name}/{prefix}"
        )

    print(f"[{site_code}] Downloading {len(site_keys)} forcing file(s) from S3...")
    for key in site_keys:
        rel = key[len(prefix):].lstrip("/")
        local_path = dest / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if local_path.exists():
            remote_size = s3.head_object(Bucket=bucket_name, Key=key)["ContentLength"]
            if local_path.stat().st_size == remote_size:
                logger.debug(f"  skip (exists): {rel}")
                continue

        print(f"  ↓  {rel}")
        s3.download_file(bucket_name, key, str(local_path))

    print(f"[{site_code}] S3 download complete → {local_dest}")
    return str(dest)


# ===========================================================================
# SECTION 3 – Forcing transformation layer
# ===========================================================================

def _apply_da_transform(
    da: xr.DataArray,
    method: str,
    *,
    factor: float = 1.0,
    value: float = 0.0,
    month_factors=None,
    noise_mode: str = "add",
    noise_sigma: float = 0.0,
    noise_seed: Optional[int] = None,
) -> xr.DataArray:
    """
    Apply one of four in-memory transforms to a DataArray.

    Methods
    -------
    'scaling'          → da * factor
    'add'              → da + value
    'seasonal_scaling' → da * monthly_factor  (12 factors, Jan–Dec)
    'noise'            → da ± Gaussian(0, noise_sigma)
    """
    if method == "scaling":
        return da * factor

    if method == "add":
        return da + value

    if method == "seasonal_scaling":
        if month_factors is None or len(month_factors) != 12:
            raise ValueError(
                "seasonal_scaling requires exactly 12 month_factors (Jan–Dec)."
            )
        mf = xr.DataArray(
            month_factors, dims=["month"], coords={"month": np.arange(1, 13)}
        )
        return da.groupby("time.month") * mf

    if method == "noise":
        rng = np.random.default_rng(noise_seed)
        eps = xr.DataArray(
            rng.normal(0.0, noise_sigma, size=da.shape),
            coords=da.coords,
            dims=da.dims,
        )
        return da + eps if noise_mode == "add" else da * (1.0 + eps)

    raise ValueError(f"Unknown transform method: {method!r}")


def transform_neon_input_dir(
    input_root: str,
    output_root: str,
    site_code: str,
    var_name: str,
    method: str,
    *,
    factor: float = 1.0,
    value: float = 0.0,
    seasonal_factors: Optional[str] = None,
    noise_mode: str = "add",
    noise_sigma: float = 0.0,
    noise_seed: Optional[int] = None,
):
    """
    Mirror-copy NEON met NetCDF files from input_root → output_root,
    applying a transform to var_name in every matching file.

    FIX (Bug 3): raises RuntimeError immediately if no files are matched
    instead of silently doing nothing.
    """
    in_root = Path(input_root)
    out_root = Path(output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # ---- validate input_root exists ----------------------------------------
    if not in_root.exists():
        raise RuntimeError(
            f"transform_neon_input_dir: input_root does not exist: {in_root}\n"
            f"Check that DIN_LOC_ROOT is correctly set before calling the transform."
        )

    month_factors = None
    if seasonal_factors:
        month_factors = [float(x.strip()) for x in seasonal_factors.split(",")]
        if len(month_factors) != 12:
            raise ValueError(
                "--seasonal-factors must contain exactly 12 comma-separated numbers."
            )

    # ---- FIX (Bug 3): count matched files ----------------------------------
    matched = 0
    for src in in_root.rglob("atm/cdeps/*/*/*.nc"):
        if f"/{site_code}/" not in str(src):
            continue

        matched += 1
        rel = src.relative_to(in_root)
        dst = out_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        ds = xr.open_dataset(src, chunks="auto")
        try:
            if var_name in ds:
                da_new = _apply_da_transform(
                    ds[var_name], method,
                    factor=factor, value=value,
                    month_factors=month_factors,
                    noise_mode=noise_mode,
                    noise_sigma=noise_sigma,
                    noise_seed=noise_seed,
                )
                ds[var_name] = da_new
                encoding = {k: {"zlib": True, "complevel": 1} for k in ds.data_vars}
                ds.to_netcdf(dst, encoding=encoding)
                logger.debug(f"  transformed: {rel}")
            else:
                # Variable not in this file – pass through unchanged
                ds.to_netcdf(dst)
                logger.debug(f"  copied (var not present): {rel}")
        finally:
            ds.close()

    # ---- FIX (Bug 3): loud failure instead of silent no-op -----------------
    if matched == 0:
        raise RuntimeError(
            f"transform_neon_input_dir: no forcing files found for site={site_code} "
            f"under {in_root}.\n"
            f"Expected files matching: atm/cdeps/*/{site_code}/*.nc\n"
            f"Check that DIN_LOC_ROOT points at the correct inputdata root."
        )

    print(f"[{site_code}] Transform complete: {matched} file(s) → {out_root}")


# ===========================================================================
# SECTION 4 – CLI argument parser
# ===========================================================================

def get_parser(args, description, valid_neon_sites):
    """Build and parse command-line arguments for the NEON runner."""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    CIME.utils.setup_standard_logging_options(parser)
    parser.print_usage = parser.print_help

    parser.add_argument(
        "--neon-sites",
        help="4-letter NEON site code(s), or 'all'.",
        action="store", required=False,
        choices=valid_neon_sites + ["all"],
        dest="neon_sites", default=["OSBS"], nargs="+",
    )
    parser.add_argument(
        "--base-case",
        help="Root directory of base case build. [default: auto]",
        action="store", dest="base_case_root", type=str,
        required=False, default=None,
    )
    parser.add_argument(
        "--output-root",
        help="Root output directory of cases. [default: CIME_OUTPUT_ROOT]",
        action="store", dest="output_root", type=str,
        required=False, default="CIME_OUTPUT_ROOT as defined in cime",
    )
    parser.add_argument(
        "--overwrite",
        help="Overwrite existing case directories. [default: False]",
        action="store_true", dest="overwrite", required=False, default=False,
    )
    parser.add_argument(
        "--setup-only",
        help="Only set up cases; do not build or run. [default: False]",
        action="store_true", dest="setup_only", required=False, default=False,
    )
    parser.add_argument(
        "--rerun",
        help="Restart an existing incomplete case. [default: False]",
        action="store_true", dest="rerun", required=False, default=False,
    )
    parser.add_argument(
        "--no-batch",
        help="Run locally without a batch queue. [default: False]",
        action="store_true", dest="no_batch", required=False, default=False,
    )
    parser.add_argument(
        "--run-type",
        help="Simulation phase: ad | postad | transient | sasu. [default: transient]",
        choices=["ad", "postad", "transient", "sasu"], default="transient",
    )
    parser.add_argument(
        "--run-length",
        help="Run duration as modified ISO 8601 (e.g. '4Y'). [default: 0Y → auto]",
        required=False, type=str, default="0Y",
    )
    parser.add_argument(
        "--start-date",
        help="Simulation start date ISO format. [default: 2018-01-01]",
        action="store", dest="start_date", required=False,
        type=datetime.date.fromisoformat,
        default=datetime.datetime.strptime("2018-01-01", "%Y-%m-%d"),
    )
    parser.add_argument(
        "--end-date",
        help="Simulation end date ISO format. [default: 2021-01-01]",
        action="store", dest="end_date", required=False,
        type=datetime.date.fromisoformat,
        default=datetime.datetime.strptime("2021-01-01", "%Y-%m-%d"),
    )
    parser.add_argument(
        "--run-from-postad",
        help="Transient only: start from postad spinup instead of finidat.",
        action="store_true", required=False, default=False,
    )
    parser.add_argument(
        "--neon-version",
        help="NEON data version (v1 or v2). [default: latest]",
        action="store", dest="user_version", required=False,
        type=str, choices=["v1", "v2"],
    )

    # ---- transform flags ---------------------------------------------------
    parser.add_argument(
        "--transform-var",
        help="NetCDF variable to transform (e.g. PRECTmms). "
             "Omit to skip the transform step.",
        type=str, default=None,
    )
    parser.add_argument(
        "--transform-method",
        help="Transform type: scaling | add | seasonal_scaling | noise.",
        type=str,
        choices=["scaling", "add", "seasonal_scaling", "noise"],
        default="scaling",
    )
    parser.add_argument(
        "--transform-value",
        help="Numeric parameter: factor for scaling (e.g. 1.1) or addend for add.",
        type=float, default=1.0,
    )
    parser.add_argument(
        "--seasonal-factors",
        help="12 comma-separated monthly scale factors for seasonal_scaling (Jan–Dec).",
        type=str, default=None,
    )
    parser.add_argument(
        "--noise-mode",
        help="Noise application mode if method=noise: add | mul.",
        type=str, choices=["add", "mul"], default="add",
    )
    parser.add_argument(
        "--noise-sigma",
        help="Gaussian noise std-dev if method=noise (e.g. 0.05).",
        type=float, default=0.0,
    )
    parser.add_argument(
        "--noise-seed",
        help="Random seed for reproducible noise.",
        type=int, default=42,
    )
    parser.add_argument(
        "--transform-tag",
        help="Sub-directory tag for transformed inputdata under RUNDIR. "
             "[default: inputdata_v2]",
        type=str, default="inputdata_v2",
    )

    # ---- S3 flags ----------------------------------------------------------
    parser.add_argument(
        "--s3-input-bucket",
        help="S3 bucket to pull NEON forcing data from. Omit to use local inputdata.",
        type=str, default=None, dest="s3_input_bucket",
    )
    parser.add_argument(
        "--s3-input-prefix",
        help="Key prefix within the S3 bucket for forcing data. [default: '']",
        type=str, default="", dest="s3_input_prefix",
    )
    parser.add_argument(
        "--s3-endpoint-url",
        help="S3 endpoint URL for non-AWS services. "
             "[default: https://campus.s3.wisc.edu]",
        type=str, default="https://campus.s3.wisc.edu",
        dest="s3_endpoint_url",
    )

    args = CIME.utils.parse_args_and_handle_standard_logging_options(args, parser)

    neon_sites = valid_neon_sites if "all" in args.neon_sites else args.neon_sites
    for site in neon_sites:
        if site not in valid_neon_sites:
            raise ValueError(f"Invalid site name: {site}")

    if "CIME_OUTPUT_ROOT" in args.output_root:
        args.output_root = "/home/user"
        #args.output_root = None

    if args.run_length == "0Y":
        run_length = "100Y" if args.run_type in ("ad", "postad") else "4Y"
    else:
        run_length = args.run_length
    run_length = parse_isoduration(run_length)

    base_case_root = os.path.abspath(args.base_case_root) if args.base_case_root else None

    if not args.debug and not args.verbose:
        logging.getLogger().setLevel(logging.WARN)

    return (
        neon_sites,
        args.output_root,
        args.run_type,
        args.overwrite,
        run_length,
        base_case_root,
        args.run_from_postad,
        args.setup_only,
        args.no_batch,
        args.rerun,
        args.user_version,
        # transform
        args.transform_var,
        args.transform_method,
        args.transform_value,
        args.seasonal_factors,
        args.noise_mode,
        args.noise_sigma,
        args.noise_seed,
        args.transform_tag,
        # S3
        args.s3_input_bucket,
        args.s3_input_prefix,
        args.s3_endpoint_url,
    )


# ===========================================================================
# SECTION 5 – ISO duration helper
# ===========================================================================

def get_isosplit(s, split):
    if split in s:
        n, s = s.split(split)
    else:
        n = 0
    return n, s


def parse_isoduration(s: str) -> int:
    """
    Minimal ISO 8601 duration parser → integer number of days.
    Assumes 365-day years and 30-day months; no leap years.
    """
    s = s.split("P")[-1]
    years, s = get_isosplit(s, "Y")
    months, s = get_isosplit(s, "M")
    days, s = get_isosplit(s, "D")
    dt = datetime.timedelta(
        days=int(days) + 365 * int(years) + 30 * int(months)
    )
    return int(dt.total_seconds() / 86400)


# ===========================================================================
# SECTION 6 – NeonSite class
# ===========================================================================

class NeonSite:
    """
    Encapsulates a single NEON tower site and orchestrates CTSM case setup,
    build, and submission for that site.
    """

    def __init__(self, name, start_year, end_year, start_month, end_month, finidat):
        self.name = name
        self.start_year = int(start_year)
        self.end_year = int(end_year)
        self.start_month = int(start_month)
        self.end_month = int(end_month)
        self.cesmroot = path_to_ctsm_root()
        self.finidat = finidat

    def __str__(self):
        return (
            str(self.__class__) + "\n"
            + "\n".join(f"{k} = {v}" for k, v in self.__dict__.items())
        )

    # ------------------------------------------------------------------
    def build_base_case(
        self, cesmroot, output_root, res, compset, overwrite=False, setup_only=False
    ):
        """Create (or reuse) and build the generic base CTSM case."""
        print("---- building base case ----")
        self.base_case_root = output_root
        user_mods_dirs = [
            os.path.join(cesmroot, "cime_config", "usermods_dirs", "clm", "NEON", self.name)
        ]
        if not output_root:
            output_root = os.getcwd()
        case_path = os.path.join(output_root, self.name)

        if overwrite and os.path.isdir(case_path):
            print(f"Removing existing case: {case_path}")
            shutil.rmtree(case_path)

        with Case(case_path, read_only=False) as case:
            if not os.path.isdir(case_path):
                case.create(
                    case_path, cesmroot, compset, res,
                    run_unsupported=True, answer="r",
                    output_root=output_root,
                    user_mods_dirs=user_mods_dirs,
                    driver="nuopc",
                )
                # CTSM 5.4 NEON runs use SSP3-7.0 forcing dates (2018+)
                # but IHist compsets default CLM_CMIP_ERA to cmip7.
                # CMIP7 SSP data doesn't exist yet; force cmip6. (ADR-0006)
                case.set_value("CLM_CMIP_ERA", "cmip6")
                case.case_setup()
            else:
                existingcompname = case.get_value("COMPSET")
                match = re.search("^HIST", existingcompname, flags=re.IGNORECASE)
                if re.search("^HIST", compset, flags=re.IGNORECASE) is None:
                    expect(match is None,
                           "Existing base case is historical – rerun with --overwrite")
                else:
                    expect(match is not None,
                           "Existing base case should be historical – rerun with --overwrite")
                case.case_setup(reset=True)

            case_path = case.get_value("CASEROOT")
            if setup_only:
                return case_path

            t0 = time.time()
            build.case_build(case_path, case=case)
            print(f"Base case built in {time.time() - t0:.1f}s")

        return case_path

    # ------------------------------------------------------------------
    def diff_month(self):
        d1 = datetime.datetime(self.end_year, self.end_month, 1)
        d2 = datetime.datetime(self.start_year, self.start_month, 1)
        return (d1.year - d2.year) * 12 + d1.month - d2.month

    # ------------------------------------------------------------------
    def run_case(
        self,
        base_case_root,
        run_type,
        run_length,
        user_version,
        overwrite=False,
        setup_only=False,
        no_batch=False,
        rerun=False,
        # ---- transform ----
        transform_var=None,
        transform_method="scaling",
        transform_value=1.0,
        seasonal_factors=None,
        noise_mode="add",
        noise_sigma=0.0,
        noise_seed=42,
        transform_tag="inputdata_v2",
        # ---- S3 ----
        s3_input_bucket=None,
        s3_input_prefix="",
        s3_endpoint_url="https://campus.s3.wisc.edu",
    ):
        """
        Clone the base case for this site, configure it, optionally download
        S3 forcing and/or apply a forcing transform, then submit.

        Transform ordering
        ------------------
        The correct pipeline is:

            case.case_setup()
                ↓
            [STEP A] download forcing from S3  (optional)
                ↓
            [STEP B] transform the forcing variable  (optional)
                ↓
            case.create_namelists()   ← runs once, after DIN_LOC_ROOT is final
            case.check_all_input_data()
                ↓
            case.submit()

        This guarantees that create_namelists() and check_all_input_data()
        always see the final (possibly transformed) DIN_LOC_ROOT, not the
        original staging path.
        """
        user_mods_dirs = [
            os.path.join(
                self.cesmroot, "cime_config", "usermods_dirs", "clm", "NEON", self.name
            )
        ]
        expect(
            os.path.isdir(base_case_root),
            f"Base case not found: {base_case_root}",
        )

        version = user_version if user_version else "latest"
        print(f"NEON data version: {version}")

        case_root = os.path.abspath(
            os.path.join(base_case_root, self.name + "." + run_type)
        )
        rundir = None

        # ---- handle existing case ----------------------------------------
        if os.path.isdir(case_root):
            if overwrite:
                print("---- removing existing case ----")
                shutil.rmtree(case_root)
            elif rerun:
                with Case(case_root, read_only=False) as case:
                    archroot = os.path.join(os.path.dirname(base_case_root), "archive")
                    exp_name = f"{transform_var}_{transform_value}" if transform_var else "control"
                    archroot_exp = os.path.join(archroot, self.name, exp_name)
                    case.set_value("DOUT_S_ROOT", archroot_exp)

                    rundir = case.get_value("RUNDIR")
                    if os.path.isfile(os.path.join(rundir, "ESMF_Profile.summary")):
                        print(f"Case appears complete, skipping: {case_root}")
                    elif not setup_only:
                        print(f"Resubmitting: {case_root}")
                        print(f"[{self.name}] Archive root → {archroot_exp}")
                        case.submit(no_batch=no_batch)
                return
            else:
                logger.warning(f"Case exists, not overwriting: {case_root}")
                return

        if run_type == "postad":
            adcase_root = case_root.replace(".postad", ".ad")
            if not os.path.isdir(adcase_root):
                logger.warning(f"postad requested but no ad case found: {adcase_root}")
                return

        # ---- clone base case --------------------------------------------
        if not os.path.isdir(case_root):
            with Case(base_case_root, read_only=False) as basecase:
                print(f"---- cloning base case → {case_root}")
                basecase.create_clone(
                    case_root, keepexe=True, user_mods_dirs=user_mods_dirs
                )

        with Case(case_root, read_only=False) as case:
            # ---- run-type specific settings ------------------------------
            if run_type != "transient":
                case.set_value("STOP_OPTION", "ndays")
                case.set_value("REST_OPTION", "end")
            case.set_value("CONTINUE_RUN", False)
            case.set_value("NEONVERSION", version)

            if run_type == "ad":
                case.set_value("CLM_FORCE_COLDSTART", "on")
                case.set_value("CLM_ACCELERATED_SPINUP", "on")
                case.set_value("RUN_REFDATE", "0018-01-01")
                case.set_value("RUN_STARTDATE", "0018-01-01")
                case.set_value("RESUBMIT", 1)
                case.set_value("STOP_N", run_length)
            else:
                case.set_value("CLM_FORCE_COLDSTART", "off")
                case.set_value("CLM_ACCELERATED_SPINUP", "off")
                case.set_value("RUN_TYPE", "hybrid")

            if run_type == "postad":
                self.set_ref_case(case)
                case.set_value("STOP_N", run_length)

            if run_type == "transient":
                if self.finidat:
                    case.set_value("RUN_TYPE", "startup")
                else:
                    if not self.set_ref_case(case):
                        return
                case.set_value("CALENDAR", "GREGORIAN")
                case.set_value("RESUBMIT", 0)
                case.set_value("STOP_OPTION", "nmonths")

            if not rundir:
                rundir = case.get_value("RUNDIR")

            self.modify_user_nl(case_root, run_type, rundir)

            # ==============================================================
            # STEP A – optionally download forcing from S3
            # ==============================================================
            if s3_input_bucket:
                s3_local_dest = os.path.join(rundir, "inputdata_s3")
                run_input_root = download_s3_forcing(
                    bucket_name=s3_input_bucket,
                    prefix=s3_input_prefix,
                    site_code=self.name,
                    local_dest=s3_local_dest,
                    endpoint_url=s3_endpoint_url,
                )
                case.set_value("DIN_LOC_ROOT", run_input_root)
                print(f"[{self.name}] DIN_LOC_ROOT → {run_input_root}  (S3 source)")
            else:
                # FIX (Bug 1): read the real DIN_LOC_ROOT from the case
                # instead of assuming a hardcoded rundir/inputdata path.
                run_input_root = case.get_value("DIN_LOC_ROOT")
                print(f"[{self.name}] DIN_LOC_ROOT (local) → {run_input_root}")

            # Diagnostic: confirm the source path actually exists
            if not os.path.isdir(run_input_root):
                raise RuntimeError(
                    f"[{self.name}] run_input_root does not exist: {run_input_root}\n"
                    f"Cannot proceed with transform or namelist generation."
                )

            # ==============================================================
            # STEP B – optionally transform the forcing variable
            # ==============================================================
            if transform_var:
                out_root = os.path.join(rundir, transform_tag)
                print(
                    f"[{self.name}] Transforming '{transform_var}': "
                    f"method={transform_method}, value={transform_value}\n"
                    f"  source : {run_input_root}\n"
                    f"  dest   : {out_root}"
                )
                transform_neon_input_dir(
                    input_root=run_input_root,
                    output_root=out_root,
                    site_code=self.name,
                    var_name=transform_var,
                    method=transform_method,
                    factor=transform_value if transform_method == "scaling" else 1.0,
                    value=transform_value if transform_method == "add" else 0.0,
                    seasonal_factors=seasonal_factors,
                    noise_mode=noise_mode,
                    noise_sigma=noise_sigma,
                    noise_seed=noise_seed,
                )
                # Repoint to transformed data
                case.set_value("DIN_LOC_ROOT", out_root)
                print(f"[{self.name}] DIN_LOC_ROOT → {out_root}  (transformed)")
            # ==============================================================

            # FIX (Bug 2): create_namelists + check_all_input_data run AFTER
            # DIN_LOC_ROOT is finalised (post S3 download + transform).
            case.create_namelists()
            case.check_all_input_data()

            if not setup_only:
                archroot = os.path.join(os.path.dirname(base_case_root), "archive")
                exp_name = f"{transform_var}_{transform_value}" if transform_var else "control"
                archroot_exp = os.path.join(archroot, self.name, exp_name)
                case.set_value("DOUT_S_ROOT", archroot_exp)
                print(f"[{self.name}] Archive root → {archroot_exp}")
                case.submit(no_batch=no_batch)

    # ------------------------------------------------------------------
    def set_ref_case(self, case):
        rundir = case.get_value("RUNDIR")
        case_root = case.get_value("CASEROOT")
        if case_root.endswith(".postad"):
            ref_case_root = case_root.replace(".postad", ".ad")
            root = ".ad"
        else:
            ref_case_root = case_root.replace(".transient", ".postad")
            root = ".postad"

        if not os.path.isdir(ref_case_root):
            logger.warning(
                f"ERROR: spinup must be completed first; missing {ref_case_root}"
            )
            return False

        with Case(ref_case_root) as refcase:
            refrundir = refcase.get_value("RUNDIR")
        case.set_value("RUN_REFDIR", refrundir)
        case.set_value("RUN_REFCASE", os.path.basename(ref_case_root))

        refdate = None
        for reffile in glob.iglob(
            refrundir + f"/{self.name}{root}.clm2.r.*.nc"
        ):
            m = re.search(r"(\d{4}-\d{2}-\d{2})-\d{5}\.nc", reffile)
            if m:
                refdate = m.group(1)
            symlink_force(reffile, os.path.join(rundir, os.path.basename(reffile)))

        logger.info(f"refdate = {refdate}")
        if not refdate:
            logger.warning(f"Could not find refcase for {case_root}")
            return False

        for rpfile in glob.iglob(refrundir + "/rpointer*"):
            safe_copy(rpfile, rundir)

        if not os.path.isdir(os.path.join(rundir, "inputdata")) and \
                os.path.isdir(os.path.join(refrundir, "inputdata")):
            symlink_force(
                os.path.join(refrundir, "inputdata"),
                os.path.join(rundir, "inputdata"),
            )

        case.set_value("RUN_REFDATE", refdate)
        if case_root.endswith(".postad"):
            case.set_value("RUN_STARTDATE", refdate)
        return True

    # ------------------------------------------------------------------
    def modify_user_nl(self, case_root, run_type, rundir):
        user_nl_fname = os.path.join(case_root, "user_nl_clm")
        user_nl_lines = None
        if run_type == "transient":
            if self.finidat:
                user_nl_lines = [
                    "finidat = '{}/inputdata/lnd/ctsm/initdata/{}'".format(
                        rundir, self.finidat
                    )
                ]
        else:
            user_nl_lines = [
                "hist_fincl2 = ''",
                "hist_mfilt = 20",
                "hist_nhtfrq = -8760",
                "hist_empty_htapes = .true.",
                "hist_fincl1 = 'TOTECOSYSC', 'TOTECOSYSN', 'TOTSOMC', 'TOTSOMN', "
                "'TOTVEGC', 'TOTVEGN', 'TLAI', 'GPP', 'CPOOL', 'NPP', 'TWS', 'H2OSNO'",
            ]
        if user_nl_lines:
            with open(user_nl_fname, "a") as fd:
                for line in user_nl_lines:
                    fd.write(f"{line}\n")


# ===========================================================================
# SECTION 7 – NEON listing helpers
# ===========================================================================

def check_neon_listing(valid_neon_sites):
    listing_file = "listing.csv"
    url = "https://storage.neonscience.org/neon-ncar/listing.csv"
    download_file(url, listing_file)
    return parse_neon_listing(listing_file, valid_neon_sites)


def parse_neon_listing(listing_file, valid_neon_sites):
    available_list = []
    df = pd.read_csv(listing_file)
    finidatlist = df[df["object"].str.contains("lnd/ctsm")]
    df = df[df["object"].str.contains("atm/cdeps/")]
    df = df["object"].str.split("/", expand=True)
    grouped_df = df.groupby(8)

    for key, item in grouped_df:
        if not any(key in x for x in valid_neon_sites):
            continue
        site_name = key
        tmp_df = grouped_df.get_group(key)
        tmp_df = tmp_df[tmp_df[9].str.contains(r"\d{4}-\d{2}\.nc")]
        latest_version = tmp_df[7].iloc[-1]
        tmp_df = tmp_df[tmp_df[7].str.contains(latest_version)]
        tmp_df = tmp_df.copy()
        tmp_df[9] = tmp_df[9].str.replace(".nc", "")
        tmp_df2 = tmp_df[9].str.split("-", expand=True)
        tmp_df2[0] = tmp_df2[0].str.slice(-4)

        start_year, end_year = tmp_df2[0].iloc[0], tmp_df2[0].iloc[-1]
        start_month, end_month = tmp_df2[1].iloc[0], tmp_df2[1].iloc[-1]

        finidat = None
        for line in finidatlist["object"]:
            if site_name in line:
                finidat = line.split(",")[0].split("/")[-1]

        available_list.append(
            NeonSite(site_name, start_year, end_year, start_month, end_month, finidat)
        )

    return available_list


# ===========================================================================
# SECTION 8 – Entry point
# ===========================================================================

def main(description):
    cesmroot = path_to_ctsm_root()
    valid_neon_sites = sorted([
        v.split("/")[-1]
        for v in glob.glob(
            os.path.join(cesmroot, "cime_config", "usermods_dirs", "clm", "NEON", "[!d]*")
        )
    ])

    (
        site_list, output_root, run_type, overwrite, run_length,
        base_case_root, run_from_postad, setup_only, no_batch, rerun,
        user_version,
        transform_var, transform_method, transform_value,
        seasonal_factors, noise_mode, noise_sigma, noise_seed, transform_tag,
        s3_input_bucket, s3_input_prefix, s3_endpoint_url,
    ) = get_parser(sys.argv, description, valid_neon_sites)

    if output_root:
        os.makedirs(output_root, exist_ok=True)

    available_list = check_neon_listing(valid_neon_sites)

    res = "CLM_USRDAT"
    compset = "IHist1PtClm60Bgc" if run_type == "transient" else "I1PtClm60Bgc"

    for neon_site in available_list:
        if neon_site.name not in site_list:
            continue
        if run_from_postad:
            neon_site.finidat = None
        if not base_case_root:
            base_case_root = neon_site.build_base_case(
                cesmroot, output_root, res, compset, overwrite, setup_only
            )
        logger.info(f"Running CTSM for: {neon_site.name}")
        neon_site.run_case(
            base_case_root, run_type, run_length, user_version,
            overwrite, setup_only, no_batch, rerun,
            transform_var=transform_var,
            transform_method=transform_method,
            transform_value=transform_value,
            seasonal_factors=seasonal_factors,
            noise_mode=noise_mode,
            noise_sigma=noise_sigma,
            noise_seed=noise_seed,
            transform_tag=transform_tag,
            s3_input_bucket=s3_input_bucket,
            s3_input_prefix=s3_input_prefix,
            s3_endpoint_url=s3_endpoint_url,
        )


if __name__ == "__main__":
    main(__doc__)
