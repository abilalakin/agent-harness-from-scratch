# Step 1: Chat loop

## What this step teaches

**The model has no memory.** Each call to the model is separate. It doesn't know what you said a minute ago. The harness creates the feeling of a conversation by keeping a list of every message and sending the whole list every time.

That list is the most important thing in an agent harness. Everything later (tools, files, MCP, approvals) ends up as more messages in it. It's also why the context window from step 0 matters: the list grows with every turn, and one day it won't fit.

A message is a plain dict:

```python
{"role": "system", "content": "You are a helpful assistant. Answer briefly."}
{"role": "user", "content": "my name is Bilal"}
{"role": "assistant", "content": "Hello, Bilal!"}
```

Two smaller lessons:

- **Thinking models think out loud.** Qwen3 may start its reply with `<think>…</think>`. That text is for the model, not for you, so `strip_thinking` removes it. If the reply gets cut off mid-thought, there is an opening tag and no closing one, and the rest is dropped too.
- **Only save a turn once it worked.** `Agent.ask` builds the new list, calls the model, and saves the list only if the call succeeded. If Ollama is down, your question doesn't stay stuck in the history.

## Files to read, in order

1. `src/harness/cli.py`: the loop you type into. `run_repl` takes `read` and `write` functions, so tests can drive it without a keyboard.
2. `src/harness/agent.py`: the history list and `ask`. About 20 lines, and the core of this step.
3. `src/harness/model.py`: the only file that talks HTTP. `ChatModel` is a small protocol, so tests use `tests/fakes.py::FakeModel` instead.

## Things to try

```bash
uv run harness
```

- Say "my name is Bilal", then ask "what is my name?". It remembers.
- Type `/reset`, then ask again. It doesn't. You cleared the list.
- Stop Ollama (`sudo systemctl stop ollama`), ask something, and see the hint. Start it again with `sudo systemctl start ollama`.
- Want to see the list? Add `print(self.messages)` at the end of `Agent.ask` and run again.
