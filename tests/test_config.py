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
