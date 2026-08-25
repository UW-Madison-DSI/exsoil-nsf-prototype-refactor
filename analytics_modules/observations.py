"""Observed tower fluxes from the NCAR/NEON evaluation files.

The counterpart to `data_access`, which reads *model* output. This reads the
*observations* Hub 2 evaluates the model against.

Source
------
    https://storage.neonscience.org/neon-ncar/NEON/eval_files/v1/{SITE}/{SITE}_eval_{YYYY-MM}.nc

Public and credential-free (the host redirects to a public bucket), one file
per site-month, 2018-01 through 2021-09. Each carries GPP, NEE, sensible and
latent heat, friction velocity and net radiation at half-hourly resolution,
each with a gap-filling quality flag.

Three things about this data drive the design, all established by inspecting
all 225 site-months. See docs/decisions/005-observed-gpp-comparison/.

1. **Units differ from the model.** Observations are umol CO2 m-2 s-1; model
   GPP is gC m-2 s-1. The conversion is x12.011e-6 (12.011 g C per mol).
   Getting it wrong produces a five-order-of-magnitude bias that reads as
   catastrophic model failure rather than a units error, so conversion is the
   default rather than an option.

2. **Observed GPP is often negative** -- 26-36% of half-hourly values, at every
   site, in every season. Towers measure *net* exchange; GPP is derived by
   estimating respiration and subtracting, and the arithmetic returns
   physically impossible negatives when that estimate overshoots or the flux
   is small relative to noise. Monthly aggregation reduces this to 8%, which
   is why `monthly_observed_gpp` is the primary interface. The residual
   negatives are reported, not clamped -- at those magnitudes model and
   observation are both indistinguishable from zero.

3. **18% of site-months contain no GPP at all**, and the quality flag does not
   tell you. ABBY 2018-07 reports GPP_fqc = 0 ("measured") for all 1488
   timesteps while every value is NaN. Anything trusting the flag computes
   statistics over nothing and reports them confidently. Coverage here is
   derived from the values, never the flag.
"""

import os
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
import requests
import xarray as xr

EVAL_BASE_URL = (
    "https://storage.neonscience.org/neon-ncar/NEON/eval_files/v1"
)

# 12.011 g C per mol; observations are umol CO2 m-2 s-1, model GPP is gC m-2 s-1.
UMOL_CO2_TO_GC = 12.011e-6

# The published window. Requests outside it will 404.
EVAL_FIRST_MONTH = "2018-01"
EVAL_LAST_MONTH = "2021-09"

SAMPLE_SITES = ("ABBY", "CLBJ", "CPER", "KONZ", "TALL")


def eval_cache_dir() -> Path:
    """Where downloaded eval files are kept. Override with NEON_EVAL_CACHE."""
    return Path(
        os.path.expanduser(os.getenv("NEON_EVAL_CACHE", "~/.cache/neon-eval"))
    )


def eval_months(first: str = EVAL_FIRST_MONTH, last: str = EVAL_LAST_MONTH) -> List[str]:
    """Every YYYY-MM in the published window, inclusive."""
    return [
        f"{p.year}-{p.month:02d}"
        for p in pd.period_range(first, last, freq="M")
    ]


def eval_file_url(site: str, month: str) -> str:
    """URL of one site-month file. `month` is 'YYYY-MM'."""
    return f"{EVAL_BASE_URL}/{site}/{site}_eval_{month}.nc"


def download_eval_files(
    site: str,
    months: Optional[Iterable[str]] = None,
    *,
    cache_dir=None,
    overwrite: bool = False,
    timeout: int = 90,
) -> List[Path]:
    """Fetch eval files for a site, caching to disk. Returns local paths.

    Replaces the `download_eval_files` referenced but never written in
    Modeling_Hub. No credentials needed.

    Files already cached are skipped unless `overwrite`. A month the server
    does not have is skipped with a warning rather than raising, because gaps
    in this dataset are normal -- see the module docstring.

    Args:
        site: NEON site code, e.g. "KONZ".
        months: 'YYYY-MM' strings. Defaults to the full published window.
        cache_dir: Destination root. Defaults to NEON_EVAL_CACHE.
        overwrite: Re-download files already present.
        timeout: Per-request timeout in seconds.
    """
    months = list(months) if months is not None else eval_months()
    dest = Path(cache_dir) if cache_dir else eval_cache_dir()
    dest = dest / site
    dest.mkdir(parents=True, exist_ok=True)

    paths: List[Path] = []
    for month in months:
        target = dest / f"{site}_eval_{month}.nc"
        if target.exists() and not overwrite:
            paths.append(target)
            continue
        response = requests.get(eval_file_url(site, month), timeout=timeout)
        if response.status_code == 404:
            print(f"  {site} {month}: not published, skipping")
            continue
        response.raise_for_status()
        target.write_bytes(response.content)
        paths.append(target)

    return sorted(paths)


