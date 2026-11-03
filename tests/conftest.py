from pathlib import Path

import pytest

from harness.practice_data import make_all


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    """Practice data in a temp folder, made once per test run. Tests only read it."""
    path = tmp_path_factory.mktemp("data")
    make_all(path)
    return path
