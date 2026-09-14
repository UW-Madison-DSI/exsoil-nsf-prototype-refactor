"""Goodness-of-fit scores that say *how* a model misses, not only *whether*.

`compute_fit` (in neon_eval_utils) reports R^2, RMSE, MAE and bias. Those
detect disagreement but cannot attribute it: one worse RMSE could be an
amplitude bias, a seasonal peak in the wrong month, noise, or a few bad
months. This module adds the two ILAMB-style scores that separate those
cases, without adopting ILAMB itself (decision #13):

Seasonal cycle
    The mean annual cycle of each series: the average value for each month
    of the year over every year present. Compared on when it peaks (phase)
    and how big its swing is (amplitude).

    seasonal_phase_shift_months   months between the model's peak month and
                                  the observed peak month, in [-6, 6].
                                  Positive: the model peaks late.
    seasonal_amplitude_ratio      model swing / observed swing. 1 is right;
                                  2 means the model's seasons are twice too
                                  strong.
    seasonal_climatology_r        correlation of the two 12-month curves.
    seasonal_score                0.5 * (1 + cos(2 pi shift / 12)): 1 when the
                                  peaks coincide, 0 when six months apart.
                                  ILAMB's definition, so the number is
                                  comparable to published scores.

Interannual variability
    What is left after the mean annual cycle is removed from each year: the
    good years and the bad years. A model can get the average year right and
    still flatten these.

    iav_std_ratio                 spread of model anomalies / spread of
                                  observed anomalies. 1 is right; 0.5 means
                                  the model damps year-to-year variation
                                  by half.
    iav_anomaly_r                 correlation of the anomaly series: does the
                                  model have the *same* good and bad years?
    iav_score                     exp(-|ratio - 1|), ILAMB's definition.
    n_months, n_years             months of overlap scored, and the calendar
                                  years they touch.
    short_record                  True below 48 months of overlap. Year-to-
                                  year variability from under four years of
                                  data is barely defined, and the flag exists
                                  so the number is not read with more
                                  confidence than it has earned. The NEON
                                  observation window is 45 months, so every
                                  real Hub 2 run is flagged, on purpose.

Time axes
    Inputs must carry a real time index: DatetimeIndex, PeriodIndex, or
    xarray's CFTimeIndex. Anything else raises rather than being guessed at,
    because a positional index coerced to dates lands in 1970 and collapses
    into a single month without error.

    CTSM stamps monthly files at the start of the *next* month, so a model
    series indexed by the raw `time` coordinate is a month late. The reader
    attaches a `month` coordinate for this reason (data_access), and
    `evaluate_series` uses it whenever an xarray DataArray carrying one is
    passed. Build the model series from `month`, never from `time` or
    `mcdate`, on the monthly stream.

Resolution
    Each input's cadence is inferred separately. When they differ, the finer
    one is averaged to the coarser before anything is compared, and the result
    says so under `resampled`. Correlation is then computed at the shared
    resolution. Bias, RMSE and MAE are computed on monthly means when that is
    finer than monthly, because the flux-partitioning negatives in observed
    GPP distort magnitude metrics at daily and sub-daily resolution but leave
    correlation alone (decision 005, amended 2026-08-26). Nothing here is
    specific to GPP: soil water and ET go through the same path, and negative
    values are never altered.

    When both inputs are sub-daily, their timestamps are rounded to the
    nearest minute before intersecting, because CTSM's float32 `time` and
    NEON's per-month float epoch both decode with sub-second drift that would
    otherwise leave a half-hourly model series and a half-hourly observation
    series sharing almost no exact stamps.

Small samples
    Zero shared timestamps is an error, not an all-NaN result: it means the
    join failed. Correlation needs at least three pairs and is NaN below that,
    where `compute_fit` used to return 1.0 for two points.
"""
from __future__ import annotations

import math
import warnings
from typing import Dict, Mapping, Optional, Union

