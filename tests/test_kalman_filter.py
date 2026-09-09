"""Tier 0 tests for the Kalman gain/bias calibration (issue #29).

The bug this guards against was a filter that *looked* perfect: on model-unit
GPP (gC m-2 s-1, variance ~1e-9) the default process noise was ~73,000x the
signal variance, so the bias term absorbed the observations, the learned gain
sat at zero for every step, and the post-calibration R^2 came back as 1.0.
Nothing raised, nothing warned, and the number was meaningless.

Two properties pin the fix, both on synthetic series so they run everywhere:

- **Unit invariance.** The same series in gC and in umol must calibrate to
  the same gain and to calibrated values that differ only by the unit factor.
- **Degeneracy is a failure, not a result.** Running on raw units reproduces
  the old behaviour on demand (``scale=1.0``); it must be flagged and the
  orchestrator must refuse to report its metrics.

Everything here is a plain-numpy computation, so nothing is gated on staged
data or a container.
"""

import functools
import types
import warnings

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import analytics_modules  # noqa: E402
from analytics_modules import kalman_filter as kf_module  # noqa: E402
from analytics_modules import neon_eval_utils  # noqa: E402
from analytics_modules.kalman_filter import (  # noqa: E402
    DegenerateCalibrationError,
    DegenerateCalibrationWarning,
    kalman_gain_bias,
)

pytestmark = pytest.mark.tier0

UMOL_PER_GC = 1.0 / 12.011e-6  # inverse of observations.UMOL_CO2_TO_GC
N_MONTHS = 45  # the observation window, 2018-01 -> 2021-09


def monthly_gpp_in_gc(seed: int = 0):
    """A model series and an observation series in gC m-2 s-1.

    The model is a seasonal cycle of realistic magnitude (peak ~1e-4 gC m-2
    s-1, variance of order 1e-9). Observations are an affine function of the
    model plus noise, so the truth the filter should recover is a gain of
    about 0.7 and a small positive bias.
    """
    rng = np.random.default_rng(seed)
    month = np.arange(N_MONTHS)
    sim = 5e-5 * (1 + np.sin(2 * np.pi * (month - 3) / 12)) + 1e-6
    obs = 0.7 * sim + 5e-6 + rng.normal(0, 5e-6, N_MONTHS)
    return obs, sim


def r_squared(y_true, y_pred) -> float:
    return float(np.corrcoef(y_true, y_pred)[0, 1] ** 2)


class TestUnitInvariance:
    """The calibration must not depend on the unit the series arrives in."""

    def test_gain_is_identical_in_gc_and_umol(self):
        obs, sim = monthly_gpp_in_gc()
        _, _, _, info_gc = kalman_gain_bias(obs, sim)
        _, _, _, info_umol = kalman_gain_bias(obs * UMOL_PER_GC, sim * UMOL_PER_GC)
        np.testing.assert_allclose(info_gc["theta_seq"][:, 1], info_umol["theta_seq"][:, 1], rtol=1e-9)
        assert info_gc["gain_median"] == pytest.approx(info_umol["gain_median"], rel=1e-9)

    def test_calibrated_series_scales_with_the_units(self):
        obs, sim = monthly_gpp_in_gc()
        y_gc, (lo_gc, hi_gc), smooth_gc, info_gc = kalman_gain_bias(obs, sim)
        y_umol, (lo_umol, hi_umol), smooth_umol, info_umol = kalman_gain_bias(
            obs * UMOL_PER_GC, sim * UMOL_PER_GC
        )
        for a, b in [(y_gc, y_umol), (lo_gc, lo_umol), (hi_gc, hi_umol), (smooth_gc, smooth_umol)]:
            np.testing.assert_allclose(a * UMOL_PER_GC, b, rtol=1e-9)
        # bias carries the units of y; the gain does not
        np.testing.assert_allclose(info_gc["theta_seq"][:, 0] * UMOL_PER_GC, info_umol["theta_seq"][:, 0], rtol=1e-9)
        assert info_gc["scale"] * UMOL_PER_GC == pytest.approx(info_umol["scale"], rel=1e-9)


