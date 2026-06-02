"""
Tier 1: CESM case creation tests.

Validates the CIME case management workflow taught in CESM tutorials:
create_newcase, case.setup, xmlchange, xmlquery. Does NOT build or run
the model (that is Tier 2).

Reference: NCAR/CESM-Tutorial practical exercises.
Expected runtime: < 2 minutes total.
"""

import os
import subprocess
import pytest

pytestmark = pytest.mark.tier1


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, **kwargs,
    )


# ── CIME query tools ────────────────────────────────────────────────────

class TestQueryConfig:
    """query_config must list compsets and grids (tutorial step 1)."""

    def test_query_compsets(self, cesm_root):
        script = os.path.join(cesm_root, "cime", "scripts", "query_config")
        result = run([script, "--compsets"])
        assert result.returncode == 0, f"query_config --compsets failed:\n{result.stderr}"
        assert "I2000" in result.stdout or "B1850" in result.stdout

    def test_query_grids(self, cesm_root):
        script = os.path.join(cesm_root, "cime", "scripts", "query_config")
        result = run([script, "--grids"])
        assert result.returncode == 0, f"query_config --grids failed:\n{result.stderr}"
        assert "f19_g17" in result.stdout or "f09" in result.stdout

    def test_create_newcase_help(self, cesm_root):
        script = os.path.join(cesm_root, "cime", "scripts", "create_newcase")
        result = run([script, "--help"])
        assert result.returncode == 0
        assert "--case" in result.stdout
        assert "--compset" in result.stdout


# ── Case creation (I2000Clm50Sp: lightweight land-only) ─────────────────

class TestCaseCreation:
    """
    Create a land-only CLM case with satellite phenology.
    This is the lightest compset suitable for container testing,
    following the CESM tutorial pattern of starting with a simple case.
    """

    COMPSET = "I2000Clm50Sp"
    RES = "f19_g17"

    @pytest.fixture(scope="class")
    def case_dir(self, cesm_root, scratch_dir):
        case_path = scratch_dir / "test_i2000"
        script = os.path.join(cesm_root, "cime", "scripts", "create_newcase")
        result = run([
            script,
            "--case", str(case_path),
            "--compset", self.COMPSET,
            "--res", self.RES,
            "--machine", "container",
            "--run-unsupported",
        ])
        assert result.returncode == 0, (
            f"create_newcase failed:\n{result.stdout}\n{result.stderr}"
        )
        assert case_path.exists()
        return case_path

    def test_case_directory_created(self, case_dir):
        assert (case_dir / "case.setup").exists()
        assert (case_dir / "case.build").exists()

    def test_case_setup(self, case_dir):
        inputdata = os.path.join(os.environ.get("CESMDATAROOT", "/home/user"), "inputdata")
        os.makedirs(inputdata, exist_ok=True)
        result = run([str(case_dir / "case.setup")], cwd=str(case_dir))
        assert result.returncode == 0, (
            f"case.setup failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_xmlquery_stop_option(self, case_dir):
        result = run(
            [str(case_dir / "xmlquery"), "STOP_OPTION", "--value"],
            cwd=str(case_dir),
        )
        assert result.returncode == 0
        assert result.stdout.strip() in ("ndays", "nmonths", "nyears")

    def test_xmlchange_stop_n(self, case_dir):
        result = run(
            [str(case_dir / "xmlchange"), "STOP_N=1"],
            cwd=str(case_dir),
        )
        assert result.returncode == 0, f"xmlchange failed:\n{result.stderr}"
        verify = run(
            [str(case_dir / "xmlquery"), "STOP_N", "--value"],
            cwd=str(case_dir),
        )
        assert verify.stdout.strip() == "1"

    def test_xmlchange_stop_option(self, case_dir):
        result = run(
            [str(case_dir / "xmlchange"), "STOP_OPTION=ndays"],
            cwd=str(case_dir),
        )
        assert result.returncode == 0

    def test_xmlquery_compset(self, case_dir):
        result = run(
            [str(case_dir / "xmlquery"), "COMPSET", "--value"],
            cwd=str(case_dir),
        )
        assert result.returncode == 0
        assert "CLM" in result.stdout or "Clm" in result.stdout or "2000" in result.stdout

    def test_xmlquery_machine(self, case_dir):
        result = run(
            [str(case_dir / "xmlquery"), "MACH", "--value"],
            cwd=str(case_dir),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "container"


# ── run_neon_v2 CLI ─────────────────────────────────────────────────────

class TestRunNeonCLI:
    """run_neon_v2 must parse arguments without crashing."""

    def test_help(self):
        result = run(["run_neon_v2", "--help"])
        assert result.returncode == 0
        assert "--neon-sites" in result.stdout

    def test_list_sites_flag(self):
        result = run(["run_neon_v2", "--help"])
        assert "output-root" in result.stdout