import numpy as np
import pandas as pd
import xarray as xr

MONTHS_PER_YEAR = 12
SHORT_RECORD_MONTHS = 48
MIN_PAIRS_FOR_CORRELATION = 3
MONTH_COORDINATE = "month"

SeriesLike = Union[pd.Series, xr.DataArray, np.ndarray, list]
CADENCE_ORDER = ("sub-daily", "daily", "monthly")


class ResolutionMismatchWarning(UserWarning):
    """One series was averaged to the other's coarser cadence before scoring."""


def _to_datetime_index(index: pd.Index) -> pd.DatetimeIndex:
    """Accept DatetimeIndex, PeriodIndex or CFTimeIndex. Refuse everything else."""
    if isinstance(index, pd.DatetimeIndex):
        return index
    if isinstance(index, pd.PeriodIndex):
        return index.to_timestamp()
    if type(index).__name__ == "CFTimeIndex":
        return index.to_datetimeindex()
    raise TypeError(
        f"A time index is required (DatetimeIndex, PeriodIndex or CFTimeIndex), got "
        f"{type(index).__name__}. A positional index cannot be scored: coerced to dates "
        "it would land in 1970 and collapse into one month without error."
    )


def _as_time_series(values: SeriesLike, index: Optional[pd.Index]) -> pd.Series:
    """Coerce to a float Series on a DatetimeIndex, using CTSM's `month` coordinate when present."""
    if isinstance(values, xr.DataArray):
        if MONTH_COORDINATE in values.coords:
            index = pd.PeriodIndex(values[MONTH_COORDINATE].values, freq="M")
        elif index is None:
            index = values.indexes.get("time")
            if index is None:
                raise TypeError("DataArray has neither a `month` coordinate nor a `time` index")
        values = values.squeeze().values
    elif isinstance(values, pd.Series):
        if index is None:
            index = values.index
        values = values.to_numpy()
    elif index is None:
        raise TypeError("pass Series or DataArray with time indexes, or arrays plus `index`")

    series = pd.Series(np.asarray(values, dtype=float).ravel(), index=_to_datetime_index(index))
    duplicates = int(series.index.duplicated().sum())
    if duplicates:
        raise ValueError(
            f"{duplicates} duplicate timestamp(s) in the series. Aggregate to one value per "
            "time first (for example one soil depth, or one site) so the average is deliberate."
        )
    return series.dropna().sort_index()


def infer_resolution(index: pd.DatetimeIndex) -> str:
    """'sub-daily', 'daily' or 'monthly', from the median spacing of the index."""
    if len(index) < 2:
        return "monthly"
    step = pd.Series(index).diff().median()
    if step < pd.Timedelta(hours=23):
        return "sub-daily"
    if step < pd.Timedelta(days=27):
        return "daily"
    return "monthly"