class TestModelUnitsAreNotDegenerate:
    """The exact configuration from issue #29: model-unit GPP, default arguments."""

    def test_learns_a_live_gain_and_an_imperfect_fit(self):
        obs, sim = monthly_gpp_in_gc()
        with warnings.catch_warnings():
            warnings.simplefilter("error", DegenerateCalibrationWarning)
            y_cal, _, _, info = kalman_gain_bias(obs, sim)
        assert info["degenerate"] is False
        # truth is 0.7; a filter that has not collapsed lands in this band
        assert 0.4 < info["gain_median"] < 1.0
        # better than the raw model, but not the impossible R^2 = 1.0
        assert r_squared(obs, sim) < r_squared(obs, y_cal) < 0.999

    def test_returns_are_in_the_callers_units(self):
        obs, sim = monthly_gpp_in_gc()
        y_cal, (lo, hi), y_smooth, _ = kalman_gain_bias(obs, sim)
        assert y_cal.shape == obs.shape
        # calibrated values sit in the observation range, not in normalised units
        assert 0.5 * obs.max() < np.nanmax(y_cal) < 1.5 * obs.max()
        assert y_smooth.shape == obs.shape
        # the interval is a real width in the caller's units, not a normalised one
        width = hi - lo
        assert np.all(width > 0)
        _, (lo_umol, hi_umol), _, _ = kalman_gain_bias(obs * UMOL_PER_GC, sim * UMOL_PER_GC)
        np.testing.assert_allclose((hi_umol - lo_umol), width * UMOL_PER_GC, rtol=1e-9)


class TestDegeneracyIsReportedAsFailure:
    """Reproduce the old behaviour on demand and check it is no longer silent."""

    def test_raw_units_reproduce_the_bug_and_are_flagged(self):
        obs, sim = monthly_gpp_in_gc()
        with pytest.warns(DegenerateCalibrationWarning, match="ignoring the model"):
            y_cal, _, _, info = kalman_gain_bias(obs, sim, scale=1.0)
        # this is the trap: the posterior fit is perfect because the bias
        # random walk jumped to each observation as it arrived ...
        assert r_squared(obs, y_cal) > 0.999
        assert info["bias_absorption"] > 0.95
        # ... while the prediction learned nothing it could use
        assert r_squared(obs, info["y_pred"]) < 0.999
        assert info["degenerate"] is True

    def test_gain_at_its_prior_does_not_hide_absorption(self):
        """The #29 signature was 'gain dead at zero', but that was the zero prior.

        With the filter starting from gain 1, a misconfigured Q leaves the gain
        sitting at 1 while the bias term still swallows every observation. The
        absorption test is what catches this; the gain test cannot.
        """
        obs, sim = monthly_gpp_in_gc()
        with pytest.warns(DegenerateCalibrationWarning, match="absorbs"):
            _, _, _, info = kalman_gain_bias(obs, sim, scale=1.0)
        assert abs(info["gain_standardised"]) >= 0.05  # the gain test alone would pass this
        assert info["bias_absorption"] > 0.95

    def test_well_scaled_filter_absorbs_only_part_of_the_residual(self):
        obs, sim = monthly_gpp_in_gc()
        _, _, _, info = kalman_gain_bias(obs, sim)
        assert 0.0 < info["bias_absorption"] < 0.95

    def test_mixed_units_are_flagged_not_fitted(self):
        """The Modeling_Hub cell-12 trap: observations in umol beside a model in gC.

        The learned gain collapses to the unit factor (~1e-5), which the guard
        must read as "model ignored", and the orchestrator's message must point
        at units.
        """
        obs, sim = monthly_gpp_in_gc()
        obs_umol = obs * UMOL_PER_GC
        with pytest.warns(DegenerateCalibrationWarning):
            _, _, _, info = kalman_gain_bias(obs_umol, sim)
        assert info["degenerate"] is True
        assert abs(info["gain_standardised"]) < 0.05
        frame = pd.DataFrame({"GPP": obs_umol, "sim_GPP": sim})
        with pytest.warns(DegenerateCalibrationWarning):
            with pytest.raises(DegenerateCalibrationError, match="same units"):
                neon_eval_utils.calibrate_and_evaluate(frame, "GPP")

    def test_small_true_gain_is_not_mistaken_for_degeneracy(self):
        """A model 30x too large has a legitimate gain of ~0.03.

        The raw gain sits below any sensible floor, but the model still carries
        essentially all of the observed variability, so this is a valid
        calibration and must not be refused.
        """
        rng = np.random.default_rng(2)
        _, sim = monthly_gpp_in_gc()
        obs = 0.03 * sim + 2e-6 + rng.normal(0, 1e-7, N_MONTHS)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DegenerateCalibrationWarning)
            _, _, _, info = kalman_gain_bias(obs, sim)
        assert info["degenerate"] is False
        assert 0.02 < info["gain_median"] < 0.06
        assert info["gain_standardised"] > 0.5

    def test_orchestrator_refuses_a_degenerate_calibration(self, monkeypatch):
        obs, sim = monthly_gpp_in_gc()
        frame = pd.DataFrame({"GPP": obs, "sim_GPP": sim})
        # force the degenerate path through the orchestrator's own call site
        monkeypatch.setattr(
            neon_eval_utils, "kalman_gain_bias", functools.partial(kalman_gain_bias, scale=1.0)
        )
        with pytest.warns(DegenerateCalibrationWarning):
            with pytest.raises(DegenerateCalibrationError, match="same units"):
                neon_eval_utils.calibrate_and_evaluate(frame, "GPP")

    def test_orchestrator_reports_metrics_when_calibration_is_sound(self):
        obs, sim = monthly_gpp_in_gc()
        frame = pd.DataFrame({"GPP": obs, "sim_GPP": sim})
        calibrated, summary = neon_eval_utils.calibrate_and_evaluate(frame, "GPP")
        assert "cali_sim_GPP" in calibrated
        assert summary["post_metrics"]["rmse"] < summary["pre_metrics"]["rmse"]