def _read_gpp(path) -> np.ndarray:
    """Raw half-hourly GPP from one file, in umol CO2 m-2 s-1."""
    with xr.open_dataset(path, decode_times=False) as dataset:
        return dataset["GPP"].values.ravel().astype(float)


def monthly_observed_gpp(
    site: str,
    months: Optional[Iterable[str]] = None,
    *,
    cache_dir=None,
    convert_units: bool = True,
    download: bool = True,
) -> pd.DataFrame:
    """Monthly-mean observed GPP for a site, with provenance.

    Monthly is the agreed comparison resolution for Hub 2 (decision 005): it
    reduces the flux-partitioning negatives from ~30% of samples to ~8% of
    months without truncating or discarding anything, and it matches the
    model's own h0a monthly stream so nothing needs resampling.

    Site-months with no finite GPP are omitted from the result rather than
    returned as NaN, so a caller cannot accidentally average over absent data.
    Use the `coverage` column to see how complete the months you did get are.

    Args:
        site: NEON site code.
        months: 'YYYY-MM' strings. Defaults to the full published window.
        cache_dir: Where files are cached. Defaults to NEON_EVAL_CACHE.
        convert_units: Convert to gC m-2 s-1 to match model GPP. Leave True
            unless you specifically want the native umol CO2 m-2 s-1.
        download: Fetch missing files. Set False to work purely from cache.

    Returns:
        DataFrame indexed by month-start Timestamp, with columns:
            gpp                 monthly mean (gC m-2 s-1 unless convert_units=False)
            n_obs               finite half-hourly samples in the month
            coverage            finite fraction of the month's timesteps
            negative_fraction   fraction of finite half-hourly values below zero
            low_signal          True where the monthly mean is negative, i.e.
                                true GPP is near zero and noise dominates;
                                these are reported, not clamped
    """
    months = list(months) if months is not None else eval_months()
    root = (Path(cache_dir) if cache_dir else eval_cache_dir()) / site

    if download:
        download_eval_files(site, months, cache_dir=cache_dir)

    rows = []
    for month in months:
        path = root / f"{site}_eval_{month}.nc"
        if not path.exists():
            continue
        gpp = _read_gpp(path)
        finite = np.isfinite(gpp)
        if not finite.any():
            # Present but empty. The quality flag claims "measured" here, so
            # this check has to be on the values.
            continue
        values = gpp[finite]
        mean = float(values.mean())
        rows.append(
            {
                "month": pd.Timestamp(f"{month}-01"),
                "gpp": mean * UMOL_CO2_TO_GC if convert_units else mean,
                "n_obs": int(finite.sum()),
                "coverage": float(finite.mean()),
                "negative_fraction": float((values < 0).mean()),
                "low_signal": mean < 0,
            }
        )

    if not rows:
        raise FileNotFoundError(
            f"No observed GPP for {site} in {months[0]}..{months[-1]}.\n"
            f"Cache: {root}\n"
            "Either nothing is cached and download=False, or every requested "
            "month is one of the 18% with no GPP data."
        )

    return pd.DataFrame(rows).set_index("month").sort_index()


def observed_gpp_coverage(
    sites: Iterable[str] = SAMPLE_SITES,
    *,
    cache_dir=None,
    download: bool = True,
) -> pd.DataFrame:
    """Per-site summary of how much observed GPP actually exists.

    Worth running before scoping a multi-site comparison: coverage varies
    from 45/45 months at KONZ to 28/45 at ABBY, so a cross-site comparison is
    limited to the months every participating site has.
    """
    rows = []
    for site in sites:
        try:
            frame = monthly_observed_gpp(
                site, cache_dir=cache_dir, download=download
            )
        except FileNotFoundError:
            rows.append({"site": site, "months_with_gpp": 0, "months_possible": len(eval_months())})
            continue
        rows.append(
            {
                "site": site,
                "months_with_gpp": len(frame),
                "months_possible": len(eval_months()),
                "mean_coverage": frame["coverage"].mean(),
                "mean_negative_fraction": frame["negative_fraction"].mean(),
                "low_signal_months": int(frame["low_signal"].sum()),
            }
        )
    return pd.DataFrame(rows).set_index("site")
