"""Derived flux variables that the history streams do not carry directly.

Evapotranspiration. CLM writes total latent heat (`EFLX_LH_TOT`) and the
water-flux equivalents (`QFLX_EVAP_TOT`, `QVEGT`, `QVEGE`, `QSOIL`) on the
monthly stream only. The daily stream carries the three energy components:

    FCTR  canopy transpiration
    FCEV  canopy evaporation
    FGEV  ground evaporation

all in W m-2, and their sum is total latent heat. Jingyi's instruction
(2026-09-04, #18) is to derive ET from these three at both resolutions and to
keep the components alongside the total, because partitioned tower ET will be
supplied later and the components evaluated as well as the sum.

The derived total is left as an energy flux. Converting to a water depth
divides by the latent heat of vaporisation, which CLM replaces with the heat
of sublimation over frozen surfaces, so there is no single constant; compare
in W m-2, and if a water flux is needed check it against the monthly
`QFLX_EVAP_TOT` rather than assuming one.
"""
from __future__ import annotations

import numpy as np
import xarray as xr

ET_COMPONENTS = ("FCTR", "FCEV", "FGEV")
ET_NAME = "ET"
NATIVE_TOTAL = "EFLX_LH_TOT"
# What to request from open_ctsm_hist(variables=...) on the monthly stream so
# that derive_et and check_et_closure both have what they need. On the daily
# stream the native total does not exist and is reported missing; request
# ET_COMPONENTS there, or simply request "ET" and let the reader expand it.
ET_VARIABLES = ET_COMPONENTS + (NATIVE_TOTAL,)
# The monthly reader attaches this coordinate; its presence says "this is the
# monthly stream", which is how a missing native total is told apart from a
# daily file that never had one.
MONTHLY_MARKER = "month"


def derive_et(dataset: xr.Dataset) -> xr.Dataset:
    """Add `ET` = FCTR + FCEV + FGEV (W m-2) to a dataset, keeping the components.

    Works on either stream: the components are present on both. Raises
    KeyError if any component is missing rather than summing what is there,
    because a two-term "total" would be silently wrong.
    """
    missing = [name for name in ET_COMPONENTS if name not in dataset]
    if missing:
        raise KeyError(f"Cannot derive ET: missing latent heat component(s) {missing}")
    total = sum(dataset[name] for name in ET_COMPONENTS)
    total.attrs = {
        "units": dataset[ET_COMPONENTS[0]].attrs.get("units", "W/m^2"),
        "long_name": "total evapotranspiration as latent heat flux (FCTR + FCEV + FGEV)",
        "components": ",".join(ET_COMPONENTS),
    }
    return dataset.assign({ET_NAME: total})


def check_et_closure(dataset: xr.Dataset, rtol: float = 1e-4, atol: float = 1e-3) -> float | None:
    """Compare derived ET with CLM's own `EFLX_LH_TOT` where the file carries it.

    Returns the largest absolute difference found, or None when there is
    nothing to compare: the native total is absent because this is the daily
    stream, or no timestep has both values finite. Raises AssertionError on a
    mismatch, since a derivation that disagrees with the model's own
    bookkeeping is a bug, not a result.

    Raises KeyError when the dataset is the monthly stream (it carries the
    reader's `month` coordinate) but the native total is missing: that means
    it was filtered out by a `variables` selection, and silently skipping the
    check would leave a component-sum error uncaught on the one stream that
    can catch it. Open with `variables=ET_VARIABLES` or `variables=["ET"]`.
    """
    if NATIVE_TOTAL not in dataset:
        if MONTHLY_MARKER in dataset.coords:
            raise KeyError(
                f"{NATIVE_TOTAL} is not in this monthly dataset, so it was dropped by a variable "
                f"selection. Open with variables=ET_VARIABLES (or variables=['ET']) to keep it."
            )
        return None
    if ET_NAME not in dataset:
        dataset = derive_et(dataset)
    derived = dataset[ET_NAME].values
    native = dataset[NATIVE_TOTAL].values
    finite = np.isfinite(derived) & np.isfinite(native)
    if not finite.any():
        return None
    gap = np.abs(derived[finite] - native[finite])
    if not np.allclose(derived[finite], native[finite], rtol=rtol, atol=atol):
        raise AssertionError(
            f"Derived ET disagrees with {NATIVE_TOTAL} by up to {float(gap.max()):.4g} W/m^2; "
            "the components do not sum to the model's own total."
        )
    return float(gap.max())
