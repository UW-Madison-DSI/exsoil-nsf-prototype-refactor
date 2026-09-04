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


def kalman_filter(df, var):
    """Simple scalar Kalman filter merging model predictions with observations."""

    df_clean = df.dropna(subset=[var, 'sim_' + var])

    sim = df_clean[var]
    obs = df_clean['sim_' + var]
    x_est = sim.iloc[0]
    P = 1.0
    Q = 1e-3
    R = 0.1 * np.var(obs - sim)

    kalman_estimates = []

    for i in range(len(obs)):
        z = obs.iloc[i]
        x_pred = sim.iloc[i]

        P_pred = P + Q
        K = P_pred / (P_pred + R)
        x_est = x_pred + K * (z - x_pred)
        P = (1 - K) * P_pred

        kalman_estimates.append(x_est)

    kalman_estimates = np.array(kalman_estimates)
    bias = np.mean(kalman_estimates - obs)
    kalman_corrected = kalman_estimates - bias

    df_clean["kalman_" + var] = kalman_estimates
    df_clean["kalman_" + var + "_bias_corrected"] = kalman_corrected

    return df_clean


def kalman_gain_bias(
    y_obs,
    y_sim,
    hours=None,
    Q_diag=(1e-4, 1e-4, 1e-6, 1e-6),
    R0_scale=0.1,
    smooth=True,
    scale: float | None = None,
    gain_floor: float = 0.05,
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

    A learned gain whose median magnitude is below ``gain_floor`` means the
    filter is ignoring the model. That is reported as ``info["degenerate"]``
    and a ``DegenerateCalibrationWarning``, never as a good fit.

    Returns ``y_cal, (lo, hi), y_smooth, info`` where ``info`` carries
    ``theta_seq``, ``innov``, ``S``, ``scale``, ``gain_median``, ``gain_final``
    and ``degenerate``.
    """
    y_obs, y_sim = np.asarray(y_obs, float), np.asarray(y_sim, float)
    m = np.isfinite(y_obs) & np.isfinite(y_sim)
    y, s = y_obs[m], y_sim[m]
    n = len(y)

    if scale is None:
        scale = float(np.std(y)) if n else 1.0
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

    theta = np.zeros(dim)
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
    degenerate = bool(n) and abs(gain_median) < gain_floor
    if degenerate:
        warnings.warn(
            f"Kalman calibration is degenerate: median learned gain {gain_median:.3g} "
            f"is below {gain_floor}. The filter is ignoring the model and reproducing "
            "the observations through the bias term, so any post-calibration fit "
            "statistic is meaningless.",
            DegenerateCalibrationWarning,
            stacklevel=2,
        )

    info = {
        "theta_seq": theta_out,
        "innov": innov * scale,
        "S": S_hist * scale ** 2,
        "scale": scale,
        "gain_median": gain_median,
        "gain_final": gain_final,
        "degenerate": degenerate,
    }
    return y_cal * scale, (lo * scale, hi * scale), y_smooth, info
