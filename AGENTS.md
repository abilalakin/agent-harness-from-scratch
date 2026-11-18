# agent-harness-from-scratch

A learning project: an agent harness built by hand, one idea per step. The user reads and runs each step. The coding agent (Claude, Codex, or another) writes the code.

- Design and step list: `docs/design.md`. Plans: `docs/superpowers/plans/`. Open points and ideas: `docs/backlog.md` (add a line, say where it came from).
- Run: `uv run harness`. Test: `uv run pytest`.
- Model: local `qwen3:8b` through Ollama's OpenAI-style API. Settings come from `HARNESS_*` env vars (`src/harness/config.py`).

## Rules

- Write the loop, tool handling and context handling ourselves. The `openai` package is only an HTTP client. Agent frameworks stay out.
- Messages are plain dicts in OpenAI chat format everywhere, so every message the model sees is easy to print and read.
- Tests use `tests/fakes.py::FakeModel`, so they are free, fast and offline.
- Every step updates `docs/architecture.md` (Mermaid diagram) and adds a note in `docs/steps/NN-name.md`: what the step teaches, which files to read in order, what to try.
- Keep each step readable in one sitting. Pick the plain, obvious code over the clever one.
- Comments: short and simple. One plain sentence that says why. Long comments, buzzwords and heavy punctuation make the code unreadable.
- When a step's tasks are done: a review pass for bugs (medium depth), fix what it finds, then a simplification pass. Commit that as its own commit before moving to the next step.
- Commits: at a commit point, show the changed files and the message, wait for the user's OK, then commit. Commits are signed with the personal key set in `.git/config`; leave the global git config alone.

## Git workflow

- Work goes straight to `main`, one commit per step or step part. No branches or PRs: this is a one-person learning repo.
- Messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`. Imperative mood ("add", not "added"). `!` after the type for a breaking change.
- One line, under 72 characters. No body, no `Co-Authored-By` or other attribution lines.