def _to_resolution(series: pd.Series, resolution: str) -> pd.Series:
    """Average a series onto month-start or day-start stamps, or round sub-daily stamps to the nearest minute.

    Monthly stamps mid-month move to month start. Sub-daily stamps are rounded
    to the nearest minute rather than averaged, because both a model series
    and an observation series sit on a half-hourly grid but CTSM writes `time`
    as float32 days-since, which decodes with sub-second drift (a stamp meant
    to be 2018-01-01T00:30:00 decodes as ...T00:30:00.000053644); NEON's
    half-hourly files carry their own independent drift. One minute is far
    below the smallest real spacing (30 minutes) and far above that drift.
    Data genuinely finer than one-minute resolution is out of scope: if
    rounding collapses two distinct stamps into one, that is a real duplicate
    and is raised as such below.
    """
    if resolution == "monthly":
        return series.resample("MS").mean().dropna()
    if resolution == "daily":
        return series.resample("D").mean().dropna()
    rounded = series.copy()
    rounded.index = rounded.index.round("min")
    duplicates = int(rounded.index.duplicated().sum())
    if duplicates:
        raise ValueError(
            f"{duplicates} duplicate timestamp(s) after rounding sub-daily stamps to the "
            "nearest minute. That means two distinct stamps were within a minute of each "
            "other, which is finer than this module scores; aggregate to at least "
            "one-minute spacing first."
        )
    return rounded


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < MIN_PAIRS_FOR_CORRELATION or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def magnitude_metrics(obs: np.ndarray, sim: np.ndarray) -> Dict[str, float]:
    """R2, RMSE, MAE and Bias on aligned, finite arrays.

    The single implementation of the four legacy keys; `compute_fit` calls this.
    Raises on empty input rather than returning NaN, because no pairs means the
    join failed.
    """
    obs = np.asarray(obs, dtype=float)
    sim = np.asarray(sim, dtype=float)
    if len(obs) == 0:
        raise ValueError("no observation/simulation pairs to score")
    r = _pearson(obs, sim)
    return {
        "R2": r ** 2 if np.isfinite(r) else float("nan"),
        "RMSE": float(np.sqrt(np.mean((sim - obs) ** 2))),
        "MAE": float(np.mean(np.abs(sim - obs))),
        "Bias": float(np.mean(sim - obs)),
    }


def monthly_means(series: pd.Series) -> pd.Series:
    """Calendar-month means on a month-start index. A no-op for month-start monthly input."""
    return _to_resolution(series, "monthly")


def climatology(monthly: pd.Series) -> pd.Series:
    """Mean annual cycle: one value per month of the year, indexed 1..12."""
    return monthly.groupby(monthly.index.month).mean().reindex(range(1, MONTHS_PER_YEAR + 1))


def anomalies(monthly: pd.Series) -> pd.Series:
    """Departures from the mean annual cycle, month by month."""
    clim = climatology(monthly)
    return monthly - clim.reindex(monthly.index.month).to_numpy()


def _circular_month_difference(later: int, earlier: int) -> int:
    """Difference in months on a 12-month circle, in [-6, 6]."""
    diff = (later - earlier) % MONTHS_PER_YEAR
    return diff - MONTHS_PER_YEAR if diff > MONTHS_PER_YEAR // 2 else diff


def seasonal_cycle_scores(obs_monthly: pd.Series, sim_monthly: pd.Series) -> Dict[str, float]:
    """Compare the mean annual cycles of two monthly series. See module docstring."""
    clim_obs = climatology(obs_monthly)
    clim_sim = climatology(sim_monthly)
    shared = clim_obs.notna() & clim_sim.notna()
    if shared.sum() < 3:
        return {
            "seasonal_phase_shift_months": float("nan"),
            "seasonal_amplitude_ratio": float("nan"),
            "seasonal_climatology_r": float("nan"),
            "seasonal_score": float("nan"),
        }
    co = clim_obs[shared]
    cs = clim_sim[shared]
    shift = _circular_month_difference(int(cs.idxmax()), int(co.idxmax()))
    swing_obs = float(co.max() - co.min())
    swing_sim = float(cs.max() - cs.min())
    return {
        "seasonal_phase_shift_months": float(shift),
        "seasonal_amplitude_ratio": swing_sim / swing_obs if swing_obs > 0 else float("nan"),
        "seasonal_climatology_r": _pearson(co.to_numpy(), cs.to_numpy()),
        "seasonal_score": 0.5 * (1.0 + math.cos(2.0 * math.pi * shift / MONTHS_PER_YEAR)),
    }


