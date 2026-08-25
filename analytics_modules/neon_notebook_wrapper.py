from pathlib import Path
import os
import fnmatch
import botocore

from .data_access import get_s3_client

# -------------------------------------------------------------------
# Configuration (container-internal)
# -------------------------------------------------------------------
INPUT_ROOT = Path("/opt/neon_analytics/data/inputdata")
OUTPUT_ROOT = Path("/home/user/CLM-NEON")


# -------------------------------------------------------------------
# List CTSM simulation files on S3 (glob-equivalent)
# -------------------------------------------------------------------
def list_sim_files_s3(
    *,
    bucket: str,
    neon_site: str,
    year: str,
    component: str = "lnd",
    stream: str = "hist",
    archive_root: str = "archive",
    stream_token: str = "h1",
):
    """
    Equivalent of:
      /archive/<site>.transient/lnd/hist/<site>.transient.clm2.h1.<year>*.nc

    stream_token defaults to the unsuffixed "h1" because the S3 copies predate
    the CTSM 5.4 rename. Live in-container output uses "h1a"/"h0a"; read that
    with data_access.find_ctsm_hist_files, which resolves the token itself.
    """
    s3 = get_s3_client()

    prefix = f"{archive_root}/{neon_site}.transient/{component}/{stream}/"
    pattern = f"{neon_site}.transient.clm2.{stream_token}.{year}*.nc"

    paginator = s3.get_paginator("list_objects_v2")
    matches = []

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if fnmatch.fnmatch(key.split("/")[-1], pattern):
                    matches.append(key)
    except botocore.exceptions.ClientError as e:
        raise RuntimeError(f"S3 listing failed: {e}")

    return sorted(matches)


# -------------------------------------------------------------------
# Download files into local inputdata/
# -------------------------------------------------------------------
def download_sim_files(
    *,
    bucket: str,
    keys: list[str],
    local_dir: Path,
    overwrite: bool = False,
):
    s3 = get_s3_client()
    local_dir.mkdir(parents=True, exist_ok=True)

    for key in keys:
        local_path = local_dir / Path(key).name

        if local_path.exists() and not overwrite:
            continue

        try:
            s3.download_file(bucket, key, str(local_path))
        except botocore.exceptions.ClientError as e:
            raise RuntimeError(f"Download {e}")