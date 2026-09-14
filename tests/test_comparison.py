"""Tier 0 tests for `comparison` and `time_series_comparison` (neon_eval_utils.py).

Both functions had no coverage at all before this suite, despite
`time_series_comparison` being the path Hub 2's notebook actually calls. A
recent change swapped `comparison`'s scoring from `compute_fit` (plain
magnitude metrics on whatever rows it was given) to `evaluate_fit` plus
`summarize_fit` (bias-type metrics on monthly means, plus seasonal-cycle and
interannual scores -- decision 005 / issue #18). These tests pin that
behaviour on synthetic data only, so they run on a machine with nothing
staged: no simulation output, no credentials, no network.

Column convention throughout: for a variable `var`, observations live in
column `var`, the raw model in `sim_var`, and the calibrated model in
`cali_sim_var`.
"""

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from analytics_modules import neon_eval_utils  # noqa: E402
from analytics_modules.fit_metrics import evaluate_fit, summarize_fit  # noqa: E402

pytestmark = pytest.mark.tier0

VAR = "GPP"
VARIABLES_UNITS = {VAR: {"units": "gC m-2 s-1", "var_name": "GPP"}}


@pytest.fixture(autouse=True)
def _close_figures():
    """`comparison()` never closes what it draws; do it here so the suite doesn't leak figures."""
    yield
    plt.close("all")


def _seasonal_daily_frame(
    peak_month_obs: int = 7,
    peak_month_sim: int = 9,
    peak_month_cali: int = 7,
    noise_sim: float = 1.0,
    noise_cali: float = 0.3,
    seed: int = 0,
) -> pd.DataFrame:
    """One year of daily data with a known seasonal cycle.

    Observations peak in `peak_month_obs`. The raw model peaks
    `peak_month_sim` months later (a deliberate seasonal phase shift, 2
    months late by default) and carries more noise. The calibrated model
    peaks in the same month as the observations and is much cleaner, so it
    is known ahead of running the test that it must score better.
    """
    rng = np.random.default_rng(seed)
    time = pd.date_range("2021-01-01", periods=365, freq="D")
    month = time.month
    obs = 10 + 5 * np.cos(2 * np.pi * (month - peak_month_obs) / 12) + rng.normal(0, 0.3, 365)
    sim = 10 + 5 * np.cos(2 * np.pi * (month - peak_month_sim) / 12) + rng.normal(0, noise_sim, 365)
    cali = 10 + 5 * np.cos(2 * np.pi * (month - peak_month_cali) / 12) + rng.normal(0, noise_cali, 365)
    return pd.DataFrame({"time": time, VAR: obs, f"sim_{VAR}": sim, f"cali_sim_{VAR}": cali})


def _hourly_et_frame(seed: int = 1) -> pd.DataFrame:
    """Ten days of hourly data for the `ET` variable, for the aggregation path."""
    rng = np.random.default_rng(seed)
    time = pd.date_range("2021-06-01", periods=24 * 10, freq="h")
    month = time.month
    obs = 10 + 5 * np.cos(2 * np.pi * (month - 7) / 12) + rng.normal(0, 0.3, len(time))
    sim = 10 + 5 * np.cos(2 * np.pi * (month - 9) / 12) + rng.normal(0, 1.0, len(time))
    cali = 10 + 5 * np.cos(2 * np.pi * (month - 7) / 12) + rng.normal(0, 0.3, len(time))
    return pd.DataFrame({"time": time, "ET": obs, "sim_ET": sim, "cali_sim_ET": cali})


def _replicate_time_series_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    """The exact year/month/day grouping `time_series_comparison` does, run independently.

    Used to compute the expected fit numbers without going through the
    buggy function itself (see TestTimeSeriesComparison below).
    """
    df_cal = df.copy()
    df_cal["year"] = df_cal["time"].dt.year
    df_cal["month"] = df_cal["time"].dt.month
    df_cal["day"] = df_cal["time"].dt.day
    df_cal["hour"] = df_cal["time"].dt.hour
    df_daily = df_cal.groupby(["year", "month", "day"]).mean().reset_index()
    df_daily["time"] = pd.to_datetime(df_daily[["year", "month", "day"]])
    return df_daily


