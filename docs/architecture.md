# Architecture

How the harness fits together right now. This diagram changes with every step.

```mermaid
flowchart LR
    User([You]) -- types --> CLI["cli.run_repl<br/>read, print, /reset, /exit<br/>prints [tool] lines"]
    CLI -- "ask(text)" --> Agent["Agent<br/>messages: list of dicts<br/>(system, user, assistant, tool, ...)"]
    Agent -- "history + tool schemas" --> Fit["context.fit_to_budget<br/>over budget? shorten old tool<br/>results, then drop old turns"]
    Fit -- "fits in 8192 - 2000 reserve" --> Model["OpenAIChatModel<br/>reasoning → on_thinking<br/>([thinking] lines in the CLI)"]
    Model -- "HTTP POST /v1/chat/completions" --> Ollama["Ollama<br/>qwen3:8b on the GPU<br/>localhost:11434"]
    Ollama -. "answer, or tool_calls" .-> Model
    Model -. reply .-> Agent
    Agent -- "tool_calls" --> Runner["tools.run_tool_call<br/>errors become text"]
    Runner --> T1[get_current_time]
    Runner --> T2[calculate]
    Runner --> FT["file tools<br/>list_files, read_text, read_pdf,<br/>read_excel (30 rows a page),<br/>search_files (matching lines only)"]
    FT -- "safe_path:<br/>inside data/ only" --> Data
    Runner -- "HARNESS_SANDBOX=bwrap<br/>(default)" --> RP["run_python<br/>30 s, 1 GiB, python -I"]
    RP --> Bwrap
    subgraph Bwrap["bwrap sandbox (code_tools.py, step 7)"]
        Script["the model's script<br/>/usr, venv: read-only<br/>data/: read-only<br/>data/out/: writable<br/>no network, no home, fresh /tmp"]
    end
    Script -. "stdout, stderr, exit code,<br/>[wrote out/...] lines" .-> RP
    Script -- reads --> Data
    Runner -- "HARNESS_SQL_VIA=builtin<br/>(default)" --> ST["SQL tools<br/>describe_tables, run_sql<br/>max 50 rows"]
    Runner -- "HARNESS_SQL_VIA=mcp" --> MT["MCP tools<br/>mcp__erp__describe_tables,<br/>mcp__erp__run_sql"]
    MT --> Conn["McpConnection<br/>background thread,<br/>asyncio loop"]
    Conn -- "MCP over stdio<br/>(starts the subprocess)" --> McpTools
    ST -- "mode=ro,<br/>no ATTACH" --> DB[("data/erp.db<br/>read-only")]
    Runner -. "result as a tool message<br/>partial? a note comes first:<br/>[showing rows 1-50 of 112 ...]" .-> Agent
    Agent -. "final answer<br/>(or stop after max_steps)" .-> CLI

    subgraph ErpMcp["erp-mcp: separate process (mcp_server.py)"]
        McpTools["MCP tools<br/>describe_tables, run_sql<br/>(reuses sql_tools.py)"]
    end
    McpTools -- "same locks:<br/>mode=ro, no ATTACH, 10 s" --> DB
    AnyClient(["Claude Code, MCP Inspector,<br/>any MCP client"]) -- "MCP: JSON-RPC over stdio<br/>initialize, tools/list, tools/call" --> McpTools

    MakeData["uv run make-data<br/>practice_data.py, seed 42"] --> Data[("data/<br/>erp.db, invoices/*.pdf,<br/>contracts/*.pdf, legacy/*.xlsx")]

    subgraph Evals["uv run evals (evals/, step 6)"]
        Tasks["tasks.py<br/>12 questions, answer checks,<br/>trajectory checks"]
        EvRunner["runner.py<br/>fresh Agent per run,<br/>TokenCounter wraps the model,<br/>tool calls via on_tool_call"]
        Judge["judge.py<br/>a model grades free text<br/>against a rubric; checked<br/>against hand-graded answers"]
        Report["report.py<br/>4 of 5 per task, errors apart,<br/>--compare across runs"]
    end
    Tasks --> EvRunner
    EvRunner -- "ask(question), N times" --> Agent
    EvRunner --> Judge
    Judge -- "one call, no tools" --> Model
    EvRunner --> Report
    Report --> Out[("docs/evals/*.md<br/>logs/evals/*.jsonl")]
```

