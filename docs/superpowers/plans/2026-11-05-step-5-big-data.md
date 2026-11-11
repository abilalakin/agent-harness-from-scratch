# Step 5: Big Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The agent knows when it sees only part of the data, can ask for the next part, can search instead of reading everything, and keeps the conversation inside the 8192-token context window. Success test: "does every invoice PDF match the database?" gets the right answer (INV-2026-0003's PDF is 100.00 EUR higher).

**Architecture:** Partial results start with a `[...]` note that gives real numbers and the next step. `read_excel` pages by row; `run_sql` counts all rows. A new `search_files` tool returns only matching lines with their location. A new `context.py` estimates tokens and, before each model call, shortens old tool results (then drops old turns) to fit a budget. The agent loop calls it; nothing else changes shape.

**Tech Stack:** No new dependencies. Token count is an estimate: characters ÷ 4.

**Spec:** `docs/design.md`, step 5. Builds on steps 3–4. Observed failures that drive this step are recorded at the end of `docs/steps/03-data-tools.md`.

## Global Constraints

- A note about partial data always comes **first**, before the data, in square brackets, with real numbers and what to call next. Complete results stay as they are.
- `cap_output` stays as a safety net for any tool, with its note moved to the top.
- Messages stay plain OpenAI-format dicts. Trimming replaces a tool message's `content`; it never adds keys and never leaves an assistant `tool_calls` entry without its `tool` reply.
- Tests use `FakeModel` and never call a real model.
- Every task updates `docs/architecture.md` and `docs/steps/05-big-data.md`.
- Commits: show files and message, wait for the user's OK, then commit.

## Review Focus

1. **A partial result that looks complete.** Every way a result can be cut (`cap_output`, `run_sql` row limit, `read_excel` paging, `search_files` match limit) starts with a note saying how much was shown out of how much. → tests in 5a, 5b, 5c.
2. **Paging past the end or with odd arguments.** `start_row` beyond the last row, `0`, negative, or sent as a string `"41"`. Clear error or correct page, never a crash or an empty answer that looks like "no data". → 5b tests.
3. **Search over files that can't be searched.** `erp.db` (binary), an unreadable PDF page, empty Excel cells, a path outside `data/`. Skipped or refused cleanly. → 5c tests.
4. **Trimming that breaks the conversation.** After trimming, every assistant `tool_calls` id still has its `tool` message, the system prompt and the newest user message are always kept, and the result fits the budget. → 5d tests.
5. **One message bigger than the whole budget.** A single new tool result that alone exceeds the budget. Trimming still returns something valid (the newest messages are kept as they are, the estimate is reported honestly), and the agent doesn't loop or crash. → 5d test.

## File Map

```
src/harness/tools.py        cap_output note first (5a)
src/harness/sql_tools.py    run_sql: total row count, note first (5a)
src/harness/file_tools.py   read_excel paging; wrong-type hints; search_files (5b, 5c)
src/harness/context.py      estimate_tokens, fit_to_budget (5d, new)
src/harness/agent.py        context_window → trim before each call, context_tokens (5d)
src/harness/config.py       context_window (5d)
src/harness/cli.py          pass context_window; print context size after each answer (5d)
tests/test_tools.py, tests/test_sql_tools.py, tests/test_file_tools.py,
tests/test_context.py (new), tests/test_agent.py, tests/test_config.py, tests/test_cli.py
docs/steps/05-big-data.md, docs/architecture.md
```

---

### Task 5a: Partial results say so, first

**Files:**
- Modify: `src/harness/tools.py`, `src/harness/sql_tools.py`, `tests/test_tools.py`, `tests/test_sql_tools.py`
- Create: `docs/steps/05-big-data.md`; modify `docs/architecture.md`

**Interfaces:**
- Produces:
  ```python
  # tools.py
  def cap_output(text: str, limit: int = MAX_TOOL_OUTPUT) -> str
      # longer text → "[cut: showing the first {limit} of {len(text)} characters. "
      #               "Ask for a smaller part: one page, a row range, or a narrower query.]\n" + text[:limit]

  # sql_tools.py: run_sql output when more than MAX_ROWS rows
      # "[showing rows 1-50 of {total}. Use WHERE, GROUP BY, or LIMIT/OFFSET for other rows.]"
      # then the header line, then 50 rows. total = all rows the query returns (count the rest of the cursor;
      # the 10 s time limit still applies). Results with ≤ 50 rows are unchanged.
  ```

- [ ] **Step 1: Update the tests to the new format (they fail)**