def interannual_scores(obs_monthly: pd.Series, sim_monthly: pd.Series) -> Dict[str, object]:
    """Compare year-to-year departures from the mean annual cycle. See module docstring."""
    common = obs_monthly.index.intersection(sim_monthly.index)
    anom_obs = anomalies(obs_monthly).reindex(common)
    anom_sim = anomalies(sim_monthly).reindex(common)
    n_months = int(len(common))
    std_obs = float(anom_obs.std()) if n_months > 1 else float("nan")
    std_sim = float(anom_sim.std()) if n_months > 1 else float("nan")
    ratio = std_sim / std_obs if np.isfinite(std_obs) and std_obs > 0 else float("nan")
    return {
        "iav_std_ratio": ratio,
        "iav_anomaly_r": _pearson(anom_obs.to_numpy(), anom_sim.to_numpy()),
        "iav_score": math.exp(-abs(ratio - 1.0)) if np.isfinite(ratio) else float("nan"),
        "n_months": n_months,
        "n_years": int(pd.Index(common.year).nunique()),
        "short_record": n_months < SHORT_RECORD_MONTHS,
    }


def evaluate_series(
    obs: SeriesLike,
    sim: SeriesLike,
    index: Optional[pd.Index] = None,
) -> Dict[str, object]:
    """Score a model series against an observed one.

    Args:
        obs, sim: Series or DataArrays with time indexes, or arrays plus
            `index`. A DataArray carrying CTSM's `month` coordinate is indexed
            by it, which is the only correct way to place monthly model output
            in time (see module docstring).
        index: time index for array inputs. DatetimeIndex, PeriodIndex or
            CFTimeIndex.

    Returns a dict with, in this order:
        n, resolution, resampled           pairs scored, shared cadence, and
                                           which input was averaged to reach it
        r, R2                              correlation at the shared cadence
        Bias, RMSE, MAE                    on monthly means (see module docstring)
        seasonal_*                         mean-annual-cycle comparison
        iav_*, n_months, n_years,          year-to-year variability comparison
        short_record

    The four magnitude keys match `compute_fit` on month-start monthly input.

    Raises:
        TypeError: for an index that is not a time index.
        ValueError: for duplicate timestamps, or no shared timestamps.
    """
    obs_s = _as_time_series(obs, index)
    sim_s = _as_time_series(sim, index)

    res_obs, res_sim = infer_resolution(obs_s.index), infer_resolution(sim_s.index)
    resolution = max(res_obs, res_sim, key=CADENCE_ORDER.index)
    resampled = None
    if res_obs != res_sim:
        resampled = "sim" if res_sim != resolution else "obs"
        warnings.warn(
            f"observations are {res_obs} and simulations are {res_sim}; averaging the "
            f"{resampled} series to {resolution} before scoring",
            ResolutionMismatchWarning,
            stacklevel=2,
        )
    if resolution == "monthly":
        # month-start stamps for both, so mid-month observation stamps still align
        obs_s, sim_s = _to_resolution(obs_s, "monthly"), _to_resolution(sim_s, "monthly")
    elif resolution == "sub-daily":
        # both series are sub-daily here (resolution is the coarser of the two);
        # round both onto the same one-minute grid so float32 decode drift does
        # not make two half-hourly series miss each other entirely (see
        # _to_resolution)
        obs_s, sim_s = _to_resolution(obs_s, "sub-daily"), _to_resolution(sim_s, "sub-daily")
    elif res_obs != res_sim:
        obs_s, sim_s = _to_resolution(obs_s, resolution), _to_resolution(sim_s, resolution)

    common = obs_s.index.intersection(sim_s.index)
    obs_bounds = (obs_s.index.min(), obs_s.index.max())
    sim_bounds = (sim_s.index.min(), sim_s.index.max())
    obs_s, sim_s = obs_s.reindex(common), sim_s.reindex(common)
    # DatetimeIndex.intersection takes a range-based shortcut when both indexes
    # carry the same inferred freq (e.g. two daily series stamped at different
    # times of day), and that shortcut can hand back labels that are not
    # actually present in both indexes. Reindexing onto those labels fills the
    # gaps with NaN; drop them before checking for an empty join, or the guard
    # below never fires and a mismatched pair scores as an all-NaN "fit".
    paired = obs_s.notna() & sim_s.notna()
    obs_s, sim_s = obs_s[paired], sim_s[paired]
    if len(obs_s) == 0:
        raise ValueError(
            f"no shared timestamps between observations ({obs_bounds[0]} to "
            f"{obs_bounds[1]}) and simulations ({sim_bounds[0]} to {sim_bounds[1]})"
        )

    r = _pearson(obs_s.to_numpy(), sim_s.to_numpy())
    obs_m, sim_m = monthly_means(obs_s), monthly_means(sim_s)
    shared_months = obs_m.index.intersection(sim_m.index)
    obs_m, sim_m = obs_m.reindex(shared_months), sim_m.reindex(shared_months)
    # obs_m and sim_m are resampled independently and can diverge, so the same
    # fast-path hazard applies here as above.
    paired_months = obs_m.notna() & sim_m.notna()
    obs_m, sim_m = obs_m[paired_months], sim_m[paired_months]
    magnitude = magnitude_metrics(obs_m.to_numpy(), sim_m.to_numpy())

    out: Dict[str, object] = {
        "n": int(len(common)),
        "resolution": resolution,
        "resampled": resampled,
        "r": r,
        "R2": r ** 2 if np.isfinite(r) else float("nan"),
        "Bias": magnitude["Bias"],
        "RMSE": magnitude["RMSE"],
        "MAE": magnitude["MAE"],
    }
    out.update(seasonal_cycle_scores(obs_m, sim_m))
    out.update(interannual_scores(obs_m, sim_m))
    return out


