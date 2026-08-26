"""Tier 0 tests for observed tower GPP (issue #12).

The failure modes worth guarding against are quiet ones, and all three were
found by inspecting the real dataset rather than reasoning about it:

- **Units.** Observations are umol CO2 m-2 s-1, model GPP is gC m-2 s-1. A
  missed conversion is a five-order-of-magnitude bias that reads as
  catastrophic model failure, not as a bug.
- **Empty site-months.** 18% of files contain no GPP at all, and GPP_fqc
  reports "measured" over them, so coverage must come from the values.
- **Negative GPP.** A flux-partitioning artifact, not signal. It is reported
  rather than clamped, so nothing here should silently make it disappear.

Behaviour is tested against **synthetic files** built in a temp directory, so
these run everywhere and a regression cannot hide behind a missing dataset.
The real-data tests at the bottom are integration checks that pin known
properties of the published dataset, and skip unless a cache is staged:

    NEON_EVAL_TEST_CACHE   directory holding {SITE}/{SITE}_eval_{YYYY-MM}.nc
"""

import os
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from analytics_modules import observations
from analytics_modules.observations import (
    EVAL_FIRST_MONTH,
    EVAL_LAST_MONTH,
    UMOL_CO2_TO_GC,
    download_eval_files,
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


def write_eval_file(directory: Path, site: str, month: str, gpp) -> Path:
    """Write a minimal eval file shaped like the real ones.

    The real files carry (time, lat, lon) with a GPP_fqc companion. The flag
    is deliberately set to 0 ("measured") even where GPP is NaN, because that
    is what the published data does and it is the trap this module exists to
    avoid.
    """
    values = np.asarray(gpp, dtype=float).reshape(-1, 1, 1)
    dataset = xr.Dataset(
        {
            "GPP": (("time", "lat", "lon"), values,
                    {"units": "umolm-2s-1", "long_name": "gross primary productivity"}),
            "GPP_fqc": (("time", "lat", "lon"), np.zeros_like(values)),
        },
        coords={"time": np.arange(values.shape[0], dtype=float),
                "lat": [0.0], "lon": [0.0]},
    )
    dataset.time.attrs["units"] = f"days since {month}-01 00:00:00"
    target = directory / site / f"{site}_eval_{month}.nc"
    target.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(target)
    return target


@pytest.fixture
def synthetic_cache(tmp_path):
    """A site with one normal month, one empty month, one low-signal month."""
    site = "TEST"
    # Mean +10 umol, a quarter of samples negative.
    normal = np.array([-2.0] * 12 + [14.0] * 36)
    write_eval_file(tmp_path, site, "2018-01", normal)
    # Entirely absent, while GPP_fqc still claims "measured".
    write_eval_file(tmp_path, site, "2018-02", np.full(48, np.nan))
    # Dormant season: mean below zero, the low_signal case.
    write_eval_file(tmp_path, site, "2018-03", np.array([-1.0] * 30 + [0.5] * 18))
    return tmp_path, site


@pytest.mark.tier0
class TestPureHelpers:
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
        assert UMOL_CO2_TO_GC == pytest.approx(12.011e-6)
        # A typical midday observation of 20 umol/m2/s is ~2.4e-4 gC/m2/s.
        assert 20 * UMOL_CO2_TO_GC == pytest.approx(2.4022e-4, rel=1e-6)


@pytest.mark.tier0
class TestAggregationBehaviour:
    """Deterministic, no network, no staged dataset."""

    def test_units_convert_by_default(self, synthetic_cache):
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-01"], cache_dir=root, download=False)
        # normal month mean is +10 umol/m2/s by construction
        assert frame.loc[frame.index[0], "gpp"] == pytest.approx(10.0 * UMOL_CO2_TO_GC)

    def test_convert_units_false_gives_native_umol(self, synthetic_cache):
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-01"], cache_dir=root,
                                     download=False, convert_units=False)
        assert frame.loc[frame.index[0], "gpp"] == pytest.approx(10.0)

    def test_empty_month_is_omitted_not_nan(self, synthetic_cache):
        """A NaN row averages downstream as missing data, not absent data."""
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-01", "2018-02"],
                                     cache_dir=root, download=False)
        assert len(frame) == 1
        assert not frame["gpp"].isna().any()
        assert "2018-02" not in {str(i)[:7] for i in frame.index}

    def test_coverage_ignores_the_quality_flag(self, synthetic_cache):
        """GPP_fqc is 0 ('measured') on the empty file; coverage must not be."""
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-01"], cache_dir=root, download=False)
        assert frame.loc[frame.index[0], "coverage"] == pytest.approx(1.0)
        assert frame.loc[frame.index[0], "n_obs"] == 48

    def test_negative_fraction_is_reported(self, synthetic_cache):
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-01"], cache_dir=root, download=False)
        assert frame.loc[frame.index[0], "negative_fraction"] == pytest.approx(12 / 48)

    def test_low_signal_flags_negative_means_without_clamping(self, synthetic_cache):
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-03"], cache_dir=root, download=False)
        row = frame.iloc[0]
        assert row["low_signal"], "negative monthly mean should be flagged"
        assert row["gpp"] < 0, "value must stay negative, not be clamped to zero"

    def test_index_is_sorted_month_starts(self, synthetic_cache):
        root, site = synthetic_cache
        frame = monthly_observed_gpp(site, ["2018-03", "2018-01"],
                                     cache_dir=root, download=False)
        assert frame.index.is_monotonic_increasing
        assert (frame.index.day == 1).all()

    def test_all_months_empty_raises_with_context(self, synthetic_cache):
        root, site = synthetic_cache
        with pytest.raises(FileNotFoundError, match="No observed GPP"):
            monthly_observed_gpp(site, ["2018-02"], cache_dir=root, download=False)

    def test_missing_cache_raises_with_context(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No observed GPP"):
            monthly_observed_gpp("KONZ", ["2018-01"],
                                 cache_dir=tmp_path / "nope", download=False)

    def test_empty_month_selection_rejected(self, tmp_path):
        """Empty input must not surface as an unrelated IndexError."""
        with pytest.raises(ValueError, match="months is empty"):
            monthly_observed_gpp("KONZ", [], cache_dir=tmp_path, download=False)


@pytest.mark.tier0
class TestDownloader:
    """Cache, 404 and error paths, without touching the live service."""

    class FakeResponse:
        def __init__(self, status_code, content=b"payload"):
            self.status_code = status_code
            self.content = content

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    def test_downloads_and_writes(self, tmp_path, monkeypatch):
        calls = []

        def fake_get(url, timeout=None):
            calls.append(url)
            return self.FakeResponse(200, b"netcdf-bytes")

        monkeypatch.setattr(observations.requests, "get", fake_get)
        paths = download_eval_files("KONZ", ["2018-01"], cache_dir=tmp_path)
        assert len(paths) == 1
        assert paths[0].read_bytes() == b"netcdf-bytes"
        assert len(calls) == 1

    def test_cache_hit_skips_the_network(self, tmp_path, monkeypatch):
        """A regression here would re-fetch, or worse, overwrite the cache."""
        def fail(*a, **k):
            raise AssertionError("network called despite a cached file")

        target = tmp_path / "KONZ" / "KONZ_eval_2018-01.nc"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"already here")

        monkeypatch.setattr(observations.requests, "get", fail)
        paths = download_eval_files("KONZ", ["2018-01"], cache_dir=tmp_path)
        assert paths == [target]
        assert target.read_bytes() == b"already here"

    def test_overwrite_refetches(self, tmp_path, monkeypatch):
        target = tmp_path / "KONZ" / "KONZ_eval_2018-01.nc"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"stale")

        monkeypatch.setattr(observations.requests, "get",
                            lambda url, timeout=None: self.FakeResponse(200, b"fresh"))
        download_eval_files("KONZ", ["2018-01"], cache_dir=tmp_path, overwrite=True)
        assert target.read_bytes() == b"fresh"

    def test_404_is_skipped_not_raised(self, tmp_path, monkeypatch, capsys):
        """Gaps are normal in this dataset; a missing month must not abort a run."""
        monkeypatch.setattr(observations.requests, "get",
                            lambda url, timeout=None: self.FakeResponse(404))
        paths = download_eval_files("KONZ", ["2022-01"], cache_dir=tmp_path)
        assert paths == []
        assert "not published" in capsys.readouterr().out

    def test_server_error_propagates(self, tmp_path, monkeypatch):
        """A 500 is not a gap -- it should not be silently swallowed."""
        monkeypatch.setattr(observations.requests, "get",
                            lambda url, timeout=None: self.FakeResponse(500))
        with pytest.raises(RuntimeError, match="HTTP 500"):
            download_eval_files("KONZ", ["2018-01"], cache_dir=tmp_path)

    def test_partial_failure_keeps_earlier_downloads(self, tmp_path, monkeypatch):
        responses = {"2018-01": 200, "2018-02": 404, "2018-03": 200}

        def fake_get(url, timeout=None):
            month = url.rsplit("_", 1)[-1].replace(".nc", "")
            return self.FakeResponse(responses[month])

        monkeypatch.setattr(observations.requests, "get", fake_get)
        paths = download_eval_files("KONZ", list(responses), cache_dir=tmp_path)
        assert [p.name for p in paths] == [
            "KONZ_eval_2018-01.nc", "KONZ_eval_2018-03.nc"
        ]


@pytest.mark.tier0
@requires_cache
class TestAgainstPublishedData:
    """Integration checks pinning known properties of the real dataset."""

    def test_konz_is_complete_and_abby_is_not(self):
        """Coverage varies enough to change Phase 3/5 scope, so pin it."""
        summary = observed_gpp_coverage(cache_dir=CACHE, download=False)
        assert summary.loc["KONZ", "months_with_gpp"] == 45
        assert summary.loc["ABBY", "months_with_gpp"] < 45
        assert (summary["months_possible"] == 45).all()

    def test_real_units_are_plausible(self):
        frame = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        # Monthly-mean GPP in gC/m2/s is order 1e-4; unconverted umol is ~10.
        assert frame["gpp"].abs().max() < 1e-2

    def test_real_data_has_dormant_season_low_signal_months(self):
        frame = monthly_observed_gpp("KONZ", cache_dir=CACHE, download=False)
        low = frame[frame["low_signal"]]
        assert len(low) > 0
        assert (low["gpp"] < 0).all()
        # All known cases are Sep-Mar, where true GPP is near zero.
        assert set(low.index.month) <= {9, 10, 11, 12, 1, 2, 3}
