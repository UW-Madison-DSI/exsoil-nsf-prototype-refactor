"""Tier 0 tests for observed tower GPP (issue #12).

The failure modes worth guarding against here are quiet ones, and all three
were found by inspecting the real dataset rather than reasoning about it:

- **Units.** Observations are umol CO2 m-2 s-1, model GPP is gC m-2 s-1. A
  missed conversion is a five-order-of-magnitude bias that reads as
  catastrophic model failure, not as a bug.
- **Empty site-months.** 18% of files contain no GPP at all, and GPP_fqc
  reports "measured" over them, so coverage must be derived from the values.
- **Negative GPP.** A flux-partitioning artifact, not signal. It is reported
  rather than clamped, so nothing here should silently make it disappear.

Network-backed tests skip unless a cache is staged:

    NEON_EVAL_TEST_CACHE   directory holding {SITE}/{SITE}_eval_{YYYY-MM}.nc
"""

import os
from pathlib import Path

import numpy as np
import pytest

from analytics_modules.observations import (
    EVAL_FIRST_MONTH,
    EVAL_LAST_MONTH,
    UMOL_CO2_TO_GC,
    eval_file_url,
    eval_months,
    monthly_observed_gpp,
    observed_gpp_coverage,
)

CACHE = os.getenv("NEON_EVAL_TEST_CACHE")

requires_cache = pytest.mark.skipif(
    not (CACHE and Path(CACHE).is_dir()),
    reason="set NEON_EVAL_TEST_CACHE to a directory of staged eval files",
)


@pytest.mark.tier0
class TestPureHelpers:
    """No network, no data."""

    def test_url_shape(self):
        url = eval_file_url("KONZ", "2018-07")
        assert url.endswith("/KONZ/KONZ_eval_2018-07.nc")
        assert url.startswith("https://")

    def test_published_window(self):
        months = eval_months()
        assert months[0] == EVAL_FIRST_MONTH
        assert months[-1] == EVAL_LAST_MONTH
        assert len(months) == 45

    def test_unit_conversion_constant(self):
        """12.011 g C per mol, expressed for umol input."""
        assert UMOL_CO2_TO_GC == pytest.approx(12.011e-6)
        # A typical midday observation of 20 umol/m2/s is ~2.4e-4 gC/m2/s.
        assert 20 * UMOL_CO2_TO_GC == pytest.approx(2.4022e-4, rel=1e-6)


@pytest.mark.tier0
@requires_cache
class TestMonthlyObservedGPP:
    def test_returns_converted_units_by_default(self):
        frame = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        # Monthly-mean GPP in gC/m2/s is order 1e-4; in umol it would be ~10.
        assert frame["gpp"].abs().max() < 1e-2, "looks like unconverted umol"

    def test_convert_units_false_gives_umol(self):
        native = monthly_observed_gpp(
            "KONZ", cache_dir=CACHE, download=False, convert_units=False
        )
        converted = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        ratio = converted["gpp"] / native["gpp"]
        assert np.allclose(ratio, UMOL_CO2_TO_GC)

    def test_empty_site_months_are_omitted_not_nan(self):
        """18% of files have no GPP; they must not become NaN rows.

        A NaN row averages into downstream statistics as missing data rather
        than as absent data, which is how an all-empty site could look like a
        low-GPP site.
        """
        frame = monthly_observed_gpp("ABBY", cache_dir=CACHE, download=False)
        assert not frame["gpp"].isna().any()
        assert len(frame) < 45, "ABBY has known gaps; got a full series"

    def test_coverage_is_derived_from_values_not_the_flag(self):
        """GPP_fqc reports 'measured' over all-NaN files, so it cannot be trusted."""
        frame = monthly_observed_gpp("ABBY", cache_dir=CACHE, download=False)
        assert (frame["coverage"] > 0).all()
        assert (frame["coverage"] <= 1).all()

    def test_negatives_are_reported_not_clamped(self):
        """The partitioning artifact must stay visible."""
        frame = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        assert (frame["negative_fraction"] > 0).any()
        # KONZ has known dormant-season months whose mean is below zero.
        assert frame["low_signal"].any()
        assert (frame.loc[frame["low_signal"], "gpp"] < 0).all()

    def test_index_is_sorted_month_starts(self):
        frame = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        assert frame.index.is_monotonic_increasing
        assert (frame.index.day == 1).all()

    def test_missing_data_raises_with_context(self):
        with pytest.raises(FileNotFoundError, match="No observed GPP"):
            monthly_observed_gpp(
                "KONZ", ["2018-01"], cache_dir="/nonexistent", download=False
            )


@pytest.mark.tier0
@requires_cache
class TestCoverageSummary:
    def test_reports_known_site_coverage(self):
        """Coverage varies enough to change Phase 3/5 scope, so pin it."""
        summary = observed_gpp_coverage(cache_dir=CACHE, download=False)
        assert summary.loc["KONZ", "months_with_gpp"] == 45, "KONZ should be complete"
        assert summary.loc["ABBY", "months_with_gpp"] < 45, "ABBY has known gaps"
        assert (summary["months_possible"] == 45).all()
