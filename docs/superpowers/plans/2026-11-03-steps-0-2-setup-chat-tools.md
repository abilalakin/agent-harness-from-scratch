# Steps 0–2: Setup, Chat Loop, Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A terminal chat program that talks to a local Qwen3 8B through Ollama, keeps history, and lets the model call two simple tools, with mistakes handled.

**Architecture:** One Python package `harness` under `src/`. Messages are plain dicts in the OpenAI chat format, so the user can read every message the model sees. The `Agent` owns the history and the tool loop. The model sits behind a small `ChatModel` protocol, so tests use a `FakeModel` and never call Ollama.

**Tech Stack:** Python ≥ 3.12, `uv`, `openai` (as an HTTP client to Ollama), `pytest`, Ollama with `qwen3:8b`.

**Spec:** `docs/design.md` (steps 0, 1 and 2 only). Steps 3–8 get their own plans later.

## Global Constraints

- No agent frameworks. The `openai` package is only used as an HTTP client.
- Default model `qwen3:8b`, default URL `http://localhost:11434/v1`. Both change through settings only.
- Messages are plain `dict`s in OpenAI chat format everywhere in the harness.
- Tests never call a real model. They use `tests/fakes.py::FakeModel`.
- Every task updates `docs/architecture.md` (Mermaid) and the step's note in `docs/steps/`.
- **Commits:** the implementer never runs `git add` or `git commit`. At each commit step, list the changed files and give the suggested message. The user stages and commits.
- Plain, simple words in all docs, comments and messages (user's global rule).

## Review Focus

1. **Ollama not running.** The CLI prints a short hint ("Is Ollama running?") and keeps going. No stack trace. → Task 1 test.
2. **Model call fails mid-turn.** History stays as it was before the turn, so the next question isn't confused by a half-finished turn. → Task 1 and Task 2b tests.
3. **Reply has only thinking.** Qwen3 may wrap reasoning in `<think>…</think>`, or get cut off inside it. The user sees the answer only, or `(no reply)`. → Task 1 tests.
4. **Sloppy tool arguments from a small model.** Numbers sent as strings, arguments sent as a dict instead of a JSON string, missing arguments, made-up tool names. Each gives the model a clear error string, never a crash. → Task 2a tests.
5. **Model calls tools forever.** The loop stops after `max_steps` and says so. → Task 2b test.

## File Map

```
CLAUDE.md                    repo rules for Claude (Task 0)
pyproject.toml               uv project, script entry `harness` (Task 0)
.gitignore                   (Task 0)
docs/architecture.md         Mermaid diagram, grows each task
docs/steps/00-setup.md       step notes: what it teaches, files to read, what to try
docs/steps/01-chat-loop.md
docs/steps/02-tools.md
src/harness/__init__.py
src/harness/config.py        Settings + load_settings (Task 0, extended 2b)
src/harness/model.py         ChatModel protocol, OpenAIChatModel, strip_thinking (Task 1)
src/harness/agent.py         Agent: history, then tool loop (Task 1, extended 2b)
src/harness/cli.py           run_repl + main (Task 1, extended 2b)
src/harness/tools.py         Tool, run_tool_call, two built-in tools (Task 2a)
tests/fakes.py               FakeModel (Task 1)
tests/test_config.py
tests/test_model.py
tests/test_agent.py
tests/test_cli.py
tests/test_tools.py
```

---

### Task 0: Setup

**Files:**
- Create: `CLAUDE.md` (it exists and is empty), `pyproject.toml`, `.gitignore`, `src/harness/__init__.py`, `src/harness/config.py`, `docs/architecture.md`, `docs/steps/00-setup.md`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Settings:
      base_url: str = "http://localhost:11434/v1"
      model: str = "qwen3:8b"
      api_key: str = "ollama"   # Ollama ignores it; the openai client needs a value

  def load_settings(env: Mapping[str, str] | None = None) -> Settings
      # reads HARNESS_BASE_URL, HARNESS_MODEL, HARNESS_API_KEY; env=None means os.environ
  ```

- [ ] **Step 1: User installs Ollama and the model** (needs sudo; the user runs these with `!`)

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama      # add the two lines below, save
#   [Service]
#   Environment="OLLAMA_CONTEXT_LENGTH=8192"
sudo systemctl restart ollama
ollama pull qwen3:8b
```

8192 tokens fits the model plus its cache in 8 GB of video memory. Step 5 deals with running out of it.

- [ ] **Step 2: Check the model runs on the GPU**

Run: `ollama run qwen3:8b "Say hi in three words." && ollama ps`
Expected: a short reply, and `ollama ps` lists `qwen3:8b` with `100% GPU`. If it shows a CPU/GPU split, lower the context to 4096 and restart.

- [ ] **Step 3: Create the uv project**

Run: `uv init --package --name harness --python 3.12 . && uv add openai && uv add --dev pytest`
Then: set `requires-python = ">=3.12"`, make sure `[project.scripts]` has `harness = "harness.cli:main"`, delete any `main.py` or sample code `uv init` made, keep the existing `CLAUDE.md`.
`.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`.

- [ ] **Step 4: Write the failing tests** in `tests/test_config.py`

```python
def test_defaults_point_at_local_ollama():
    s = load_settings({})
    assert s.base_url == "http://localhost:11434/v1"
    assert s.model == "qwen3:8b"

def test_env_overrides():
    s = load_settings({"HARNESS_BASE_URL": "http://x/v1", "HARNESS_MODEL": "m", "HARNESS_API_KEY": "k"})
    assert (s.base_url, s.model, s.api_key) == ("http://x/v1", "m", "k")
```

- [ ] **Step 5: Run and see them fail.** Run: `uv run pytest tests/test_config.py -v` — Expected: FAIL, `harness.config` not found.

- [ ] **Step 6: Implement `Settings` and `load_settings` in `src/harness/config.py`.**

- [ ] **Step 7: Run and see them pass.** Run: `uv run pytest -v` — Expected: 2 passed.

- [ ] **Step 8: Write `CLAUDE.md`** (short, plain words). It says:
  - What this repo is: a learning project, harness built by hand, one idea per step. Design in `docs/design.md`, plans in `docs/superpowers/plans/`.
  - Commands: `uv run harness`, `uv run pytest`.
  - Rules: no agent frameworks; messages are plain OpenAI-format dicts; tests use `FakeModel`, never a real model; every step updates `docs/architecture.md` and adds a note in `docs/steps/`; keep each step readable in one sitting; never run `git add`/`git commit`, suggest a message instead.

- [ ] **Step 9: Write `docs/architecture.md`** with a Mermaid `flowchart LR`: `User` → `Terminal` → `Ollama (qwen3:8b, GPU)`, and a one-line "what changed in this step" log under it. Write `docs/steps/00-setup.md`: what got installed and why, the context-length setting, and how to check the GPU is used.

- [ ] **Step 10: Commit (user).** The repo identity is already set in `.git/config` (personal noreply email, commits signed with the personal key through 1Password). Check with `git config --local --list` before the first commit.
  Files: everything above. Message: `chore: set up uv project, settings and docs`

---

### Task 1: Chat loop

**Files:**
- Create: `src/harness/model.py`, `src/harness/agent.py`, `src/harness/cli.py`, `tests/fakes.py`, `tests/test_model.py`, `tests/test_agent.py`, `tests/test_cli.py`, `docs/steps/01-chat-loop.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: `Settings`, `load_settings` (Task 0).
- Produces:
  ```python
  # model.py
  Message = dict[str, Any]
  class ChatModel(Protocol):
      def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message: ...
      # returns {"role": "assistant", "content": str | None} plus "tool_calls": list[dict] when present
  class OpenAIChatModel:
      def __init__(self, settings: Settings, client: OpenAI | None = None): ...
      def complete(self, messages, tools=None) -> Message: ...
  def strip_thinking(text: str | None) -> str | None

  # agent.py
  SYSTEM_PROMPT: str   # "You are a helpful assistant. Answer briefly."
  class Agent:
      messages: list[Message]        # starts as [{"role": "system", "content": system_prompt}]
      def __init__(self, model: ChatModel, system_prompt: str = SYSTEM_PROMPT): ...
      def ask(self, user_text: str) -> str      # "" if the model gave no content
      def reset(self) -> None                   # back to just the system message

  # cli.py
  def run_repl(agent: Agent, read: Callable[[str], str] = input, write: Callable[[str], None] = print) -> None
  def main() -> None

  # tests/fakes.py
  class FakeModel:
      def __init__(self, replies: list[Message | Exception]): ...   # returns or raises them in order
      calls: list[dict]   # each: {"messages": deep copy of messages, "tools": tools}
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_model.py`:
```python
def test_strip_thinking_removes_block():
    assert strip_thinking("<think>hmm</think>\n\nHello") == "Hello"

def test_strip_thinking_keeps_plain_text_and_none():
    assert strip_thinking("Hello") == "Hello"
    assert strip_thinking(None) is None

def test_strip_thinking_unclosed_block_is_all_thinking():
    assert strip_thinking("<think>never closed") == ""

def test_complete_converts_text_reply_and_omits_empty_tools():
    # stub client: .chat.completions.create(**kw) records kw, returns ChatCompletion.model_validate({...})
    # with message content "<think>x</think>Hi"
    msg = OpenAIChatModel(Settings(), client=stub).complete([{"role": "user", "content": "hey"}])
    assert msg == {"role": "assistant", "content": "Hi"}
    assert "tools" not in stub.last_kwargs
    assert stub.last_kwargs["model"] == "qwen3:8b"

def test_complete_converts_tool_calls():
    # stub returns one tool call: id "c1", function name "calculate", arguments '{"a": 1}'
    msg = OpenAIChatModel(Settings(), client=stub).complete([...], tools=[{"type": "function", "function": {...}}])
    assert msg["tool_calls"][0]["id"] == "c1"
    assert msg["tool_calls"][0]["function"] == {"name": "calculate", "arguments": '{"a": 1}'}
```

`tests/test_agent.py`:
```python
def test_ask_returns_reply_and_keeps_history():
    model = FakeModel([{"role": "assistant", "content": "Hi!"}, {"role": "assistant", "content": "Bilal"}])
    agent = Agent(model)
    assert agent.ask("hello") == "Hi!"
    agent.ask("my name?")
    sent = model.calls[1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]

def test_failed_call_leaves_history_unchanged():
    agent = Agent(FakeModel([RuntimeError("down")]))
    with pytest.raises(RuntimeError):
        agent.ask("hello")
    assert len(agent.messages) == 1

def test_reset_keeps_only_system_message():
    agent = Agent(FakeModel([{"role": "assistant", "content": "x"}]))
    agent.ask("a"); agent.reset()
    assert agent.messages == [{"role": "system", "content": SYSTEM_PROMPT}]
```

`tests/test_cli.py` (feed `read` from a list; collect `write` output in a list):
```python
def test_repl_prints_reply_and_exits_on_slash_exit(): ...          # inputs ["hi", "/exit"] → output contains the reply
def test_repl_empty_reply_prints_no_reply(): ...                    # model content None → output contains "(no reply)"
def test_repl_connection_error_prints_hint_and_continues(): ...     # FakeModel raises openai.APIConnectionError(request=httpx.Request("POST", "http://x")),
                                                                    # then a normal reply; output contains "Is Ollama running?" and the reply
def test_repl_eof_exits_cleanly(): ...                              # read raises EOFError → returns, no exception
def test_repl_reset_clears_history(): ...                           # "/reset" → output contains "(history cleared)", agent.messages has 1 item
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest -v` — Expected: FAIL, modules missing.

- [ ] **Step 3: Implement `strip_thinking` and `OpenAIChatModel` in `src/harness/model.py`.** `strip_thinking`: drop `<think>…</think>` (DOTALL); if an unclosed `<think>` remains, drop everything from it on; then strip whitespace. `complete`: pass `tools` only when not empty; content goes through `strip_thinking`; `tool_calls` become dicts via `model_dump()`, keeping `id`, `type`, `function.name`, `function.arguments`.

- [ ] **Step 4: Implement `Agent` in `src/harness/agent.py`.** `ask` sends history plus the new user message; only after the model returns does it append both to `self.messages`.

- [ ] **Step 5: Implement `run_repl` and `main` in `src/harness/cli.py`.** Prompt `you> `, reply lines start with `agent> `. Skip empty input. `/exit` quits, `/reset` clears. `EOFError` and `KeyboardInterrupt` print `bye` and return. `openai.APIConnectionError` → `Error: can't reach the model. Is Ollama running?`; other `openai.APIError` → `Error from model: <message>`; both continue the loop. `main` prints one line with model and URL plus the two commands, then calls `run_repl`.

- [ ] **Step 6: Run and see them pass.** Run: `uv run pytest -v` — Expected: all pass.

- [ ] **Step 7: Manual run.** Run: `uv run harness`, say "my name is Bilal", then ask "what is my name?". Expected: it remembers. Stop Ollama (`sudo systemctl stop ollama`), ask again. Expected: the hint, no stack trace. Start it again.

- [ ] **Step 8: Docs.** Diagram: `User` → `cli.run_repl` → `Agent (messages list)` → `OpenAIChatModel` → `Ollama`. `docs/steps/01-chat-loop.md`: the model has no memory, the harness resends the whole history each time; files to read in order (`cli.py`, `agent.py`, `model.py`); things to try (memory test, `/reset`, stop Ollama).

- [ ] **Step 9: Commit (user).** Files: all above. Message: `feat: add terminal chat loop with history`

---

### Task 2a: Tools module

**Files:**
- Create: `src/harness/tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `Message` (Task 1).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Tool:
      name: str
      description: str
      parameters: dict              # JSON Schema object
      fn: Callable[..., str]
      def schema(self) -> dict      # {"type": "function", "function": {"name", "description", "parameters"}}

  def run_tool_call(tools: Mapping[str, Tool], call: Message) -> str
      # call = {"id": ..., "type": "function", "function": {"name": str, "arguments": str | dict}}
      # always returns a string; never raises

  def get_current_time(timezone: str = "UTC") -> str     # ISO 8601 time in that zone
  def calculate(a: float, op: str, b: float) -> str      # op in "+", "-", "*", "/"; a and b cast with float()
  BUILTIN_TOOLS: list[Tool]                              # [get_current_time tool, calculate tool]
  ```
  Error strings (exact prefixes, the model reads them):
  - unknown tool → `Error: unknown tool '<name>'. Available tools: <comma-separated names>`
  - arguments not valid JSON → `Error: arguments are not valid JSON: <detail>`
  - wrong or missing arguments (`TypeError`) → `Error: bad arguments for '<name>': <detail>`
  - any other exception → `Error: tool '<name>' failed: <detail>`

- [ ] **Step 1: Write the failing tests** in `tests/test_tools.py`

```python
TOOLS = {t.name: t for t in BUILTIN_TOOLS}
def call(name, args): return {"id": "c1", "type": "function", "function": {"name": name, "arguments": args}}

def test_calculate_with_json_string_args():
    assert run_tool_call(TOOLS, call("calculate", '{"a": 6, "op": "*", "b": 7}')) == "42.0"

def test_calculate_accepts_dict_args_and_number_strings():
    assert run_tool_call(TOOLS, call("calculate", {"a": "6", "op": "*", "b": "7"})) == "42.0"

def test_divide_by_zero_is_tool_error():
    assert run_tool_call(TOOLS, call("calculate", '{"a": 1, "op": "/", "b": 0}')).startswith("Error: tool 'calculate' failed:")

def test_unknown_op_is_tool_error():
    assert run_tool_call(TOOLS, call("calculate", '{"a": 1, "op": "^", "b": 2}')).startswith("Error: tool 'calculate' failed:")

def test_unknown_tool_lists_available():
    out = run_tool_call(TOOLS, call("weather", "{}"))
    assert out == "Error: unknown tool 'weather'. Available tools: get_current_time, calculate"

def test_bad_json():
    assert run_tool_call(TOOLS, call("calculate", "{a: 1")).startswith("Error: arguments are not valid JSON:")

def test_missing_argument():
    assert run_tool_call(TOOLS, call("calculate", '{"a": 1}')).startswith("Error: bad arguments for 'calculate':")

def test_time_bad_timezone_is_tool_error():
    assert run_tool_call(TOOLS, call("get_current_time", '{"timezone": "Mars/Base"}')).startswith("Error: tool 'get_current_time' failed:")

def test_time_valid_timezone_returns_iso():
    datetime.fromisoformat(run_tool_call(TOOLS, call("get_current_time", '{"timezone": "Europe/Istanbul"}')))

def test_schema_shape():
    s = TOOLS["calculate"].schema()
    assert s["type"] == "function" and s["function"]["name"] == "calculate"
    assert s["function"]["parameters"]["required"] == ["a", "op", "b"]
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest tests/test_tools.py -v` — Expected: FAIL, module missing.

- [ ] **Step 3: Implement `tools.py`.** Empty-string arguments count as `{}`. `get_current_time` uses `zoneinfo.ZoneInfo`. Descriptions are one plain sentence each, written for the model.

- [ ] **Step 4: Run and see them pass.** Run: `uv run pytest -v` — Expected: all pass.

- [ ] **Step 5: Commit (user).** Files: `src/harness/tools.py`, `tests/test_tools.py`. Message: `feat: add tool definitions and safe tool runner`

---

### Task 2b: Tool loop in the agent

**Files:**
- Modify: `src/harness/agent.py`, `src/harness/cli.py`, `src/harness/config.py`, `tests/test_agent.py`, `tests/test_config.py`, `docs/architecture.md`
- Create: `docs/steps/02-tools.md`

**Interfaces:**
- Consumes: `Tool`, `run_tool_call`, `BUILTIN_TOOLS` (Task 2a); `ChatModel`, `Agent` (Task 1).
- Produces:
  ```python
  # config.py: Settings gains
      max_steps: int = 10            # from HARNESS_MAX_STEPS

  # agent.py
  SYSTEM_PROMPT  # adds: "Use the tools when they help. If a tool returns an error, fix the arguments and try again."
  class Agent:
      def __init__(self, model: ChatModel, system_prompt: str = SYSTEM_PROMPT,
                   tools: Sequence[Tool] = (), max_steps: int = 10,
                   on_tool_call: Callable[[str, str, str], None] | None = None): ...
                   # on_tool_call(name, arguments_as_text, result)
      def ask(self, user_text: str) -> str
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
def test_max_steps_default_and_override():
    assert load_settings({}).max_steps == 10
    assert load_settings({"HARNESS_MAX_STEPS": "3"}).max_steps == 3
```

`tests/test_agent.py` (helper `tool_reply(name, args, id="c1")` builds an assistant message with one tool call):
```python
def test_tool_call_then_final_answer():
    model = FakeModel([tool_reply("calculate", '{"a": 6, "op": "*", "b": 7}'),
                       {"role": "assistant", "content": "It is 42."}])
    seen = []
    agent = Agent(model, tools=BUILTIN_TOOLS, on_tool_call=lambda *a: seen.append(a))
    assert agent.ask("6 times 7?") == "It is 42."
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert agent.messages[3] == {"role": "tool", "tool_call_id": "c1", "content": "42.0"}
    assert seen == [("calculate", '{"a": 6, "op": "*", "b": 7}', "42.0")]
    assert model.calls[0]["tools"][0]["type"] == "function"

def test_tool_error_goes_back_to_model():
    model = FakeModel([tool_reply("weather", "{}"), {"role": "assistant", "content": "Sorry."}])
    Agent(model, tools=BUILTIN_TOOLS).ask("weather?")
    assert model.calls[1]["messages"][-1]["content"].startswith("Error: unknown tool 'weather'")

def test_stops_after_max_steps():
    model = FakeModel([tool_reply("calculate", '{"a": 1, "op": "+", "b": 1}', id=f"c{i}") for i in range(3)])
    out = Agent(model, tools=BUILTIN_TOOLS, max_steps=3).ask("loop")
    assert out == "Stopped after 3 tool steps without a final answer."
    assert len(model.calls) == 3

def test_no_tools_means_tools_not_sent():
    model = FakeModel([{"role": "assistant", "content": "hi"}])
    Agent(model).ask("hey")
    assert model.calls[0]["tools"] is None

def test_failure_mid_tool_loop_leaves_history_unchanged():
    model = FakeModel([tool_reply("calculate", '{"a": 1, "op": "+", "b": 1}'), RuntimeError("down")])
    agent = Agent(model, tools=BUILTIN_TOOLS)
    with pytest.raises(RuntimeError):
        agent.ask("1+1?")
    assert len(agent.messages) == 1
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest -v` — Expected: the new tests FAIL.

- [ ] **Step 3: Add `max_steps` to `Settings` and `load_settings`.**

- [ ] **Step 4: Extend `Agent.ask` into the tool loop.** Work on a copy of the history for the whole turn; replace `self.messages` with it only when the turn ends (final answer or step limit). The loop:

```
turn = messages + [user]
repeat up to max_steps:
    reply = model.complete(turn, schemas or None); turn.append(reply)
    if reply has no tool_calls: commit turn; return reply content or ""
    for each call: result = run_tool_call(...); on_tool_call(...); turn.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
commit turn; return "Stopped after {max_steps} tool steps without a final answer."
```

Earlier Task 1 tests must still pass unchanged.

- [ ] **Step 5: Wire it into `main`.** Pass `tools=BUILTIN_TOOLS`, `max_steps=settings.max_steps`, and an `on_tool_call` that prints `  [tool] name(arguments) -> result` with the result cut to 200 characters.

- [ ] **Step 6: Run and see them pass.** Run: `uv run pytest -v` — Expected: all pass.

- [ ] **Step 7: Manual run.** Run: `uv run harness`. Try: "what is 17.5 times 4?", "what time is it in Tokyo?", "what time is it in Mars/Base?". Expected: `[tool]` lines show the calls; the last one shows the error and the model either retries or says it can't. Note anything odd the 8B model does in the step note.

- [ ] **Step 8: Docs.** Diagram adds `Tools (run_tool_call)` with `get_current_time` and `calculate`, and a loop arrow `Agent ⇄ Model` labeled "until no tool calls or max_steps". `docs/steps/02-tools.md`: the model never runs anything, it only asks; the harness runs the tool and sends the result back as a `tool` message; why errors are returned as text instead of raised; files to read in order (`tools.py`, `agent.py`); the three prompts to try.

- [ ] **Step 9: Commit (user).** Files: all above. Message: `feat: add tool loop with step limit`