class TestOneStepAhead:
    """Issue #34: the fit that gets reported must not have seen the answer.

    ``y_cal`` is the posterior, which has assimilated the observation it is
    then compared with. ``info["y_pred"]`` is the one-step-ahead prediction,
    which has not. Only the second is an honest score.
    """

    def test_prediction_uses_only_earlier_observations(self):
        obs, sim = monthly_gpp_in_gc()
        _, _, _, info = kalman_gain_bias(obs, sim, smooth=False)
        theta = info["theta_seq"]
        # y_pred[t] must be H[t] . theta[t-1], reconstructed independently here
        expected = theta[:-1, 0] + theta[:-1, 1] * sim[1:]
        np.testing.assert_allclose(info["y_pred"][1:], expected, rtol=1e-9, atol=1e-18)

    def test_first_prediction_is_the_uncorrected_model(self):
        """The prior is bias 0, gain 1, so step 0 predicts the model itself."""
        obs, sim = monthly_gpp_in_gc()
        _, _, _, info = kalman_gain_bias(obs, sim)
        assert info["y_pred"][0] == pytest.approx(sim[0], rel=1e-9)

    def test_posterior_is_never_worse_than_prediction_in_sample(self):
        obs, sim = monthly_gpp_in_gc()
        y_cal, _, _, info = kalman_gain_bias(obs, sim)
        r2_posterior = r_squared(obs, y_cal)
        r2_prediction = r_squared(obs, info["y_pred"])
        # the posterior has seen the answer; it must look at least as good
        assert r2_prediction <= r2_posterior
        # and the gap is real, not rounding: this is the optimism #34 is about
        assert r2_posterior - r2_prediction > 0.01

    def test_prediction_scales_with_the_units(self):
        obs, sim = monthly_gpp_in_gc()
        _, _, _, info_gc = kalman_gain_bias(obs, sim)
        _, _, _, info_umol = kalman_gain_bias(obs * UMOL_PER_GC, sim * UMOL_PER_GC)
        np.testing.assert_allclose(info_gc["y_pred"] * UMOL_PER_GC, info_umol["y_pred"], rtol=1e-9)

    def test_orchestrator_scores_the_prediction_not_the_posterior(self):
        obs, sim = monthly_gpp_in_gc()
        frame = pd.DataFrame({"GPP": obs, "sim_GPP": sim})
        calibrated, summary = neon_eval_utils.calibrate_and_evaluate(frame, "GPP")
        _, _, _, info = kalman_gain_bias(obs, sim)
        # the column consumers plot and score is the one-step-ahead series
        np.testing.assert_allclose(calibrated["cali_sim_GPP"].to_numpy(), info["y_pred"], rtol=1e-9)
        # the reported post metric is computed on it, not on the posterior
        rmse_pred = float(np.sqrt(np.mean((obs - info["y_pred"]) ** 2)))
        assert summary["post_metrics"]["rmse"] == pytest.approx(rmse_pred, rel=1e-9)
        # the posterior is still available, but labelled as what it is
        assert "cali_sim_GPP_posterior" in calibrated
        assert summary["posterior_metrics"]["rmse"] <= summary["post_metrics"]["rmse"]
        # the predictive interval brackets the prediction, not the posterior
        assert np.all(calibrated["cal_lo"] <= calibrated["cali_sim_GPP"])
        assert np.all(calibrated["cali_sim_GPP"] <= calibrated["cal_hi"])