`tests/test_tools.py` — replace the two cut tests:
```python
def test_cap_output_says_so_first():
    out = cap_output("x" * 25, limit=10)
    assert out.startswith("[cut: showing the first 10 of 25 characters.")
    assert out.endswith("\n" + "x" * 10)

def test_run_tool_call_caps_long_results():
    big = Tool("big", "", {"type": "object", "properties": {}}, lambda: "y" * 5000)
    out = run_tool_call({"big": big}, call("big", "{}"))
    assert out.startswith("[cut: showing the first 3000 of 5000 characters.")
```

`tests/test_sql_tools.py` — replace `test_more_than_max_rows_is_cut_with_hint`:
```python
def test_more_than_max_rows_says_total_first(db_path):
    lines = run_sql(db_path, "SELECT id FROM orders").splitlines()
    assert lines[0] == "[showing rows 1-50 of 200. Use WHERE, GROUP BY, or LIMIT/OFFSET for other rows.]"
    assert lines[1] == "id" and len(lines) == 2 + MAX_ROWS

def test_exactly_max_rows_has_no_note(db_path):
    lines = run_sql(db_path, f"SELECT id FROM orders LIMIT {MAX_ROWS}").splitlines()
    assert lines[0] == "id" and len(lines) == 1 + MAX_ROWS
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest -q` — Expected: the 4 tests above FAIL on the old format.
- [ ] **Step 3: Implement both changes.** Update the comment above `MAX_TOOL_OUTPUT` (it no longer says "Step 5 replaces this").
- [ ] **Step 4: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass (the MCP tests too, since the server reuses `run_sql`).
- [ ] **Step 5: Manual run.** `uv run harness`: "how many invoices are there, and list their numbers". Expected: the model reports 112, not 50. Write what happened in the step note.
- [ ] **Step 6: Docs.** Start `docs/steps/05-big-data.md` with part 5a: the step 3 failure ("50 invoices"), why the note goes first (a model reads top-down and a note after 50 rows may be cut or skipped), and why real totals beat "more rows not shown". Diagram: label the result arrow "partial? note first".
- [ ] **Step 7: Commit** (after the user's OK). Message: `feat: put partial-result notes first, with totals`

---

### Task 5b: Paging through Excel

**Files:**
- Modify: `src/harness/file_tools.py`, `tests/test_file_tools.py`, `docs/steps/05-big-data.md`

**Interfaces:**
- Produces:
  ```python
  EXCEL_PAGE_ROWS = 30
  def read_excel(data_dir: Path, path: str, sheet: str | None = None,
                 start_row: int = 1, max_rows: int = EXCEL_PAGE_ROWS) -> str
      # line 1: "Sheets: Customers"
      # line 2: "[rows {a}-{b} of {total}. Next page: start_row={b+1}]"   or   "[rows {a}-{b} of {total}, end of sheet]"
      # then "1: <header>" if start_row > 1 (so every page has the column names), then rows a..b as "{n}: c1 | c2 | ..."
      # start_row/max_rows go through int() (models send "41"); start_row < 1 or > total → ValueError naming the valid range;
      # max_rows < 1 → ValueError
  ```
  Wrong-type errors in `read_pdf` and `read_excel` reuse the `read_text` wording (`Use read_pdf for .pdf, read_excel for .xlsx, run_sql for erp.db.`), through one small helper.

- [ ] **Step 1: Write the failing tests** in `tests/test_file_tools.py` (replace `test_read_excel_lists_sheets_and_header`):

```python
EXPORT = "legacy/customers_export.xlsx"

def test_read_excel_first_page_says_where_next_page_starts(data_dir):
    lines = read_excel(data_dir, EXPORT).splitlines()
    assert lines[0] == "Sheets: Customers"
    assert lines[1] == "[rows 1-30 of 56. Next page: start_row=31]"
    assert lines[2].startswith("1: Cust Name | E-Mail") and lines[-1].startswith("30: ")

def test_read_excel_last_page_repeats_header_and_says_end(data_dir):
    lines = read_excel(data_dir, EXPORT, start_row="41").splitlines()   # a string, as models send it
    assert lines[1] == "[rows 41-56 of 56, end of sheet]"
    assert lines[2].startswith("1: Cust Name") and lines[3].startswith("41: ") and lines[-1].startswith("56: ")

def test_read_excel_max_rows(data_dir):
    assert read_excel(data_dir, EXPORT, start_row=10, max_rows=5).splitlines()[1] == "[rows 10-14 of 56. Next page: start_row=15]"

@pytest.mark.parametrize("start_row", [0, -1, 57, 99])
def test_read_excel_start_row_out_of_range(data_dir, start_row):
    with pytest.raises(ValueError, match="between 1 and 56"):
        read_excel(data_dir, EXPORT, start_row=start_row)

def test_every_excel_row_is_reachable(data_dir):
    seen, start = set(), 1
    while True:
        out = read_excel(data_dir, EXPORT, start_row=start)
        seen |= {int(line.split(":")[0]) for line in out.splitlines()[2:]}
        if "end of sheet" in out.splitlines()[1]:
            break
        start = int(out.splitlines()[1].split("start_row=")[1].rstrip("]"))
    assert seen == set(range(1, 57))

@pytest.mark.parametrize("reader, path, right_tool", [
    (read_pdf, "legacy/customers_export.xlsx", "read_excel"),
    (read_excel, "invoices/INV-2026-0001.pdf", "read_pdf"),
])
def test_wrong_reader_names_the_right_tool(data_dir, reader, path, right_tool):
    with pytest.raises(ValueError, match=right_tool):
        reader(data_dir, path)
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest tests/test_file_tools.py -q` — Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** Use the sheet's `max_row` for the total. Write the row formatting as a plain `for` loop (the old one-line comprehension was hard to read). Add `start_row` and `max_rows` to the `read_excel` tool schema, with descriptions that say "use the start_row from the [rows ...] note".
- [ ] **Step 4: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Manual run.** "how many new customers are in the legacy export that are not in the database?" Expected: `read_excel` called with `start_row=31` (and maybe 61-style errors handled). Write down whether it pages through and what it concludes.
- [ ] **Step 6: Docs.** Step note part 5b: paging, why every page repeats the header, why the note says the exact `start_row` to use next (the model copies it), and the "every row is reachable" test.
- [ ] **Step 7: Commit** (after the user's OK). Message: `feat: page through Excel sheets`

---

### Task 5c: Search instead of reading everything

**Files:**
- Modify: `src/harness/file_tools.py`, `src/harness/agent.py`, `tests/test_file_tools.py`, `docs/steps/05-big-data.md`, `docs/architecture.md`

**Interfaces:**
- Produces:
  ```python
  MAX_MATCHES = 30
  def search_files(data_dir: Path, query: str, path: str = ".") -> str
      # case-insensitive substring search in every file below path:
      #   .txt .md .csv .json → by line:  "README.txt line 3: <line>"
      #   .pdf                → by line, per page:  "invoices/INV-2026-0003.pdf page 1: Total: 1234.50 EUR"
      #   .xlsx               → by row (cells joined with " | "):  "legacy/customers_export.xlsx row 12: <row>"
      #   anything else (erp.db) → skipped
      # results sorted by file, then position. More than MAX_MATCHES → first line
      #   "[showing {MAX_MATCHES} of {total} matches. Use a more specific query or a path.]"
      # no match → f"(no matches for '{query}')"; empty/whitespace query → ValueError
      # path goes through safe_path
  # make_file_tools adds a fifth tool "search_files"
  ```
  `SYSTEM_PROMPT` gains: "For questions about many files, search first instead of reading every file."

- [ ] **Step 1: Write the failing tests**

```python
def test_search_finds_every_invoice_total_with_location(data_dir):
    lines = search_files(data_dir, "total:").splitlines()
    pdf_lines = [l for l in lines if l.startswith("invoices/")]
    assert [l.split(" page")[0] for l in pdf_lines] == [f"invoices/INV-2026-000{n}.pdf" for n in range(1, 6)]
    assert all(" page 1: Total: " in l and l.endswith(" EUR") for l in pdf_lines)

def test_search_excel_rows_case_insensitive(data_dir):
    out = search_files(data_dir, "BLUE SKY", path="legacy")
    assert out and all(l.startswith("legacy/customers_export.xlsx row ") for l in out.splitlines())

def test_search_text_files_by_line(data_dir):
    assert search_files(data_dir, "SQLite database").startswith("README.txt line ")

def test_search_no_match(data_dir):
    assert search_files(data_dir, "zzz-not-there") == "(no matches for 'zzz-not-there')"

def test_search_many_matches_says_total_first(data_dir):
    first = search_files(data_dir, "info@").splitlines()[0]
    assert first.startswith(f"[showing {MAX_MATCHES} of ") and "matches" in first

def test_search_skips_the_database_file(data_dir):
    assert "erp.db" not in search_files(data_dir, "customers")

def test_search_refuses_paths_outside(data_dir):
    with pytest.raises(ValueError, match="outside the data folder"):
        search_files(data_dir, "x", path="../")

def test_search_empty_query(data_dir):
    with pytest.raises(ValueError, match="empty"):
        search_files(data_dir, "  ")
```
Also update `test_list_files…`-style tool-count expectations if any test counts `make_file_tools` (none today).

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest tests/test_file_tools.py -q` — Expected: FAIL, `search_files` missing.
- [ ] **Step 3: Implement.** One small generator per file type that yields `(location, text)`; `search_files` walks the files, filters, sorts, formats. A PDF page whose text can't be extracted yields nothing.
- [ ] **Step 4: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Manual run.** "which files mention Blue Sky?" and "list the total of every invoice PDF". Expected: `search_files` calls instead of five `read_pdf` calls. Note what happens.
- [ ] **Step 6: Docs.** Step note part 5c: search as the way to handle many files (grep, not read), location in every match so the model can follow up with `read_pdf page=` or `read_excel start_row=`, why the database is left to SQL. Diagram: `search_files` next to the file tools.
- [ ] **Step 7: Commit** (after the user's OK). Message: `feat: add search_files across text, PDF and Excel`

---

### Task 5d: Keep the conversation inside the context window

**Files:**
- Create: `src/harness/context.py`, `tests/test_context.py`
- Modify: `src/harness/agent.py`, `src/harness/config.py`, `src/harness/cli.py`, `tests/test_agent.py`, `tests/test_config.py`, `tests/test_cli.py`, `docs/steps/05-big-data.md`, `docs/architecture.md`

**Interfaces:**
- Consumes: `Message` (step 1).
- Produces:
  ```python
  # context.py
  CHARS_PER_TOKEN = 4
  REPLY_RESERVE = 2000          # tokens left free for the model's answer (Qwen3 thinks out loud)
  KEEP_RECENT_TOOL_RESULTS = 2  # never shorten the newest two tool results
  def estimate_tokens(messages: list[Message], tools: list[dict] | None = None) -> int
      # len(json.dumps(messages) + json.dumps(tools or [])) // CHARS_PER_TOKEN
  def fit_to_budget(messages: list[Message], budget: int) -> tuple[list[Message], int]
      # returns (new list, number of changes); never mutates the input.
      # stage 1: oldest-first, replace the content of tool messages (except the newest KEEP_RECENT_TOOL_RESULTS)
      #          with "[old result removed to save space: {name}({arguments})]", name/arguments taken from the
      #          assistant tool_call with the same id (arguments cut to 80 chars); stop once under budget.
      # stage 2: if still over, drop whole old turns (a user message up to the next user message),
      #          oldest first, never the system message and never the turn holding the newest user message.
      # if still over after both: return what's left (it can't shrink further without breaking the turn).

  # config.py: Settings gains
      context_window: int = 8192     # HARNESS_CONTEXT_WINDOW; must match OLLAMA_CONTEXT_LENGTH

  # agent.py
  class Agent:
      def __init__(..., context_window: int | None = None): ...
          # None = no trimming (keeps all earlier tests unchanged)
      context_tokens: int          # estimate sent on the most recent model call, 0 before the first
      # in ask(), before each model.complete:
      #   budget = context_window - REPLY_RESERVE - estimate_tokens([], schemas)
      #   turn, changes = fit_to_budget(turn, budget); self.context_tokens = estimate_tokens(turn, schemas)
      #   if changes and self.on_trim: self.on_trim(changes)
      on_trim: Callable[[int], None] | None   # constructor argument, default None

  # cli.py
      # main passes context_window=settings.context_window and on_trim printing
      #   "  [context] shortened {n} old message(s) to fit"
      # run_repl prints "  [context ~{agent.context_tokens} of {window} tokens]" after each answer
      #   when the agent has a context_window
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_context.py` (helpers: `tool_turn(i, size)` builds `user`, `assistant` with one tool call id `c{i}` named `read_pdf` with arguments `{"path": "f{i}.pdf"}`, `tool` reply of `size` characters, final `assistant`):
```python
def test_estimate_is_chars_over_four():
    assert estimate_tokens([{"role": "user", "content": "x" * 400}]) in range(100, 115)

def test_under_budget_unchanged():
    msgs = [SYSTEM] + tool_turn(1, 100)
    assert fit_to_budget(msgs, 10_000) == (msgs, 0)

def test_shortens_oldest_tool_results_first_and_keeps_newest_two():
    msgs = [SYSTEM] + tool_turn(1, 4000) + tool_turn(2, 4000) + tool_turn(3, 4000) + tool_turn(4, 400)
    out, changes = fit_to_budget(msgs, 2500)
    contents = {m["tool_call_id"]: m["content"] for m in out if m["role"] == "tool"}
    assert contents["c1"] == '[old result removed to save space: read_pdf({"path": "f1.pdf"})]'
    assert contents["c3"] == "x" * 4000 and contents["c4"] == "x" * 400   # newest two kept
    assert changes >= 1 and estimate_tokens(out) <= 2500

def test_drops_old_turns_when_shortening_is_not_enough():
    msgs = [SYSTEM] + [m for i in range(1, 30) for m in plain_turn(i, 400)]    # no tool results, just chat
    out, _ = fit_to_budget(msgs, 1000)
    assert out[0] == SYSTEM and out[-2:] == msgs[-2:] and estimate_tokens(out) <= 1000

def test_never_leaves_a_tool_call_without_its_result():
    msgs = [SYSTEM] + [m for i in range(1, 8) for m in tool_turn(i, 3000)]
    out, _ = fit_to_budget(msgs, 1500)
    call_ids = {c["id"] for m in out if m["role"] == "assistant" for c in m.get("tool_calls", [])}
    result_ids = {m["tool_call_id"] for m in out if m["role"] == "tool"}
    assert call_ids == result_ids

def test_one_huge_newest_result_is_kept_and_does_not_crash():
    msgs = [SYSTEM] + tool_turn(1, 50_000)
    out, _ = fit_to_budget(msgs, 1000)
    assert out[0] == SYSTEM and any(m["role"] == "tool" and len(m["content"]) == 50_000 for m in out)

def test_input_list_is_not_changed():
    msgs = [SYSTEM] + tool_turn(1, 4000) + tool_turn(2, 4000) + tool_turn(3, 4000)
    before = copy.deepcopy(msgs)
    fit_to_budget(msgs, 1500)
    assert msgs == before
```

`tests/test_agent.py`:
```python
def test_agent_trims_before_calling_model_and_reports_it():
    # 3 tool calls returning 4000 chars each, then a final answer; context_window small enough to force trimming
    trims = []
    agent = Agent(model, tools=[big_tool], context_window=REPLY_RESERVE + 1800, on_trim=trims.append)
    agent.ask("go")
    last_sent = model.calls[-1]["messages"]
    assert any("[old result removed to save space" in (m.get("content") or "") for m in last_sent)
    assert trims and agent.context_tokens > 0

def test_agent_without_context_window_never_trims():
    # same model and tools, no context_window → every tool result reaches the model in full
```

`tests/test_config.py`: `load_settings({}).context_window == 8192`; `HARNESS_CONTEXT_WINDOW=4096` → 4096.

`tests/test_cli.py`: with `Agent(FakeModel(...), context_window=8192)`, the output after an answer contains `"[context ~"` and `"of 8192 tokens]"`; with no context window it doesn't.

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest -q` — Expected: new tests FAIL (`harness.context` missing, new arguments missing).
- [ ] **Step 3: Implement `context.py`.** Two stages, each a plain loop. A short comment explains why tool results go first (they're the biggest and the model already used them) and why turns are dropped whole (half a turn breaks the tool-call pairing).
- [ ] **Step 4: Wire into `Agent`, `Settings`, the CLI.**
- [ ] **Step 5: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.
- [ ] **Step 6: Manual runs.**
  1. The success test: `printf 'does every invoice PDF match the database? compare the totals\n/exit\n' | uv run harness`. Expected: `search_files` (or `read_pdf`) for the totals, `run_sql` for the database totals, and the answer names INV-2026-0003 as 100.00 EUR off. Write down exactly what happens, success or not.
  2. A long session that forces trimming: read the contract, both pages, then the Excel sheet page by page, then ask about something from the start. Expected: `[context] shortened ...` lines, the context number stays under 8192, and note what the model still remembers.
- [ ] **Step 7: Docs.** Step note part 5d: what the context window is, why the harness (not Ollama) must manage it (Ollama silently drops the oldest text, including the system prompt), the two trimming stages, the estimate vs real token counts, and the result of the success test. Diagram: a `context.fit_to_budget` box between `Agent` and `OpenAIChatModel`.
- [ ] **Step 8: Commit** (after the user's OK), then push. Message: `feat: keep the conversation inside the context window`
