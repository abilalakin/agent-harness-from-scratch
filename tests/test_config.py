from pathlib import Path

import pytest

from harness.config import load_settings


def test_defaults_point_at_local_ollama():
    s = load_settings({})
    assert s.base_url == "http://localhost:11434/v1"
    assert s.model == "qwen3:8b"


def test_env_overrides():
    s = load_settings(
        {"HARNESS_BASE_URL": "http://x/v1", "HARNESS_MODEL": "m", "HARNESS_API_KEY": "k"}
    )
    assert (s.base_url, s.model, s.api_key) == ("http://x/v1", "m", "k")


def test_max_steps_default_and_override():
    assert load_settings({}).max_steps == 10
    assert load_settings({"HARNESS_MAX_STEPS": "3"}).max_steps == 3


def test_data_dir_default_and_override():
    assert load_settings({}).data_dir == Path("data")
    assert load_settings({"HARNESS_DATA_DIR": "/tmp/x"}).data_dir == Path("/tmp/x")


def test_sql_via_default_override_and_bad_value():
    assert load_settings({}).sql_via == "builtin"
    assert load_settings({"HARNESS_SQL_VIA": "mcp"}).sql_via == "mcp"
    with pytest.raises(ValueError, match="builtin or mcp"):
        load_settings({"HARNESS_SQL_VIA": "both"})


def test_context_window_default_and_override():
    assert load_settings({}).context_window == 8192
    assert load_settings({"HARNESS_CONTEXT_WINDOW": "4096"}).context_window == 4096


@pytest.mark.parametrize(
    "name, value",
    [("HARNESS_MAX_STEPS", "0"), ("HARNESS_MAX_STEPS", "ten"), ("HARNESS_CONTEXT_WINDOW", "-5")],
)
def test_counts_must_be_whole_numbers_of_at_least_one(name, value):
    with pytest.raises(ValueError, match="whole number of 1 or more"):
        load_settings({name: value})


def test_sandbox_setting_validated():
    assert load_settings({}).sandbox == "bwrap"
    assert load_settings({"HARNESS_SANDBOX": "none"}).sandbox == "none"
    with pytest.raises(ValueError, match="bwrap, none or off"):
        load_settings({"HARNESS_SANDBOX": "podman"})
