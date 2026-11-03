# learn-harness-engineering

A learning project: an agent harness built by hand, one idea per step. The user reads and runs each step. The coding agent (Claude, Codex, or another) writes the code.

- Design and step list: `docs/design.md`. Plans: `docs/superpowers/plans/`.
- Run: `uv run harness`. Test: `uv run pytest`.
- Model: local `qwen3:8b` through Ollama's OpenAI-style API. Settings come from `HARNESS_*` env vars (`src/harness/config.py`).

## Rules

- Write the loop, tool handling and context handling ourselves. The `openai` package is only an HTTP client. Agent frameworks stay out.
- Messages are plain dicts in OpenAI chat format everywhere, so every message the model sees is easy to print and read.
- Tests use `tests/fakes.py::FakeModel`, so they are free, fast and offline.
- Every step updates `docs/architecture.md` (Mermaid diagram) and adds a note in `docs/steps/NN-name.md`: what the step teaches, which files to read in order, what to try.
- Keep each step readable in one sitting. Pick the plain, obvious code over the clever one.
- Commits: at a commit point, show the changed files and a Conventional Commits message, wait for the user's OK, then commit. Commits are signed with the personal key set in `.git/config`; leave the global git config alone.