class TestEdgeCases:
    def test_constant_observations_scale_by_the_model_and_are_degenerate(self):
        """std(obs) = 0 must not send the filter back to raw units.

        The model's spread is the only signal left, so that becomes the scale;
        and constant observations leave nothing for the model to explain, so
        the result is degenerate by definition.
        """
        sim = np.linspace(1e-6, 1e-4, 20)
        obs = np.full(20, 2e-5)
        with pytest.warns(DegenerateCalibrationWarning):
            _, _, _, info = kalman_gain_bias(obs, sim)
        assert info["scale"] == pytest.approx(float(np.std(sim)))
        assert info["scale"] != 1.0
        assert info["degenerate"] is True

    def test_constant_model_is_degenerate(self):
        obs, _ = monthly_gpp_in_gc()
        sim = np.full(N_MONTHS, 3e-5)
        with pytest.warns(DegenerateCalibrationWarning):
            _, _, _, info = kalman_gain_bias(obs, sim)
        # std of a constant float array is ~1e-20, not exactly zero
        assert info["gain_standardised"] == pytest.approx(0.0, abs=1e-9)
        assert info["degenerate"] is True

    def test_nan_pairs_are_dropped_not_propagated(self):
        obs, sim = monthly_gpp_in_gc()
        obs[[3, 17]] = np.nan
        y_cal, _, _, info = kalman_gain_bias(obs, sim)
        assert y_cal.shape == (N_MONTHS - 2,)
        assert np.all(np.isfinite(y_cal))

    def test_harmonics_path_runs_and_scales(self):
        rng = np.random.default_rng(1)
        hours = np.arange(48 * 7) % 24 * 0.5
        sim = 2e-5 * np.clip(np.sin(2 * np.pi * (hours - 6) / 24), 0, None)
        obs = 0.8 * sim + rng.normal(0, 2e-6, sim.size)
        y_cal, _, _, info = kalman_gain_bias(obs, sim, hours=hours)
        assert info["theta_seq"].shape == (sim.size, 4)
        assert np.all(np.isfinite(y_cal))


class TestSingleImplementation:
    """Issue #29's last task: a fix must not be able to land in one copy only."""

    def test_every_import_path_is_the_same_object(self):
        assert kf_module.kalman_gain_bias is neon_eval_utils.kalman_gain_bias
        assert kf_module.kalman_gain_bias is analytics_modules.kalman_gain_bias

    def test_neon_eval_utils_no_longer_defines_its_own_copy(self):
        import inspect

        source = inspect.getsource(neon_eval_utils)
        assert "def kalman_gain_bias" not in source
        assert "def kalman_filter" not in source

    def test_submodule_is_reachable_by_its_name(self):
        """Issues #31 and #32: the scalar filter and its shadowing re-export are gone."""
        assert isinstance(analytics_modules.kalman_filter, types.ModuleType)
        assert analytics_modules.kalman_filter is kf_module
        assert not hasattr(kf_module, "kalman_filter")
        assert not hasattr(neon_eval_utils, "kalman_filter")
