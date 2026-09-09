"""
Kalman filter calibration for CTSM simulation outputs.

This is the single home of the filter. ``neon_eval_utils`` re-exports these
names so both import paths resolve to the same function; a second copy used
to live there and the two drifted (issue #29).
"""
from __future__ import annotations

import warnings

import numpy as np


class DegenerateCalibrationWarning(UserWarning):
    """The filter learned to ignore the model and reproduce the observations."""


class DegenerateCalibrationError(ValueError):
    """Raised by orchestrators when a calibration is degenerate and its metrics would mislead."""


def kalman_gain_bias(
    y_obs,
    y_sim,
    hours=None,
    Q_diag=(1e-4, 1e-4, 1e-6, 1e-6),
    R0_scale=0.1,
    smooth=True,
    scale: float | None = None,
    gain_floor: float = 0.05,
    absorption_ceiling: float = 0.95,
):
    """
    Linear state-space with predictor vector h_t = [1, sim_t, sin(wt), cos(wt)] (last two optional).
        state theta_t = [bias_t, gain_t, s_t, c_t]';  theta_t = theta_{t-1} + w_t,  w~N(0,Q)
        obs   y_t = h_t . theta_t + v_t,              v~N(0,R_t)
    If hours is None -> model uses [1, sim_t] only.

    The filter runs on both series divided by a common ``scale`` (default: the
    standard deviation of the finite observations). ``Q_diag`` and the initial
    state covariance are therefore relative to the size of the signal, and the
    result does not depend on whether GPP arrives in gC m-2 s-1 or umol m-2 s-1.
    Without this, the default process noise is ~73,000x the variance of
    model-unit GPP, the bias term absorbs the observations outright, and the
    filter returns R^2 = 1.0 with a dead gain (issue #29). Pass ``scale=1.0``
    to run on raw units.

    The gain is dimensionless, so it is unaffected by the scaling; bias, the
    harmonic amplitudes, the calibrated series and its interval are scaled
    back before they are returned.

    A filter that is ignoring the model is reported as ``info["degenerate"]``
    and a ``DegenerateCalibrationWarning``, never as a good fit. Two tests,
    either of which flags it:

    - The *standardised* gain, the median learned gain times
      ``std(sim) / std(obs)``, is below ``gain_floor``. That is the fraction
      of the observed variability reaching the output through the model
      path. A raw gain of 0.03 is legitimate when the model's amplitude is
      30x the observations', so the raw gain is not what is compared.
    - The *bias absorption*, ``1 - SS(y - y_cal) / SS(y - y_pred)``, exceeds
      ``absorption_ceiling``. When the process noise is far larger than the
      signal, the bias random walk jumps to each observation as it arrives:
      the posterior reproduces the data exactly while the one-step-ahead
      prediction learns nothing. That is the #29 failure, and it is what
      the posterior R^2 of 1.0 was measuring. With a well-scaled Q the
      posterior absorbs a modest share of the prediction residual, not
      nearly all of it.

    Three calibrated series come back, and they are not interchangeable:

    - ``info["y_pred"]`` is the **one-step-ahead prediction**,
      ``H[t] . theta_{t-1}``: the calibrated model at ``t`` using only
      observations before ``t``. This is the series to score against the
      observations. The first value uses the prior, which starts from the
      uncorrected model (bias 0, gain 1), so ``y_pred[0] == y_sim[0]``.
    - ``y_cal`` is the **posterior fit**, ``H[t] . theta_t``, which has already
      assimilated ``y[t]``. It is in-sample: scoring it against the
      observations overstates the fit, because each value has seen the
      answer (issue #34).
    - ``y_smooth`` is the RTS-smoothed fit, two-sided and therefore also
      in-sample.

    Returns ``y_cal, (lo, hi), y_smooth, info`` where ``info`` carries
    ``y_pred``, ``theta_seq``, ``innov``, ``S`` (the one-step-ahead predictive
    variance, in y units squared), ``scale``, ``gain_median``,
    ``gain_standardised``, ``gain_final``, ``bias_absorption`` and
    ``degenerate``.
    """
    y_obs, y_sim = np.asarray(y_obs, float), np.asarray(y_sim, float)
    m = np.isfinite(y_obs) & np.isfinite(y_sim)
    y, s = y_obs[m], y_sim[m]
    n = len(y)

    obs_std = float(np.std(y)) if n else 0.0
    sim_std = float(np.std(s)) if n else 0.0
    if scale is None:
        # Observations first; if they are constant, the model's spread is the
        # only signal left. Falling straight back to 1.0 would re-enter the
        # raw-unit regime this normalisation exists to avoid.
        scale = obs_std if obs_std > 0 else sim_std
    scale = float(scale)
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    y = y / scale
    s = s / scale

    use_harm = hours is not None
    if use_harm:
        h = (np.asarray(hours, int) % 24)[m]
        w = 2 * np.pi / 24.0
        H = np.column_stack([np.ones(n), s, np.sin(w * h), np.cos(w * h)])
        Q = np.diag([Q_diag[0], Q_diag[1], Q_diag[2], Q_diag[3]])
    else:
        H = np.column_stack([np.ones(n), s])
        Q = np.diag([Q_diag[0], Q_diag[1]])
    dim = H.shape[1]

    # Prior: the uncorrected model. Bias 0, gain 1, no harmonic correction.
    # A zero prior would make the first one-step-ahead prediction 0, an
    # artefact that would have to be discarded before scoring.
    theta = np.zeros(dim)
    theta[1] = 1.0
    P = np.eye(dim)
    R = R0_scale * np.var(y - s) if np.isfinite(np.var(y - s)) else 1.0
    R = max(R, 1e-8)

    theta_f = np.zeros((n, dim))
    P_f = np.zeros((n, dim))
    K_hist = np.zeros(n)
    innov = np.zeros(n)
    S_hist = np.zeros(n)

    for t in range(n):
        theta_pred = theta
        P_pred = P + Q
        ht = H[t]
        v = y[t] - ht @ theta_pred
        S = float(ht @ P_pred @ ht + R)
        K = (P_pred @ ht) / S
        theta = theta_pred + K * v
        P = (np.eye(dim) - np.outer(K, ht)) @ P_pred

        theta_f[t] = theta
        P_f[t] = np.diag(P)
        K_hist[t] = K[1] if dim > 1 else K[0]
        innov[t] = v
        S_hist[t] = S

        R_est = max(v * v - float(ht @ P_pred @ ht), 1e-10)
        R = 0.95 * R + 0.05 * R_est

    y_cal = np.sum(H * theta_f, axis=1)
    # innov = y - H . theta_pred, so the one-step-ahead prediction falls out
    y_pred = y - innov
    half_width = 1.96 * np.sqrt(np.maximum(np.sum((H ** 2) * P_f, axis=1), 1e-12))
    lo = y_cal - half_width
    hi = y_cal + half_width

    if smooth:
        theta_s = theta_f.copy()
        Pd = np.diag(Q)
        for t in range(n - 2, -1, -1):
            P_pred_next = np.diag(P_f[t] + Pd)
            J = np.diag(P_f[t]) @ np.linalg.pinv(P_pred_next)
            theta_s[t] = theta_f[t] + (J @ (theta_s[t + 1] - theta_f[t + 1]))
        y_smooth = np.sum(H * theta_s, axis=1) * scale
    else:
        y_smooth = None

    # Back to the caller's units. Column 1 of theta is the gain, which is
    # dimensionless; every other state component multiplies a predictor of
    # order one and so carries the units of y.
    theta_out = theta_f * scale
    theta_out[:, 1] = theta_f[:, 1]

    gain = theta_f[:, 1]
    gain_median = float(np.median(gain)) if n else np.nan
    gain_final = float(gain[-1]) if n else np.nan
    # Constant observations or a constant model leave nothing for the model
    # path to explain, so both count as zero explained variability.
    gain_standardised = gain_median * sim_std / obs_std if obs_std > 0 else 0.0

    ss_pred = float(np.sum((y - y_pred) ** 2))
    ss_post = float(np.sum((y - y_cal) ** 2))
    bias_absorption = 1.0 - ss_post / ss_pred if ss_pred > 0 else 0.0

    reasons = []
    if bool(n) and abs(gain_standardised) < gain_floor:
        reasons.append(
            f"standardised gain {gain_standardised:.3g} (median learned gain "
            f"{gain_median:.3g} x std(sim)/std(obs)) is below {gain_floor}"
        )
    if bool(n) and bias_absorption > absorption_ceiling:
        reasons.append(
            f"the posterior absorbs {bias_absorption:.4f} of the one-step-ahead "
            f"residual, above {absorption_ceiling}"
        )
    degenerate = bool(reasons)
    if degenerate:
        warnings.warn(
            "Kalman calibration is degenerate: " + "; ".join(reasons) + ". The "
            "filter is ignoring the model and reproducing the observations "
            "through the bias term, so any post-calibration fit statistic is "
            "meaningless.",
            DegenerateCalibrationWarning,
            stacklevel=2,
        )

    info = {
        "y_pred": y_pred * scale,
        "theta_seq": theta_out,
        "innov": innov * scale,
        "S": S_hist * scale ** 2,
        "scale": scale,
        "gain_median": gain_median,
        "gain_standardised": gain_standardised,
        "gain_final": gain_final,
        "bias_absorption": bias_absorption,
        "degenerate": degenerate,
    }
    return y_cal * scale, (lo * scale, hi * scale), y_smooth, info