class TestComparisonPrintsFitAndSummary:
    """Item 1 & 2: comparison() prints both fits, each with its summary, and
    the numbers are exactly what evaluate_fit computes for those columns.
    """

    def test_prints_both_fits_each_followed_by_its_summary(self, capsys):
        df = _seasonal_daily_frame()
        neon_eval_utils.comparison(df, "site label", VAR, VARIABLES_UNITS)
        captured = capsys.readouterr()

        lines = captured.out.splitlines()
        clm_index = next(i for i, line in enumerate(lines) if line.startswith("CLM fit:"))
        kf_index = next(i for i, line in enumerate(lines) if line.startswith("KF_CLM fit:"))
        # the summary line for each fit is printed on the very next line
        assert lines[clm_index + 1].strip().startswith("CLM ")
        assert lines[kf_index + 1].strip().startswith("KF_CLM ")

    def test_printed_metrics_match_evaluate_fit(self, capsys):
        """Pins the behaviour change: comparison() must score with evaluate_fit
        (bias-type metrics on monthly means, plus seasonal/interannual scores),
        not the old compute_fit (plain magnitude metrics on raw rows).
        """
        df = _seasonal_daily_frame()
        expected_sim = evaluate_fit(df, VAR, f"sim_{VAR}")
        expected_cali = evaluate_fit(df, VAR, f"cali_sim_{VAR}")

        neon_eval_utils.comparison(df, "site label", VAR, VARIABLES_UNITS)
        captured = capsys.readouterr()

        assert f"CLM fit: {expected_sim}" in captured.out
        assert f"KF_CLM fit: {expected_cali}" in captured.out
        assert summarize_fit(expected_sim, "CLM") in captured.out
        assert summarize_fit(expected_cali, "KF_CLM") in captured.out

    def test_calibrated_model_scores_better_than_raw(self, capsys):
        """Item 3: the calibrated series is built to score better, and does."""
        df = _seasonal_daily_frame()
        expected_sim = evaluate_fit(df, VAR, f"sim_{VAR}")
        expected_cali = evaluate_fit(df, VAR, f"cali_sim_{VAR}")
        assert expected_cali["RMSE"] < expected_sim["RMSE"]
        assert expected_cali["R2"] > expected_sim["R2"]

        neon_eval_utils.comparison(df, "site label", VAR, VARIABLES_UNITS)
        captured = capsys.readouterr()
        assert f"CLM fit: {expected_sim}" in captured.out
        assert f"KF_CLM fit: {expected_cali}" in captured.out


class TestSeasonalPhaseShift:
    """Item 4: a deliberate phase shift is reported and described in words."""

    def test_raw_model_reports_a_two_month_late_peak(self, capsys):
        df = _seasonal_daily_frame(peak_month_obs=7, peak_month_sim=9, peak_month_cali=7)
        expected_sim = evaluate_fit(df, VAR, f"sim_{VAR}")
        assert expected_sim["seasonal_phase_shift_months"] == pytest.approx(2.0)

        neon_eval_utils.comparison(df, "site label", VAR, VARIABLES_UNITS)
        captured = capsys.readouterr()
        assert "CLM peaks 2 month(s) late" in captured.out

    def test_calibrated_model_with_matching_phase_reports_no_shift(self, capsys):
        df = _seasonal_daily_frame(peak_month_obs=7, peak_month_sim=9, peak_month_cali=7)
        expected_cali = evaluate_fit(df, VAR, f"cali_sim_{VAR}")
        assert expected_cali["seasonal_phase_shift_months"] == pytest.approx(0.0)

        neon_eval_utils.comparison(df, "site label", VAR, VARIABLES_UNITS)
        captured = capsys.readouterr()
        assert "KF_CLM peaks in the same month as the observations" in captured.out


class TestTimeSeriesComparison:
    """Item 5 & 6: the aggregate-then-compare path, and the new ET entry."""

    def test_module_imports_pandas_it_uses(self):
        """Regression guard: time_series_comparison calls pd.to_datetime twice.

        `neon_eval_utils` lost its only `import pandas as pd` when the
        duplicated Kalman block around it was deleted, so every call raised
        NameError before `comparison` was reached, for every variable. It
        went unnoticed because neither function had a test. Assert the name
        is bound rather than only that a call succeeds, so deleting the
        import again fails here and not somewhere downstream.
        """
        assert neon_eval_utils.pd is pd

    def test_reaches_comparison_and_scores_the_aggregated_frame(self, capsys):
        """The whole path Hub 2 reaches: aggregate to daily, score, plot.

        The day-aggregation and the ET wiring are exercised end to end, and
        the expected metrics are recomputed here from an independent
        replication of the aggregation rather than read back from the
        function under test.
        """
        df = _hourly_et_frame()
        expected_daily = _replicate_time_series_aggregation(df)
        expected_sim = evaluate_fit(expected_daily, "ET", "sim_ET")
        expected_cali = evaluate_fit(expected_daily, "ET", "cali_sim_ET")

        neon_eval_utils.time_series_comparison(df, "hourly ET", "ET")
        captured = capsys.readouterr()

        # same shape of output as calling comparison() directly: both fits,
        # each with its summary, scored on the day-aggregated frame
        assert f"CLM fit: {expected_sim}" in captured.out
        assert f"KF_CLM fit: {expected_cali}" in captured.out
        assert summarize_fit(expected_sim, "CLM") in captured.out
        assert summarize_fit(expected_cali, "KF_CLM") in captured.out

        # ET's entry in variables_units_dict is what makes it plottable in the Hub
        ylabel = plt.gcf().axes[0].get_ylabel()
        assert "Evapotranspiration" in ylabel
        assert "W m$^{-2}$" in ylabel


class TestComparisonUnknownVariable:
    """Item 7: a variable missing from variables_units, pinned as current behaviour."""

    def test_missing_variable_raises_key_error(self):
        """Documents current behaviour, not necessarily the desired one.

        `comparison()` indexes `variables_units[var]` with no membership
        check and no helpful message, so a variable absent from the table
        raises a plain KeyError. A future change that validates `var` and
        raises something friendlier would be deliberate, not accidental --
        that is what this test guards against.
        """
        df = _seasonal_daily_frame()
        variables_units = {"SOME_OTHER_VAR": {"units": "x", "var_name": "y"}}
        with pytest.raises(KeyError):
            neon_eval_utils.comparison(df, "label", VAR, variables_units)
