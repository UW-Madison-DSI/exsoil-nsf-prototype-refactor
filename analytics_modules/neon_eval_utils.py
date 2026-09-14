# These functions should belong to from utilities import evaluate_misfit
#These functions should belong to from utilities import evaluate_misfit

from typing import Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import xarray as xr

#

"""
This code is to evaluate misfit of the CTSM model simulations against observations of data
"""

def residuals_plots(
    y_obs,
    y_simulations,
    bins: int = 30,
    figsize: tuple = (12, 4),
    alpha: float = 0.6,
    savepath: Optional[str] = None,
    show: bool = True,
    thresholds: Optional[dict] = None,
):
    """
    Plot residual diagnostics (histogram, Q–Q plot, residuals vs fitted) and
    produce a short text conclusion about misfit.

    Returns
    -------
    fig : matplotlib.figure.Figure
    residuals : np.ndarray
    metrics : dict
    conclusion : str
    """
    # ---- Config ----
    thr = {
        "alpha_norm": 0.05,   # normality test significance
        "bias_ratio": 0.10,   # |bias| > 10% of std(obs) => flag
        "rho_abs": 0.20,      # |Spearman rho| >= 0.2 => heteroscedasticity flag
        "rmse_ratio": 0.50,   # RMSE > 50% of std(obs) => large error
    }
    if thresholds:
        thr.update(thresholds)

    # ---- Data cleaning ----
    y_obs = np.asarray(y_obs, dtype=float)
    y_sim = np.asarray(y_simulations, dtype=float)
    mask = np.isfinite(y_obs) & np.isfinite(y_sim)
    y_obs, y_sim = y_obs[mask], y_sim[mask]
    residuals = y_obs - y_sim

    # ---- Metrics ----
    n = residuals.size
    bias = float(np.mean(residuals)) if n else np.nan
    rmse = float(np.sqrt(np.mean(residuals**2))) if n else np.nan
    mae  = float(np.mean(np.abs(residuals))) if n else np.nan
    obs_std = float(np.std(y_obs)) if n else np.nan
    bias_ratio = (abs(bias) / obs_std) if (np.isfinite(obs_std) and obs_std > 0) else np.nan

    # R and R^2 (guard tiny n)
    r = np.nan
    r2 = np.nan
    if n > 1 and np.std(y_obs) > 0 and np.std(y_sim) > 0:
        r = float(np.corrcoef(y_obs, y_sim)[0, 1])
        r2 = r**2

    # Normality of residuals (D’Agostino–Pearson)
    if n >= 8:
        _, p_norm = stats.normaltest(residuals)
    else:
        p_norm = np.nan

    # Heteroscedasticity proxy: |residuals| vs fitted (Spearman)
    if n > 2:
        rho, p_rho = stats.spearmanr(np.abs(residuals), y_sim)
    else:
        rho, p_rho = np.nan, np.nan

    metrics = {
        "n": n,
        "bias": bias,
        "bias_vs_std_obs": bias_ratio,   # unitless
        "rmse": rmse,
        "mae": mae,
        "r": r,
        "r2": r2,
        "p_norm": p_norm,                # residual normality p-value
        "rho_absres_vs_fitted": rho,     # heteroscedasticity proxy
        "p_rho": p_rho,
        "std_obs": obs_std,
    }

    # ---- Simple rule-based conclusion ----
    issues = []
    if np.isfinite(bias_ratio) and bias_ratio > thr["bias_ratio"]:
        issues.append(f"noticeable bias ({bias:.3g}, {bias_ratio:.0%} of obs std)")
    if np.isfinite(rmse) and np.isfinite(obs_std) and obs_std > 0 and (rmse > thr["rmse_ratio"] * obs_std):
        issues.append(f"RMSE large vs variability (RMSE={rmse:.3g}, std(obs)={obs_std:.3g})")
    if np.isfinite(p_norm) and p_norm < thr["alpha_norm"]:
        issues.append("residuals deviate from normality (p<0.05)")
    if np.isfinite(rho) and abs(rho) >= thr["rho_abs"]:
        issues.append(f"heteroscedasticity pattern (|ρ|={abs(rho):.2f})")

    if not issues:
        conclusion = (
            f"Good fit: residuals centered near 0 (bias={bias:.3g}), "
            f"no strong pattern vs fitted (ρ={rho:.2f}), approx. normal "
            f"(p={p_norm:.3g}); R²≈{r2:.2f}."
        )
    else:
        conclusion = (
            "Misfit notes: " + "; ".join(issues) +
            (f" R²≈{r2:.2f}, MAE={mae:.3g}" if np.isfinite(r2) else " inf")
        )

    # ---- Plots ----
    fig, axes = plt.subplots(1, 4, figsize=figsize)

    # 1) Histogram
    axes[0].hist(residuals, bins=bins, edgecolor="black")
    axes[0].set_title("Residuals Histogram")
    axes[0].set_xlabel("Residual")
    axes[0].set_ylabel("Count")

    # 2) Q–Q plot
    stats.probplot(residuals, dist="norm", plot=axes[1])
    axes[1].set_title("Q–Q Plot (Residuals)")

    # 3) Residuals vs Fitted
    axes[2].scatter(y_sim, residuals, alpha=alpha, s=18)
    axes[2].axhline(0, color="red", linestyle="--", linewidth=1)
    axes[2].set_title("Residuals vs Fitted")
    axes[2].set_xlabel("Fitted (Simulated)")
    axes[2].set_ylabel("Residual (Obs − Sim)")
    
    # 4) Obs vs Fitted
    axes[3].scatter(y_obs, y_sim, alpha=alpha, s=18)
    axes[3].axhline(0, color="red", linestyle="--", linewidth=1)
    axes[3].set_title("Observed vs Fitted")
    axes[3].set_ylabel("Fitted (Simulated)")
    axes[3].set_xlabel("Observed")

    # Summary line on top
    fig.suptitle(conclusion, fontsize=10, y=1.03)
    fig.tight_layout()

    if savepath:
        fig.savefig(savepath, dpi=160, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, residuals, metrics, conclusion


# The filter lives in kalman_filter.py. It used to be duplicated here, and the two
# copies drifted (issue #29). Re-exported so `from .neon_eval_utils import ...`
# and `from analytics_modules import ...` keep working.
from .kalman_filter import (  # noqa: E402,F401
    DegenerateCalibrationError,
    DegenerateCalibrationWarning,
    kalman_gain_bias,
)
from .fit_metrics import evaluate_fit, magnitude_metrics, summarize_fit  # noqa: E402


# ---------- Orchestrator ----------
def calibrate_and_evaluate(df, col, method="auto", hour_col=None):
    """Run the Kalman calibration on `col` against `sim_col` and score before and after.

    The post-calibration metrics are computed on the **one-step-ahead
    prediction** -- the calibrated model at each step using only earlier
    observations -- which is the honest measure of what the filter adds. The
    posterior fit, which has already seen each observation it is compared
    with, is returned as `cali_sim_{col}_posterior` and scored under
    `posterior_metrics`, labelled in-sample (issue #34).

    Columns added to the returned frame:
        cali_sim_{col}            one-step-ahead calibrated model (score this)
        cal_lo, cal_hi            95% predictive interval around it
        cali_sim_{col}_posterior  in-sample posterior fit (for plotting only)
        cal_smooth                RTS-smoothed fit, two-sided, also in-sample
    """
    d = df.dropna(subset=[col, "sim_" + col]).copy()
    y_obs = d[col].to_numpy(float)
    y_sim = d["sim_" + col].to_numpy(float)
    hours = d[hour_col].to_numpy(int) if (hour_col and hour_col in d) else None

    print("--------------------- Observations vs simulations")
    fig, residuals, metrics_pre, conclusion_pre = residuals_plots(
        y_obs,
        y_sim,
        bins=40,
        savepath=None,
    )
    print(conclusion_pre)
    print(metrics_pre)

    print("--------------------- Observations vs KF calibration (one-step-ahead)")
    y_cal, (lo, hi), y_smooth, info = kalman_gain_bias(y_obs, y_sim, hours=hours)
    if info["degenerate"]:
        # A near-zero gain means the bias term reproduced the observations on
        # its own. The post-calibration metrics would report a near-perfect fit
        # that says nothing about the model, so refuse rather than print them.
        raise DegenerateCalibrationError(
            f"Kalman calibration of {col!r} is degenerate (standardised gain "
            f"{info['gain_standardised']:.3g}, bias absorption {info['bias_absorption']:.3f}); "
            "the filter ignored the model. Check that observations and simulations "
            "are in the same units, and see issue #29."
        )
    y_pred = info["y_pred"]
    pred_half_width = 1.96 * np.sqrt(np.maximum(info["S"], 0.0))
    d["cali_sim_" + col] = y_pred
    d["cal_lo"], d["cal_hi"] = y_pred - pred_half_width, y_pred + pred_half_width
    d["cali_sim_" + col + "_posterior"] = y_cal
    if y_smooth is not None:
        d["cal_smooth"] = y_smooth
    pars = {"kf": "bias+gain" + ("+harmonics" if hours is not None else "")}

    fig, residuals, metrics_post, conclusion_post = residuals_plots(
        y_obs,
        y_pred,
        bins=40,
        savepath=None,
    )
    print(conclusion_post)
    print(metrics_post)

    # The posterior fit is reported for reference only. It is in-sample, so it
    # will always look at least as good as the prediction and usually better.
    fig_post, _, metrics_posterior, _ = residuals_plots(
        y_obs, y_cal, bins=40, savepath=None, show=False,
    )
    plt.close(fig_post)
    print("--------------------- Posterior fit (in-sample, for reference only)")
    print(metrics_posterior)

    return d, {
        "pre_metrics": metrics_pre,
        "post_metrics": metrics_post,
        "posterior_metrics": metrics_posterior,
        "method": method,
        "params": pars,
    }


######################## time series comparison

def compute_fit(df, obs, sim):
    """R2, RMSE, MAE and Bias of column `sim` against column `obs`, over rows where both are present.

    A thin wrapper over fit_metrics.magnitude_metrics, so there is one
    definition of these four numbers. For the seasonal-cycle and interannual
    scores that say *how* the model misses, use evaluate_fit (issue #18).
    """
    mask = df[obs].notna() & df[sim].notna()
    return magnitude_metrics(df.loc[mask, obs].to_numpy(float), df.loc[mask, sim].to_numpy(float))


def comparison(df, label, var, variables_units):
    #Comparison at the time series level of aggregation
    
    plot_var = var
    sim_var  = f"sim_{plot_var}"
    calib_sim_var  = f"cali_sim_{plot_var}"

    plot_var_desc = variables_units[plot_var]['var_name']
    plot_var_unit = variables_units[plot_var]['units']

    # ensure time is datetime & sorted (optional but helpful)
    df_daily = df.copy()
    df_daily = df_daily.sort_values("time")

    fig, ax = plt.subplots(figsize=(13, 5))

    # Plot with pandas but turn OFF legend to avoid the bug
    df_daily.plot(x="time", y=plot_var,   marker="o", ax=ax, color="b", legend=False)
    df_daily.plot(x="time", y=sim_var,    marker="o", ax=ax, color="r", legend=False)
    df_daily.plot(x="time", y=calib_sim_var,    marker="o", ax=ax, color="g", legend=False)
    
    # evaluate_fit scores bias-type metrics on monthly means (decision 005)
    # and adds the seasonal-cycle and interannual scores (issue #18).
    fit_sim = evaluate_fit(df_daily, var, "sim_" + var)
    fit_cali = evaluate_fit(df_daily, var, "cali_sim_" + var)

    print("CLM fit:", fit_sim)
    print("   ", summarize_fit(fit_sim, "CLM"))
    print("KF_CLM fit:", fit_cali)
    print("   ", summarize_fit(fit_cali, "KF_CLM"))

    ax.set_xlabel("Time", fontsize=14)
    ax.set_ylabel(f"{plot_var_desc} [{plot_var_unit}]", fontsize=14)
    ax.legend(["NEON", "CLM", "KF_CLM"], fontsize=12)   # normal Matplotlib legend
    ax.text(0.01, 0.95,
        f"CLM R²={fit_sim['R2']:.2f}, RMSE={fit_sim['RMSE']:.2f}\n"
        f"KF_CLM R²={fit_cali['R2']:.2f}, RMSE={fit_cali['RMSE']:.2f}",
        transform=ax.transAxes, fontsize=12,
        verticalalignment="top", bbox=dict(boxstyle="round", facecolor="white", alpha=0.6))

    ax.set_title(f"{label}", fontweight="bold", fontsize=16)

    plt.tight_layout()
    plt.show()
    
#-- extract year, month, day, hour information from time
def time_series_comparison(df, label, var):
    '''
        Simply giving formatting to the data and call comparisons function
    '''
    
    variables_units_dict = {
        'EFLX_LH_TOT': {
            'units':"W m$^{-2}$",
            'var_name': "Latent Heat Flux"
            },
        'GPP': {
            'units':"",
            'var_name': "GPP"
            },
        'H2OSOI': {
            'units':"",
            'var_name': "H2OSOI"
            },
        'ET': {
            'units':"W m$^{-2}$",
            'var_name': "Evapotranspiration (latent heat, FCTR + FCEV + FGEV)"
            }
        }
    
    df_cal = df.copy()
    df_cal['year'] = df_cal['time'].dt.year
    df_cal['month'] = df_cal['time'].dt.month
    df_cal['day'] = df_cal['time'].dt.day
    df_cal['hour'] = df_cal['time'].dt.hour
    
    df_daily = df_cal.groupby(['year','month','day']).mean().reset_index()
    df_daily['time']=pd.to_datetime(df_daily[["year", "month", "day"]])
    df_daily["time"] = pd.to_datetime(df_daily["time"])
    comparison(
        df_daily,
        label=label,
        var=var,
        variables_units=variables_units_dict
    )    


################# utilities to give formatting to data and subseting to specific depth for H2OSOI

def ctsm_sim_depth(sim_files, var, levsoi=2.5):
    """
    Extract CTSM simulation data for the closest available soil depth level.
    
    Parameters:
    -----------
    sim_files : list or str
        Path(s) to CTSM simulation files
    var : str
        Variable name to extract
    levsoi : float
        Target soil depth level (will find closest available), only .5 increments from 0 to 6m
    
    Returns:
    --------
    pandas.DataFrame
        DataFrame with data for the closest soil depth
    """
    ds_ctsm = xr.open_mfdataset(sim_files, decode_times=True, combine='by_coords')
    
    # Convert to DataFrame
    df_ctsm_handle = ds_ctsm[var].to_dataframe().reset_index()
    
    # Define depth mapping based on available depths
    if levsoi > 6:
        print("Depths from 0-6m only")
        ds_ctsm.close()
        return None
    
    elif levsoi == 0:
        # Closest to surface: 0.009999999776482582
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'] <= 0.02]
    
    elif levsoi == 0.5:
        # Closest: 0.5799999833106995
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(0.57, 0.59)]
    
    elif levsoi == 1:
        # Closest: 1.059999942779541
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(1.05, 1.07)]
        
    elif levsoi == 1.5:
        # Closest: 1.3600000143051147
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(1.35, 1.37)]
        
    elif levsoi == 2:
        # Closest: 2.0799999237060547
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(2.07, 2.09)]
    
    elif levsoi == 2.5:
        # Exact match: 2.5
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'] == 2.5]
    
    elif levsoi in [3, 3.5]:
        # Closest: 3.5799999237060547
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(3.57, 3.59)]
    
    elif levsoi in [4, 4.5]:
        # Closest: 4.269999980926514
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(4.26, 4.28)]
        
    elif levsoi == 5:
        # Closest: 5.059999942779541
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(5.05, 5.07)]
    
    elif levsoi == 5.5:
        # Closest: 5.949999809265137
        df_ctsm_handle = df_ctsm_handle[df_ctsm_handle['levsoi'].between(5.94, 5.96)]
    
    else:
        # If no predefined range, find the closest automatically
        available_depths = df_ctsm_handle['levsoi'].unique()
        closest_depth = available_depths[np.argmin(np.abs(available_depths - levsoi))]
        print(f"Using closest available depth: {closest_depth}m for requested {levsoi}m")
        df_ctsm_handle = df_ctsm_handle[
            np.abs(df_ctsm_handle['levsoi'] - closest_depth) < 0.001
        ]
    
    # Close the dataset to free memory
    ds_ctsm.close()
    
    return df_ctsm_handle