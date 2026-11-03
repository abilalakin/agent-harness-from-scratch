# Architecture

How the harness fits together right now. This diagram changes with every step.

```mermaid
flowchart LR
    User([You]) -- types --> CLI["cli.run_repl<br/>read, print, /reset, /exit"]
    CLI -- "ask(text)" --> Agent["Agent<br/>messages: list of dicts<br/>(system, user, assistant, ...)"]
    Agent -- "whole history<br/>every call" --> Model["OpenAIChatModel<br/>strips &lt;think&gt; blocks"]
    Model -- "HTTP POST /v1/chat/completions" --> Ollama["Ollama<br/>qwen3:8b on the GPU<br/>localhost:11434"]
    Ollama -. "one assistant message" .-> Model
    Model -. reply .-> Agent
    Agent -. answer text .-> CLI
```

## What changed

- **Step 0:** Ollama runs the model locally. No harness code yet, only settings (`config.py`) that say where the model is.
- **Step 1:** The chat loop. `Agent` keeps the history and sends all of it on every call. `OpenAIChatModel` is the only part that knows about HTTP. The CLI catches connection errors, so a stopped Ollama gives a hint instead of a crash.
