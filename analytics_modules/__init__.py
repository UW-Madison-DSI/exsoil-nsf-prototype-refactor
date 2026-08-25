"""Public API for analytics_modules.

Re-exports the most commonly used functions so notebooks can do
`from analytics_modules import ctsm_sim_depth, residuals_plots, ...`
without needing to know which submodule defines what.

For names that appear in both kalman_filter.py and neon_eval_utils.py,
the neon_eval_utils version wins (the project-canonical implementation).

Each submodule is imported defensively so a missing function in one
optional module doesn't break notebooks that only use a different one.
"""

# CTSM data prep & evaluation utilities (core — required)
from .neon_eval_utils import (
    ctsm_sim_depth,
    compute_fit,
    comparison,
    time_series_comparison,
    residuals_plots,
    calibrate_and_evaluate,
    kalman_filter,
    kalman_gain_bias,
)

# S3 + visualization (core — required)
from .data_access import (
    get_s3_client,
    get_storage_options,
    test_s3_connection,
    list_keys,
    list_objects_under_prefix,
    download_keys,
    open_ctsm_hist_from_s3,
    plot_soil_profile_timeseries,
    truncate_colormap,
)

# Source-agnostic CTSM history access (local by default, S3 opt-in)
from .data_access import (
    open_ctsm_hist,
    open_ctsm_hist_local,
    find_ctsm_hist_files,
    get_output_root,
    resolve_source,
)

# Notebook helpers — optional; only pulls in symbols that exist
try:
    from .neon_notebook_wrapper import download_sim_files  # noqa: F401
except ImportError:
    pass
try:
    from .neon_notebook_wrapper import list_sim_files_s3  # noqa: F401
except ImportError:
    pass

# Experiment management — optional
try:
    from .perturbation import CTSMExperimentManager  # noqa: F401
except ImportError:
    pass

# LLM helper — only available when `openai` is installed AND OPENAI_API_KEY is set
try:
    from .llm_interaction import ask_llm  # noqa: F401
except ImportError:
    pass
