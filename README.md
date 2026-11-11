# agent-harness-from-scratch

An LLM agent harness built step by step in plain Python, to learn how one works inside. No agent framework: the tool loop, the sandboxing, the MCP client and the context management are all written by hand, one idea per step. It runs fully local, on an open model through Ollama.

Each step is a commit with tests, a note on what it teaches (`docs/steps/`), and an update to the architecture diagram (`docs/architecture.md`).

| Step | What it adds |
|---|---|
| 1 | A chat loop: the model has no memory, the harness resends the history |
| 2 | Tools: the model asks, the harness runs, errors come back as text |
| 3 | Fake ERP data; file, PDF, Excel and read-only SQL tools, locked to one folder |
| 4 | An MCP server for the SQL tools, and the harness as an MCP client |
| 5 | Big data: partial-result notes, paging, search, keeping the chat inside the context window |
| 6 | Code execution in a sandbox |
| 7 | Human in the loop: a messy data migration with an approval page |

Start with `docs/design.md`, then `docs/steps/00-setup.md`.

## Run it

```bash
uv run make-data     # fake practice data in data/
uv run harness       # chat; type /exit to quit
uv run pytest        # offline tests, no model needed
```

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), and [Ollama](https://ollama.com) with `qwen3:8b` pulled (see `docs/steps/00-setup.md`).
