"""
Pytest configuration for container validation tests.

These tests validate that the multi-arch Docker image provides the
functionality documented in CESM tutorials and workshops
(https://www.cesm.ucar.edu/events/tutorials).

Tests are organized into tiers by execution time and dependency:

    Tier 0 - Smoke tests (seconds): imports, CLI tools, env vars
    Tier 1 - Case creation (seconds-minutes): create_newcase, case.setup
    Tier 2 - Build & analysis (minutes): case.build, scientific workflows

Run a specific tier with:
    pytest tests/ -m tier0
    pytest tests/ -m tier1
    pytest tests/ -m tier2
"""

import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: smoke tests (seconds)")
    config.addinivalue_line("markers", "tier1: case creation tests (seconds-minutes)")
    config.addinivalue_line("markers", "tier2: build and analysis tests (minutes)")


@pytest.fixture(scope="session")
def cesm_root():
    return os.environ.get("CESMROOT", "/opt/ncar/cesm")


@pytest.fixture(scope="session")
def conda_prefix():
    return os.environ.get("CONDA_PREFIX", "/opt/conda")


@pytest.fixture(scope="session")
def scratch_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("cesm_test_cases")
