"""Tier 0 tests for source-agnostic CTSM history access (Phase 1, issue #6).

These cover the reader boundary rather than the notebooks. The failure mode
worth guarding against is a silent empty read: a stale glob matches nothing,
`open_mfdataset` yields an empty or partial Dataset, and downstream code
treats it as "no data for that year" instead of a bug. So the assertions are
on file counts, stream tokens, and non-zero time length, not merely on calls
returning without raising.

Data-backed tests skip when their inputs are absent so the suite still runs on
a machine with no completed simulation:

    CTSM_TEST_LIVE_ROOT      root of a completed CTSM 5.4 run (h1a/h0a, CDF-5)
    CTSM_TEST_REFERENCE_ROOT root holding the legacy reference copies (h1/h0)
"""

import os
from pathlib import Path

import pytest

from analytics_modules import data_access
from analytics_modules.data_access import (
    STREAM_TOKENS,
    _engine_for_local,
    find_ctsm_hist_files,
    open_ctsm_hist,
    resolve_source,
)

LIVE_ROOT = os.getenv("CTSM_TEST_LIVE_ROOT")
REFERENCE_ROOT = os.getenv("CTSM_TEST_REFERENCE_ROOT", str(Path(__file__).resolve().parents[1]))

requires_live = pytest.mark.skipif(
    not (LIVE_ROOT and Path(LIVE_ROOT).is_dir()),
    reason="set CTSM_TEST_LIVE_ROOT to a completed CTSM run",
)
requires_reference = pytest.mark.skipif(
    not list(Path(REFERENCE_ROOT).glob("reference-output/*/lnd/hist")),
    reason="reference copies not staged (see tests/fixtures/reference_output/README.md)",
)


