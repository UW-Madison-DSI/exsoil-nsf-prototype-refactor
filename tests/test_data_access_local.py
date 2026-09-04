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


def write_history_file(directory, site, stamp, variables, stream="h1a", day_index=0,
                       n_steps=4, netcdf_format=None):
    """Write a minimal CTSM-shaped history file.

    Enough structure to exercise discovery and variable selection without a
    completed simulation: a time axis, the bookkeeping variables CTSM emits
    alongside it (including `time_bounds`, the one a variable filter is most
    likely to lose), and whatever data variables the test asks for.

    Values are offset per file so a test can tell which file a row came from.
    """
    import numpy as np
    import xarray as xr

    n = n_steps
    # Distinct time values per file, or combine="by_coords" cannot order them.
    # Real CTSM files differ this way naturally; synthetic ones must be made to.
    offset = float(day_index * n)
    times = offset + np.arange(n, dtype=float)
    data = {name: (("time",), offset + np.arange(n, dtype=float)) for name in variables}
    data["mcdate"] = (("time",), np.full(n, 20180101 + day_index, dtype=int))
    data["mcsec"] = (("time",), np.arange(n, dtype=int) * 1800)
    data["time_bounds"] = (("time", "nbnd"), np.column_stack([times - 0.5, times + 0.5]))
    dataset = xr.Dataset(data, coords={"time": times})
    dataset.time.attrs["units"] = "days since 2018-01-01 00:00:00"

    target = Path(directory) / "archive" / "lnd" / "hist"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{site}.transient.clm2.{stream}.{stamp}.nc"
    dataset.to_netcdf(path, format=netcdf_format)
    return path


@pytest.mark.tier0
class TestVariableSelection:
    """Selecting variables at open time, without needing a real run.

    The monthly stream carries 623 variables per file; reading all of them
    takes ~117 s where selecting three takes ~10 s. The risk in that
    optimisation is silently losing the time axis, so that is what these pin.
    """

    @pytest.fixture
    def synthetic_run(self, tmp_path):
        stamps = ("2018-01-01-01800", "2018-01-02-01800")
        for day_index, stamp in enumerate(stamps):
            write_history_file(tmp_path, "KONZ", stamp, ["GPP", "TSOI", "FSH"],
                               day_index=day_index)
        return tmp_path

    def test_selection_keeps_only_requested_variables(self, synthetic_run):
        dataset = open_ctsm_hist(
            "KONZ", output_root=synthetic_run, variables=["GPP"]
        )
        assert "GPP" in dataset.data_vars
        assert "TSOI" not in dataset.data_vars
        assert "FSH" not in dataset.data_vars

    def test_selection_retains_the_time_axis(self, synthetic_run):
        """Losing time to a variable filter is never what the caller meant."""
        dataset = open_ctsm_hist(
            "KONZ", output_root=synthetic_run, variables=["GPP"]
        )
        assert dataset.sizes["time"] > 0
        assert {"time", "time_bounds", "mcdate", "mcsec"} <= set(dataset.variables)

    def test_a_bare_string_selects_that_one_variable(self, synthetic_run):
        """`variables="GPP"` must not be read as the characters G and P."""
        dataset = open_ctsm_hist("KONZ", output_root=synthetic_run, variables="GPP")
        assert "GPP" in dataset.data_vars
        assert "TSOI" not in dataset.data_vars

    def test_no_selection_returns_everything(self, synthetic_run):
        dataset = open_ctsm_hist("KONZ", output_root=synthetic_run)
        assert {"GPP", "TSOI", "FSH"} <= set(dataset.data_vars)

    def test_unknown_requested_variable_raises(self, synthetic_run):
        """A typo must not come back as a dataset with a time axis and no data."""
        with pytest.raises(KeyError, match="NOT_A_VAR"):
            open_ctsm_hist("KONZ", output_root=synthetic_run, variables=["NOT_A_VAR"])
        # ... even when it travels with a valid name
        with pytest.raises(KeyError, match="NOT_A_VAR"):
            open_ctsm_hist("KONZ", output_root=synthetic_run, variables=["GPP", "NOT_A_VAR"])