The file tools read the files in `data/`. The SQL tools read `erp.db`, and the database itself refuses every write. They reach the database one of two ways: built in, inside the harness process, or through the `erp-mcp` server, which the harness starts as a subprocess. To the agent, both look like normal tools.

The agent loops between the model and the tools until the model answers without asking for a tool, or until `max_steps` model calls are used up.

`run_python` runs a script the model wrote, as a separate process. By default the process lives in a bubblewrap sandbox that shows it the data folder read-only, one writable folder for results, and no network. `HARNESS_SANDBOX=none` runs it without the sandbox (for the step 7 lesson), `off` removes the tool.

The evals sit on top of all of this and change none of it. The runner builds the same agent the CLI builds, asks each question N times on a fresh agent, and measures from the outside: tool calls through the `on_tool_call` hook, tokens by wrapping the model.

## What changed

- **Step 0:** Ollama runs the model locally. No harness code yet, only settings (`config.py`) that say where the model is.
- **Step 1:** The chat loop. `Agent` keeps the history and sends all of it on every call. `OpenAIChatModel` is the only part that knows about HTTP. The CLI catches connection errors, so a stopped Ollama gives a hint instead of a crash.
- **Step 2:** Tools. The agent sends tool schemas with each call. When the model replies with `tool_calls`, the agent runs them through `run_tool_call` and appends each result as a `tool` message, then calls the model again. Mistakes come back to the model as `Error: ...` text. `max_steps` stops endless loops.
- **Step 3a:** Practice data. `uv run make-data` writes a fake ERP database, invoice PDFs, a contract PDF and a messy Excel export into `data/`. Nothing reads it yet.
- **Step 3b:** File tools. Four tools read text, PDF and Excel files. Every path goes through `safe_path`, so nothing outside `data/` can be opened. `run_tool_call` now cuts every result to 3000 characters, so one big file can't fill the context.
- **Step 3c:** SQL tools. `describe_tables` shows the table layout, `run_sql` runs one query. The database is opened read-only and can't attach other files, so writes fail inside SQLite itself. Results stop at 50 rows.
- **Step 4a:** An MCP server, `erp-mcp`. It offers the same two SQL tools to any MCP client, as a separate program talking JSON-RPC over stdin/stdout. Our harness doesn't use it yet.
- **Step 4b:** The harness as an MCP client. With `HARNESS_SQL_VIA=mcp` it starts `erp-mcp`, asks for its tools, and wraps each one as a normal `Tool` named `mcp__erp__<tool>`. `McpConnection` runs the async MCP client on a background thread, so the rest of the harness stays synchronous. The agent loop didn't change.
- **Step 5a:** Partial results say so first. `run_sql` counts every row and starts a cut result with `[showing rows 1-50 of 112 ...]`. `cap_output` (the 3000-character safety net) also puts its note at the top.
- **Step 5b:** `read_excel` returns 30 rows at a time and says which `start_row` to call next. `max_rows` can't go above the page size.
- **Step 5c:** `search_files` finds a word across text, PDF and Excel files and returns only the matching lines, each with its file and page or row. The model can search five PDFs in one call instead of reading them one by one.
- **Step 5d:** `context.py` estimates the size of each request (characters ÷ 4) and trims it to fit before every model call: old tool results become one-line stubs, then whole old turns are dropped. The newest turn and the system prompt always stay. The CLI shows `[context ~N of 8192 tokens]` after each answer.
- **Step 6:** Evals. `uv run evals` runs twelve questions over the practice data N times each and writes a report: `4 of 5` per task, a trajectory column for what the agent did (did it read all five PDFs?), errors counted apart from wrong answers, and the first failed answer quoted. A model judge grades the free-text task against a rubric, and is checked against six hand-graded answers first. `--compare` puts several runs side by side, one variable per run: model, prompt, context window, commit.
- **Step 7:** `run_python`. The model writes a short script; the harness runs it with the data folder as its working directory, under a 30-second and 1 GiB limit, and returns what it printed and wrote to `data/out/`. 7a ran it as a plain subprocess and showed the script listing the home folder and writing outside the data folder. 7b runs it inside `bwrap`: `/usr`, the venv and `data/` read-only, `data/out/` writable, no network, no home. The same scripts now fail. The model cannot choose the mode: the tool's only argument is the code.