@pytest.mark.tier0
class TestSourceResolution:
    """Source selection must not require credentials to decide it is local."""

    def test_defaults_to_local(self, monkeypatch):
        monkeypatch.delenv("CTSM_DATA_SOURCE", raising=False)
        assert resolve_source() == "local"

    def test_env_var_selects_s3(self, monkeypatch):
        monkeypatch.setenv("CTSM_DATA_SOURCE", "s3")
        assert resolve_source() == "s3"

    def test_explicit_argument_beats_env(self, monkeypatch):
        monkeypatch.setenv("CTSM_DATA_SOURCE", "s3")
        assert resolve_source("local") == "local"

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError, match="local"):
            resolve_source("gopher")

    def test_no_cos_credentials_needed_for_local(self, monkeypatch):
        monkeypatch.delenv("COS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("COS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("CTSM_DATA_SOURCE", raising=False)
        assert resolve_source() == "local"


@pytest.mark.tier0
class TestS3Dispatch:
    """What open_ctsm_hist forwards to the S3 reader.

    These need no credentials and no network: the reader is replaced with a
    recorder. Both bugs guarded here shipped in Phase 1 precisely because the
    rest of the suite only exercises the local branch.
    """

    @pytest.fixture
    def forwarded(self, monkeypatch):
        captured = {}

        def fake_reader(input_label, s3_client, bucket_name, neon_site, year, **kwargs):
            captured.update(year=year, neon_site=neon_site,
                            input_label=input_label, **kwargs)
            return "dataset"

        monkeypatch.setattr(data_access, "open_ctsm_hist_from_s3", fake_reader)
        monkeypatch.setattr(data_access, "get_s3_client", lambda *a, **k: None)
        return captured

    def test_year_none_becomes_empty_prefix(self, forwarded):
        """year=None must match every year, not the literal string 'None'."""
        open_ctsm_hist("KONZ", None, source="s3")
        assert forwarded["year"] == "", (
            "year=None must forward an empty prefix; "
            f"got {forwarded['year']!r}, which matches no key"
        )

    def test_year_is_stringified(self, forwarded):
        open_ctsm_hist("KONZ", 2018, source="s3")
        assert forwarded["year"] == "2018"

    def test_stream_maps_to_legacy_token(self, forwarded):
        """S3 holds pre-5.4 output, so 'monthly' must reach it as h0, not h1."""
        open_ctsm_hist("KONZ", 2018, source="s3", stream="monthly")
        assert forwarded["stream_token"] == "h0"

    def test_daily_maps_to_legacy_token(self, forwarded):
        open_ctsm_hist("KONZ", 2018, source="s3", stream="daily")
        assert forwarded["stream_token"] == "h1"

    def test_explicit_stream_token_wins(self, forwarded):
        open_ctsm_hist("KONZ", 2018, source="s3", stream="daily", stream_token="h1a")
        assert forwarded["stream_token"] == "h1a"

    def test_unknown_stream_rejected_on_s3_path(self, forwarded):
        with pytest.raises(ValueError, match="daily"):
            open_ctsm_hist("KONZ", 2018, source="s3", stream="hourly")


@pytest.mark.tier0
class TestFileDiscovery:
    def test_rejects_unknown_stream(self):
        with pytest.raises(ValueError, match="daily"):
            find_ctsm_hist_files("KONZ", 2018, stream="hourly")

    def test_missing_data_names_what_it_tried(self, tmp_path):
        """An empty result must be loud, and must say where it looked."""
        with pytest.raises(FileNotFoundError) as excinfo:
            find_ctsm_hist_files("KONZ", 2018, output_root=tmp_path)
        message = str(excinfo.value)
        assert "Tried:" in message
        assert "h1a" in message and "h1." in message, "both stream conventions should be attempted"

    def test_both_conventions_are_known(self):
        assert STREAM_TOKENS["daily"][0] == "h1a", "current naming must be tried first"
        assert "h1" in STREAM_TOKENS["daily"]
        assert "h0" in STREAM_TOKENS["monthly"]


@pytest.mark.tier0
@requires_live
class TestLiveOutput:
    def test_daily_resolves_to_suffixed_stream(self):
        files = find_ctsm_hist_files("KONZ", 2018, output_root=LIVE_ROOT)
        assert files, "no live daily files found"
        assert all(".clm2.h1a." in f for f in files)

    def test_monthly_resolves_to_suffixed_stream(self):
        files = find_ctsm_hist_files("KONZ", stream="monthly", output_root=LIVE_ROOT)
        assert files and all(".clm2.h0a." in f for f in files)

    def test_live_files_need_the_netcdf4_engine(self):
        """CTSM 5.4 writes CDF-5, which scipy and h5netcdf both fail to read."""
        first = find_ctsm_hist_files("KONZ", 2018, output_root=LIVE_ROOT)[0]
        assert _engine_for_local(first) == "netcdf4"

    def test_opens_non_empty_dataset(self):
        dataset = open_ctsm_hist("KONZ", 2018, output_root=LIVE_ROOT)
        assert dataset.sizes.get("time", 0) > 0
        # Subset, not intersection: the data contract promises all three, and
        # an intersection check passes when two of them have gone missing.
        missing = {"TSOI", "H2OSOI", "GPP"} - set(dataset.variables)
        assert not missing, f"missing contract variables: {sorted(missing)}"


@pytest.mark.tier0
@requires_reference
class TestLegacyReferenceCopies:
    """The validation oracle uses the pre-5.4 naming and must stay readable."""

    def test_resolves_to_unsuffixed_stream(self):
        files = find_ctsm_hist_files("CLBJ", 2019, output_root=REFERENCE_ROOT)
        assert files and all(".clm2.h1." in f for f in files)

    def test_reference_files_are_netcdf3(self):
        first = find_ctsm_hist_files("CLBJ", 2019, output_root=REFERENCE_ROOT)[0]
        assert _engine_for_local(first) == "scipy"

    def test_opens_non_empty_dataset(self):
        dataset = open_ctsm_hist("CLBJ", 2019, output_root=REFERENCE_ROOT)
        assert dataset.sizes.get("time", 0) > 0
