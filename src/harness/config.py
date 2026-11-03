"""Settings for the harness, read from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Ollama serves an OpenAI-style API on this URL.
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:8b"
    # Ollama ignores the key, but the openai client refuses to start without one.
    api_key: str = "ollama"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from HARNESS_* variables. Missing ones keep their default."""
    env = os.environ if env is None else env
    default = Settings()
    return Settings(
        base_url=env.get("HARNESS_BASE_URL", default.base_url),
        model=env.get("HARNESS_MODEL", default.model),
        api_key=env.get("HARNESS_API_KEY", default.api_key),
    )