@pytest.mark.tier0
class TestMonthLabels:
    """The monthly stream carries the month it belongs to, read from the filename.

    CTSM stamps h0a.2018-07.nc with mcdate 20180801, so any index built from
    mcdate is a month late. The label has to travel with the data through
    combine="by_coords", not be zipped on from a separately sorted file list.
    """

    @pytest.fixture
    def monthly_run(self, tmp_path):
        # Written out of calendar order on purpose: the label must follow the
        # data, whatever order the files were listed or opened in.
        for day_index, stamp in ((1, "2018-02"), (0, "2018-01"), (2, "2018-03")):
            write_history_file(tmp_path, "KONZ", stamp, ["GPP"], stream="h0a",
                               day_index=day_index, n_steps=1)
        return tmp_path

    def test_month_coordinate_follows_the_data(self, monthly_run):
        dataset = open_ctsm_hist("KONZ", output_root=monthly_run, stream="monthly", variables=["GPP"])
        assert list(dataset["month"].values) == ["2018-01", "2018-02", "2018-03"]
        # value written into each file was its day_index, so the pairing is checkable
        assert list(dataset["GPP"].values) == [0.0, 1.0, 2.0]

    def test_month_coordinate_present_without_a_selection(self, monthly_run):
        dataset = open_ctsm_hist("KONZ", output_root=monthly_run, stream="monthly")
        assert "month" in dataset.coords

    def test_daily_stream_has_no_month_coordinate(self, tmp_path):
        write_history_file(tmp_path, "KONZ", "2018-01-01-01800", ["GPP"])
        dataset = open_ctsm_hist("KONZ", output_root=tmp_path)
        assert "month" not in dataset.coords


@pytest.mark.tier0
class TestS3VariableSelection:
    """`variables` must mean the same thing whichever source resolves.

    The S3 boundary is mocked at the three calls the reader makes -- key
    listing, storage options, and file opening -- so the branch runs without
    credentials or a network.
    """

    @pytest.fixture
    def mocked_s3(self, tmp_path, monkeypatch):
        # scipy is the S3 engine and reads only NetCDF-3, so write classic files
        paths = [
            write_history_file(tmp_path, "KONZ", stamp, ["GPP", "TSOI"], stream="h1",
                               day_index=i, netcdf_format="NETCDF3_CLASSIC")
            for i, stamp in enumerate(("2018-01-01-00000", "2018-01-02-00000"))
        ]
        keys = [f"archive_1/KONZ.transient/lnd/hist/{p.name}" for p in paths]
        by_key = dict(zip(keys, paths))

        class _Opener:
            def __init__(self, uri):
                self.path = by_key[uri.split("/", 3)[3]]

            def open(self):
                return open(self.path, "rb")

        monkeypatch.setattr(data_access, "list_objects_under_prefix", lambda s3, bucket, prefix: keys)
        monkeypatch.setattr(data_access, "get_storage_options", lambda endpoint_url=None: {})
        monkeypatch.setattr(data_access.fsspec, "open_files", lambda uris, mode, **kw: [_Opener(u) for u in uris])
        monkeypatch.setenv("CTSM_DATA_SOURCE", "s3")
        monkeypatch.setattr(data_access, "get_s3_client", lambda *a, **k: object())
        return tmp_path

    def test_s3_path_accepts_and_applies_variables(self, mocked_s3):
        dataset = open_ctsm_hist("KONZ", 2018, variables=["GPP"])
        assert "GPP" in dataset.data_vars
        assert "TSOI" not in dataset.data_vars
        assert {"time", "mcdate"} <= set(dataset.variables)

    def test_s3_path_raises_on_unknown_variable(self, mocked_s3):
        with pytest.raises(KeyError, match="NOT_A_VAR"):
            open_ctsm_hist("KONZ", 2018, variables=["NOT_A_VAR"])
