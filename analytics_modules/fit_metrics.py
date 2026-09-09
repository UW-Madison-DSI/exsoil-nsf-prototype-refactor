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
    n_years, short_record         how many calendar years contributed, and a
                                  flag when fewer than four did. Year-to-year
                                  variability over three years is barely
                                  defined, and the flag exists so the number
                                  is not read with more confidence than it
                                  has earned. The NEON window is 45 months.

Resolution
    Correlation is computed at the resolution the data arrive in. Bias, RMSE
    and MAE are computed on monthly means when the input is finer, because
    the flux-partitioning negatives in observed GPP distort magnitude
    metrics at daily and sub-daily resolution but leave correlation alone
    (decision 005, amended 2026-08-26). Nothing here is specific to GPP:
    soil water and ET go through the same path, and negative values are
    never altered.
"""
from __future__ import annotations

import math
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd

MONTHS_PER_YEAR = 12
SHORT_RECORD_YEARS = 4


def _as_time_series(values, index) -> pd.Series:
    """Coerce to a float Series on a DatetimeIndex, dropping NaN."""
    series = pd.Series(np.asarray(values, dtype=float), index=index)
    if isinstance(series.index, pd.PeriodIndex):
        series.index = series.index.to_timestamp()
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)
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


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def magnitude_metrics(obs: np.ndarray, sim: np.ndarray) -> Dict[str, float]:
    """R2, RMSE, MAE and Bias on aligned arrays. Same definitions as compute_fit."""
    obs = np.asarray(obs, dtype=float)
    sim = np.asarray(sim, dtype=float)
    r = _pearson(obs, sim)
    return {
        "R2": r ** 2 if np.isfinite(r) else float("nan"),
        "RMSE": float(np.sqrt(np.mean((sim - obs) ** 2))) if len(obs) else float("nan"),
        "MAE": float(np.mean(np.abs(sim - obs))) if len(obs) else float("nan"),
        "Bias": float(np.mean(sim - obs)) if len(obs) else float("nan"),
    }


def monthly_means(series: pd.Series) -> pd.Series:
    """Calendar-month means on a month-start index. A no-op for monthly input."""
    return series.resample("MS").mean().dropna()


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


def interannual_scores(obs_monthly: pd.Series, sim_monthly: pd.Series) -> Dict[str, float]:
    """Compare year-to-year departures from the mean annual cycle. See module docstring."""
    common = obs_monthly.index.intersection(sim_monthly.index)
    anom_obs = anomalies(obs_monthly).reindex(common)
    anom_sim = anomalies(sim_monthly).reindex(common)
    n_years = int(pd.Index(common.year).nunique())
    std_obs = float(anom_obs.std()) if len(common) > 1 else float("nan")
    std_sim = float(anom_sim.std()) if len(common) > 1 else float("nan")
    ratio = std_sim / std_obs if std_obs and np.isfinite(std_obs) and std_obs > 0 else float("nan")
    return {
        "iav_std_ratio": ratio,
        "iav_anomaly_r": _pearson(anom_obs.to_numpy(), anom_sim.to_numpy()),
        "iav_score": math.exp(-abs(ratio - 1.0)) if np.isfinite(ratio) else float("nan"),
        "n_years": n_years,
        "short_record": n_years < SHORT_RECORD_YEARS,
    }


def evaluate_series(obs, sim, index=None) -> Dict[str, object]:
    """Score a model series against an observed one, at the resolution they arrive in.

    Args:
        obs, sim: array-likes or Series. If Series, their own indexes are used
            and aligned on shared timestamps; otherwise `index` is required.
        index: time index for array inputs. DatetimeIndex or PeriodIndex.

    Returns a dict with, in this order:
        n, resolution                      pairs scored and the inferred cadence
        r, R2                              correlation at native resolution
        Bias, RMSE, MAE                    on monthly means (see module docstring)
        seasonal_*                         mean-annual-cycle comparison
        iav_*, n_years, short_record       year-to-year variability comparison

    The four magnitude keys match `compute_fit` exactly on monthly input, so
    a caller that only reads those can switch without seeing a change.
    """
    if index is None:
        if not (isinstance(obs, pd.Series) and isinstance(sim, pd.Series)):
            raise ValueError("pass Series with time indexes, or arrays plus `index`")
        obs_s = _as_time_series(obs.to_numpy(), obs.index)
        sim_s = _as_time_series(sim.to_numpy(), sim.index)
    else:
        obs_s = _as_time_series(obs, index)
        sim_s = _as_time_series(sim, index)

    common = obs_s.index.intersection(sim_s.index)
    obs_s, sim_s = obs_s.reindex(common), sim_s.reindex(common)
    resolution = infer_resolution(common)

    r = _pearson(obs_s.to_numpy(), sim_s.to_numpy())
    obs_m, sim_m = monthly_means(obs_s), monthly_means(sim_s)
    shared_months = obs_m.index.intersection(sim_m.index)
    obs_m, sim_m = obs_m.reindex(shared_months), sim_m.reindex(shared_months)
    magnitude = magnitude_metrics(obs_m.to_numpy(), sim_m.to_numpy())

    out: Dict[str, object] = {
        "n": int(len(common)),
        "resolution": resolution,
        "r": r,
        "R2": r ** 2 if np.isfinite(r) else float("nan"),
        "Bias": magnitude["Bias"],
        "RMSE": magnitude["RMSE"],
        "MAE": magnitude["MAE"],
    }
    out.update(seasonal_cycle_scores(obs_m, sim_m))
    out.update(interannual_scores(obs_m, sim_m))
    return out


def evaluate_fit(df: pd.DataFrame, obs: str, sim: str, time: Optional[str] = "time") -> Dict[str, object]:
    """`evaluate_series` on two columns of a frame. Sibling of compute_fit.

    `time` names the column holding timestamps; pass None to use the index.
    """
    index = df.index if time is None else pd.DatetimeIndex(pd.to_datetime(df[time]))
    return evaluate_series(df[obs].to_numpy(), df[sim].to_numpy(), index=index)


def evaluate_pairs(df: pd.DataFrame, pairs: Mapping[str, str], time: Optional[str] = "time") -> pd.DataFrame:
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
        text += (f" Only {metrics.get('n_years')} calendar year(s) contribute, so the"
                 " interannual numbers are indicative at best.")
    return text
