"""Settings for the harness, read from environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Ollama serves an OpenAI-style API on this URL.
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:8b"
    # Ollama ignores the key, but the openai client refuses to start without one.
    api_key: str = "ollama"
    # How many model calls one question may use before the agent gives up.
    max_steps: int = 10
    # Practice data (files and erp.db). File tools can't open anything outside it.
    data_dir: Path = Path("data")
    # Where the SQL tools come from: "builtin" (sql_tools.py, in this process)
    # or "mcp" (the erp-mcp server, a separate process).
    sql_via: str = "builtin"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from HARNESS_* variables. Missing ones keep their default."""
    env = os.environ if env is None else env
    default = Settings()
    sql_via = env.get("HARNESS_SQL_VIA", default.sql_via)
    if sql_via not in ("builtin", "mcp"):
        raise ValueError(f"HARNESS_SQL_VIA must be builtin or mcp, not {sql_via!r}")
    return Settings(
        base_url=env.get("HARNESS_BASE_URL", default.base_url),
        model=env.get("HARNESS_MODEL", default.model),
        api_key=env.get("HARNESS_API_KEY", default.api_key),
        max_steps=int(env.get("HARNESS_MAX_STEPS", default.max_steps)),
        data_dir=Path(env.get("HARNESS_DATA_DIR", default.data_dir)),
        sql_via=sql_via,
    )
