"""Tier 0 tests for the derived ET variable (issue #18)."""

import numpy as np
import pytest
import xarray as xr

from analytics_modules.fluxes import ET_COMPONENTS, ET_VARIABLES, check_et_closure, derive_et

pytestmark = pytest.mark.tier0


def components(n: int = 6, with_total: bool = True) -> xr.Dataset:
    rng = np.random.default_rng(0)
    data = {name: (("time", "lndgrid"), rng.uniform(0, 100, (n, 1)), {"units": "W/m^2"}) for name in ET_COMPONENTS}
    dataset = xr.Dataset(data, coords={"time": np.arange(n, dtype=float)})
    if with_total:
        dataset["EFLX_LH_TOT"] = sum(dataset[name] for name in ET_COMPONENTS)
    return dataset


def test_et_is_the_sum_and_components_are_kept():
    out = derive_et(components())
    expected = sum(components()[name].values for name in ET_COMPONENTS)
    np.testing.assert_allclose(out["ET"].values, expected)
    for name in ET_COMPONENTS:
        assert name in out
    assert out["ET"].attrs["units"] == "W/m^2"
    assert out["ET"].attrs["components"] == "FCTR,FCEV,FGEV"


def test_missing_component_raises_rather_than_summing_two():
    with pytest.raises(KeyError, match="FGEV"):
        derive_et(components().drop_vars("FGEV"))


def test_closure_against_the_native_monthly_total():
    assert check_et_closure(derive_et(components())) == pytest.approx(0.0, abs=1e-9)


def test_closure_failure_is_an_error_not_a_number():
    dataset = derive_et(components())
    dataset["EFLX_LH_TOT"] = dataset["EFLX_LH_TOT"] * 1.05
    with pytest.raises(AssertionError, match="do not sum"):
        check_et_closure(dataset)


def test_daily_stream_has_nothing_to_close_against():
    """The daily stream carries no EFLX_LH_TOT; that is a None, not a pass."""
    assert check_et_closure(derive_et(components(with_total=False))) is None


def test_monthly_dataset_missing_the_total_is_a_selection_error_not_a_skip():
    """The reader marks the monthly stream with a `month` coordinate. If the
    native total is missing there, a `variables` selection dropped it."""
    monthly = components(with_total=False).assign_coords(month=("time", np.array(["2018-01"] * 6)))
    with pytest.raises(KeyError, match="ET_VARIABLES"):
        check_et_closure(derive_et(monthly))


def test_all_nan_pairs_return_none_not_a_perfect_closure():
    dataset = components()
    for name in ET_COMPONENTS + ("EFLX_LH_TOT",):
        dataset[name] = dataset[name] * np.nan
    assert check_et_closure(derive_et(dataset)) is None


def test_et_variables_is_what_to_request_on_the_monthly_stream():
    assert ET_VARIABLES == ("FCTR", "FCEV", "FGEV", "EFLX_LH_TOT")
