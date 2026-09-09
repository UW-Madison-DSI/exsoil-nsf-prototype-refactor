"""Tier 0 tests for the seasonal-cycle and interannual-variability scores (issue #18).

Everything is synthetic and constructed so the right answer is known before
the code runs: a series shifted by two months must report a two-month phase
shift; anomalies scaled by half must report a ratio of one half. The scores
are only useful if they attribute a misfit correctly, so the assertions are
on values, not on "it returned a number".
"""

import math

import numpy as np
import pandas as pd
import pytest

from analytics_modules.fit_metrics import (
    evaluate_fit,
    evaluate_pairs,
    evaluate_series,
    infer_resolution,
    magnitude_metrics,
    summarize_fit,
)
from analytics_modules.neon_eval_utils import compute_fit

pytestmark = pytest.mark.tier0


def monthly_index(years: int, start: str = "2018-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=12 * years, freq="MS")


def seasonal(index: pd.DatetimeIndex, peak_month: int = 7, amplitude: float = 1.0,
             year_anomaly=None) -> pd.Series:
    """A clean annual cycle peaking in `peak_month`, optionally with per-year offsets."""
    phase = 2 * np.pi * (index.month - peak_month) / 12
    values = 5.0 + amplitude * np.cos(phase)
    if year_anomaly is not None:
        values = values + np.array([year_anomaly[y] for y in index.year])
    return pd.Series(values, index=index)


class TestSeasonalCycle:
    def test_identical_series_score_perfectly(self):
        idx = monthly_index(4)
        obs = seasonal(idx)
        m = evaluate_series(obs, obs.copy())
        assert m["seasonal_phase_shift_months"] == 0
        assert m["seasonal_amplitude_ratio"] == pytest.approx(1.0)
        assert m["seasonal_score"] == pytest.approx(1.0)
        assert m["seasonal_climatology_r"] == pytest.approx(1.0)

    def test_two_month_late_peak_is_reported_as_plus_two(self):
        idx = monthly_index(4)
        obs = seasonal(idx, peak_month=7)
        sim = seasonal(idx, peak_month=9)
        m = evaluate_series(obs, sim)
        assert m["seasonal_phase_shift_months"] == 2
        assert m["seasonal_score"] == pytest.approx(0.5 * (1 + math.cos(2 * math.pi * 2 / 12)))

    def test_early_peak_is_negative_and_wraps_around_the_year(self):
        idx = monthly_index(4)
        obs = seasonal(idx, peak_month=1)
        sim = seasonal(idx, peak_month=12)
        assert evaluate_series(obs, sim)["seasonal_phase_shift_months"] == -1

    def test_amplitude_ratio_is_model_swing_over_observed_swing(self):
        idx = monthly_index(4)
        obs = seasonal(idx, amplitude=1.0)
        sim = seasonal(idx, amplitude=2.0)
        m = evaluate_series(obs, sim)
        assert m["seasonal_amplitude_ratio"] == pytest.approx(2.0)
        # a pure amplitude error leaves the phase alone: that is the attribution
        assert m["seasonal_phase_shift_months"] == 0


class TestInterannualVariability:
    def test_same_good_and_bad_years_at_half_strength(self):
        idx = monthly_index(5)
        years = sorted(set(idx.year))
        obs_anom = dict(zip(years, [1.0, -1.0, 0.5, -0.5, 0.0]))
        sim_anom = {y: 0.5 * a for y, a in obs_anom.items()}
        obs = seasonal(idx, year_anomaly=obs_anom)
        sim = seasonal(idx, year_anomaly=sim_anom)
        m = evaluate_series(obs, sim)
        assert m["iav_std_ratio"] == pytest.approx(0.5)
        assert m["iav_anomaly_r"] == pytest.approx(1.0)
        assert m["iav_score"] == pytest.approx(math.exp(-0.5))
        # and the seasonal scores are untouched by the anomalies
        assert m["seasonal_phase_shift_months"] == 0
        assert m["seasonal_amplitude_ratio"] == pytest.approx(1.0)

    def test_flattened_years_are_distinguishable_from_a_wrong_average_year(self):
        idx = monthly_index(5)
        years = sorted(set(idx.year))
        obs = seasonal(idx, year_anomaly=dict(zip(years, [1.0, -1.0, 0.5, -0.5, 0.0])))
        flat = seasonal(idx)                    # right average year, no variability
        shifted = seasonal(idx, peak_month=9, year_anomaly=dict(zip(years, [1.0, -1.0, 0.5, -0.5, 0.0])))
        m_flat, m_shift = evaluate_series(obs, flat), evaluate_series(obs, shifted)
        assert m_flat["iav_std_ratio"] == pytest.approx(0.0)
        assert m_flat["seasonal_phase_shift_months"] == 0
        assert m_shift["iav_std_ratio"] == pytest.approx(1.0)
        assert m_shift["seasonal_phase_shift_months"] == 2

    def test_short_record_is_flagged_not_hidden(self):
        short = seasonal(monthly_index(3))
        long = seasonal(monthly_index(5))
        assert evaluate_series(short, short)["short_record"] is True
        assert evaluate_series(short, short)["n_years"] == 3
        assert evaluate_series(long, long)["short_record"] is False

    def test_neon_window_is_a_short_record(self):
        """45 months, 2018-01 to 2021-09: four calendar years touched, so not flagged,
        but the last is partial. The flag is about years, the caller reads n."""
        idx = pd.date_range("2018-01-01", periods=45, freq="MS")
        m = evaluate_series(seasonal(idx), seasonal(idx))
        assert m["n"] == 45
        assert m["n_years"] == 4
        assert m["short_record"] is False


class TestResolution:
    def test_infers_cadence(self):
        assert infer_resolution(pd.date_range("2018-01-01", periods=10, freq="30min")) == "sub-daily"
        assert infer_resolution(pd.date_range("2018-01-01", periods=10, freq="D")) == "daily"
        assert infer_resolution(pd.date_range("2018-01-01", periods=10, freq="MS")) == "monthly"

    def test_daily_input_scores_magnitude_on_monthly_means(self):
        """Correlation at native resolution; Bias/RMSE/MAE on monthly means."""
        idx = pd.date_range("2018-01-01", "2021-12-31", freq="D")
        rng = np.random.default_rng(0)
        obs = pd.Series(5 + np.cos(2 * np.pi * (idx.dayofyear - 200) / 365) + rng.normal(0, 0.5, len(idx)), index=idx)
        sim = obs + 0.3 + rng.normal(0, 0.5, len(idx))
        m = evaluate_series(obs, sim)
        assert m["resolution"] == "daily"
        obs_m, sim_m = obs.resample("MS").mean(), sim.resample("MS").mean()
        expected = magnitude_metrics(obs_m.to_numpy(), sim_m.to_numpy())
        assert m["RMSE"] == pytest.approx(expected["RMSE"])
        assert m["Bias"] == pytest.approx(expected["Bias"])
        # correlation is on the daily pairs, not the monthly means
        assert m["r"] == pytest.approx(float(np.corrcoef(obs, sim)[0, 1]))
        assert m["n"] == len(idx)

    def test_period_index_is_accepted(self):
        idx = monthly_index(4)
        obs = seasonal(idx)
        obs_period = obs.copy()
        obs_period.index = obs_period.index.to_period("M")
        assert evaluate_series(obs_period, obs_period)["n"] == 48


class TestVariableAgnostic:
    def test_negative_values_pass_through_unaltered(self):
        """Nothing here may clamp or drop negatives: decision 005 reports, not hides."""
        idx = monthly_index(4)
        obs = seasonal(idx) - 5.5          # dips below zero every winter
        sim = obs * 1.1
        m = evaluate_series(obs, sim)
        assert m["n"] == 48
        assert m["Bias"] == pytest.approx(float((sim - obs).mean()))

    def test_unaligned_indexes_score_only_shared_timestamps(self):
        idx = monthly_index(4)
        obs = seasonal(idx)
        sim = seasonal(idx)[6:]            # model starts six months late
        assert evaluate_series(obs, sim)["n"] == 42

    def test_magnitude_keys_match_compute_fit_on_monthly_input(self):
        idx = monthly_index(4)
        rng = np.random.default_rng(1)
        frame = pd.DataFrame({"time": idx, "GPP": seasonal(idx).to_numpy(),
                              "sim_GPP": seasonal(idx, amplitude=1.3).to_numpy() + rng.normal(0, 0.1, 48)})
        old = compute_fit(frame, "GPP", "sim_GPP")
        new = evaluate_fit(frame, "GPP", "sim_GPP")
        for key in ("R2", "RMSE", "MAE", "Bias"):
            assert new[key] == pytest.approx(old[key], rel=1e-9), key


class TestComponentInterface:
    def test_evaluate_pairs_gives_one_row_per_component(self):
        idx = monthly_index(4)
        frame = pd.DataFrame({"time": idx})
        for name, amp in (("FCTR", 1.0), ("FCEV", 0.5), ("FGEV", 0.3)):
            frame[f"{name}_obs"] = seasonal(idx, amplitude=amp).to_numpy()
            frame[name] = seasonal(idx, amplitude=2 * amp).to_numpy()
        table = evaluate_pairs(frame, {"FCTR_obs": "FCTR", "FCEV_obs": "FCEV", "FGEV_obs": "FGEV"})
        assert list(table.index) == ["FCTR_obs", "FCEV_obs", "FGEV_obs"]
        np.testing.assert_allclose(table["seasonal_amplitude_ratio"].to_numpy(), 2.0)
        assert set(table.columns) >= {"R2", "RMSE", "MAE", "Bias", "seasonal_score", "iav_score"}


class TestSummary:
    def test_summary_says_late_and_by_how_much(self):
        idx = monthly_index(5)
        m = evaluate_series(seasonal(idx, peak_month=7), seasonal(idx, peak_month=9, amplitude=2.0))
        text = summarize_fit(m, "GPP")
        assert "2 month(s) late" in text
        assert "2.00x" in text
        assert "indicative" not in text

    def test_summary_warns_on_short_record(self):
        idx = monthly_index(2)
        text = summarize_fit(evaluate_series(seasonal(idx), seasonal(idx)))
        assert "indicative at best" in text