def evaluate_fit(df: pd.DataFrame, obs: str, sim: str, time: Optional[str] = None) -> Dict[str, object]:
    """`evaluate_series` on two columns of a frame. Sibling of compute_fit.

    `time` names the column holding timestamps. When None, a `time` column is
    used if the frame has one, otherwise the frame's index. Either way the
    result must be a real time index, or this raises.
    """
    if time is None:
        time = "time" if "time" in df.columns else None
    if time is None:
        index = df.index
    else:
        index = pd.DatetimeIndex(pd.to_datetime(df[time]))
    return evaluate_series(df[obs].to_numpy(), df[sim].to_numpy(), index=index)


def evaluate_pairs(df: pd.DataFrame, pairs: Mapping[str, str], time: Optional[str] = None) -> pd.DataFrame:
    """Score several observed/simulated column pairs at once, one row per pair.

    Built for component-wise comparison: when partitioned tower ET arrives,
    pass {"ET_obs": "ET", "FCTR_obs": "FCTR", ...} and read one table.
    """
    rows = {obs_col: evaluate_fit(df, obs_col, sim_col, time=time) for obs_col, sim_col in pairs.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def summarize_fit(metrics: Mapping[str, object], variable: str = "the model") -> str:
    """One paragraph, in plain words, saying how the model misses."""
    parts = []
    shift = metrics.get("seasonal_phase_shift_months")
    if shift is not None and np.isfinite(shift):
        if shift == 0:
            parts.append(f"{variable} peaks in the same month as the observations")
        else:
            when = "late" if shift > 0 else "early"
            parts.append(f"{variable} peaks {abs(int(shift))} month(s) {when}")
    ratio = metrics.get("seasonal_amplitude_ratio")
    if ratio is not None and np.isfinite(ratio):
        parts.append(f"its seasonal swing is {ratio:.2f}x the observed")
    iav = metrics.get("iav_std_ratio")
    if iav is not None and np.isfinite(iav):
        parts.append(f"its year-to-year variability is {iav:.2f}x the observed")
    text = "; ".join(parts) + "." if parts else "Too little data to attribute the misfit."
    if metrics.get("short_record"):
        text += (f" Only {metrics.get('n_months')} months over {metrics.get('n_years')} calendar"
                 " year(s) contribute, so the interannual numbers are indicative at best.")
    if metrics.get("resampled"):
        text += f" The {metrics['resampled']} series was averaged to {metrics.get('resolution')} to match."
    return text
