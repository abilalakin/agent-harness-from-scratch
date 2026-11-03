# Step 0: Setup

## What this step teaches

An agent harness is a normal program that talks to a model over HTTP. Before writing it, you need a model to talk to. Here that's Ollama, running Qwen3 8B on your GPU.

## What got installed

- **Ollama.** It runs open models locally and serves them on `http://localhost:11434`. Under `/v1` it speaks the same chat format as OpenAI's API. That's why the harness can use the `openai` Python package as its HTTP client.
- **qwen3:8b.** An 8-billion-parameter open model that can call tools. It takes about 5 GB of your 8 GB of video memory.
- **The `uv` project.** `pyproject.toml` lists two packages: `openai` (HTTP client) and `pytest` (tests, dev only).

## The context window setting

The context window is how many tokens the model can see at once: the system prompt, the whole chat history, and tool results. When it fills up, the oldest text gets cut, and Ollama does this without telling you.

We set `OLLAMA_CONTEXT_LENGTH=8192`. The model's cache grows with this number, and 8192 still fits on the GPU next to the model. Step 5 deals with what happens when 8192 isn't enough.

## Files to read

1. `src/harness/config.py`: where the model lives and which model to use. Change them with `HARNESS_BASE_URL`, `HARNESS_MODEL` and `HARNESS_API_KEY`.
2. `CLAUDE.md`: the rules Claude follows in this repo.

## Things to try

```bash
ollama run qwen3:8b "Say hi in three words."
ollama ps                         # PROCESSOR should say 100% GPU
uv run pytest -v                  # 2 tests pass
```

If `ollama ps` shows a CPU/GPU split, the model doesn't fit fully in video memory. Lower the context to 4096 and restart Ollama.
