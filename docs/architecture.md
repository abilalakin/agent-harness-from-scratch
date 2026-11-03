# Architecture

How the harness fits together right now. This diagram changes with every step.

```mermaid
flowchart LR
    User([You]) --> Terminal[Terminal]
    Terminal --> Ollama["Ollama<br/>qwen3:8b on the GPU<br/>localhost:11434"]
```

## What changed

- **Step 0:** Ollama runs the model locally. No harness code yet, only settings (`config.py`) that say where the model is.
