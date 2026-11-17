# Step 7: Code Execution in a Sandbox - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `run_python` tool: the model writes a short script, the harness runs it and returns stdout, stderr and the files it wrote. First with plain `subprocess`, to see the danger. Then inside `bwrap`, where the same escapes fail. Then measured with the step 6 evals.

**Architecture:** One new module, `src/harness/code_tools.py`. `run_python(data_dir, code, sandbox)` writes nothing itself: it builds a command (plain Python, or Python inside `bwrap`), runs it with `subprocess.run` under a time limit and a memory limit, and formats the result. The script's working directory is the data folder, so the relative paths the model already knows (`invoices/INV-2026-0001.pdf`) work unchanged, and anything it writes goes to `out/` inside the data folder, where the file tools can read it back. `HARNESS_SANDBOX` picks the mode: `bwrap` (default), `none` (7a, the unsafe one), `off` (no tool at all, for the eval comparison).

**Tech Stack:** `bubblewrap` 0.12 (installed), `subprocess`, `resource.setrlimit`. New dependency: `pandas`.

**Spec:** `docs/design.md`, step 7 (7a, 7b) and the "Sandboxing" decision. The step 6 evals (`docs/steps/06-evals.md`) measure it: the two Excel tasks failed 0 of 5 at step 6.

## Global Constraints

- The sandbox facts, from a spike on 2026-11-16: `bwrap --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin --proc /proc --dev /dev --tmpfs /tmp --ro-bind ~/.local/share/uv/python <same> --ro-bind <repo>/.venv <same> --ro-bind <data> /sandbox/data --bind <data>/out /sandbox/data/out --unshare-all --die-with-parent --new-session --clearenv --setenv HOME /tmp --setenv OPENBLAS_NUM_THREADS 1 --setenv OMP_NUM_THREADS 1 --chdir /sandbox/data -- <repo>/.venv/bin/python -I -c <code>`. The venv's `python` is a symlink into uv's Python folder, so that folder must be mounted at its real path. Memory limit: `RLIMIT_AS` of 1 GiB set in `preexec_fn`, inherited by the script. Pandas needs the thread caps to import under 1 GiB.
- Limits: `TIMEOUT_SECONDS = 30`, `MEMORY_LIMIT_BYTES = 1 GiB`. `run_python` cuts stdout and stderr each to `MAX_TOOL_OUTPUT // 2` with `cap_output`, so the whole result fits the tool cap and `run_tool_call` never adds a second cut note.
- The script runs with `python -I` (isolated: no `PYTHONPATH`, no user site, no current-directory import), in both modes.
- The output folder is `data/out/`. It is created if missing. It is not cleared between runs, so the model can build on earlier results and the file tools can read them. It is git-ignored with the rest of `data/`.
- Messages, tools and the agent loop do not change. `run_python` is one more `Tool`.
- Tests that need `bwrap` are skipped when it is not installed (`pytest.mark.skipif(shutil.which("bwrap") is None, ...)`). Tests in `none` mode run real Python and must stay under a second each.
- Every task updates `docs/steps/07-sandbox.md`; the last task updates `docs/architecture.md` and `README.md`.
- Commits: show files and message, wait for the user's OK, then commit. One line, Conventional Commits.

## Review Focus

1. **A script that never ends** (`while True: pass`). Killed at 30 seconds, in both modes, with a result that says so and does not hang the REPL. → tests in Task 1 (none) and Task 2 (bwrap).
2. **A script that prints megabytes.** `print("x" * 10_000_000)`. The harness must not hold it all in the context: `cap_output` cuts it, and the subprocess must not block on a full pipe (`capture_output` reads both pipes, so it does not). → test in Task 1.
3. **A script that writes outside `out/`** (`data/x.txt`, `/tmp/x`, `~/x`). In `none` mode it succeeds, and the step note shows it. In `bwrap` mode `data/` is read-only and `~` is `/tmp` inside the sandbox, so nothing reaches the host. → tests in Task 1 (documents the hole) and Task 2 (closed).
4. **A script that reads the host** (`~/.ssh`, `/etc/passwd`). Same shape: works in `none`, fails in `bwrap` (the path does not exist inside). → tests in Tasks 1 and 2.
5. **`bwrap` missing or refusing to start** (not installed, or user namespaces disabled). The tool returns an error that says what to install or which setting to change, instead of a stack trace, and `HARNESS_SANDBOX=none` is named as the fallback. → test in Task 2 with a fake `bwrap` path.

## File Map

```
src/harness/code_tools.py     run_python, _plain_command, _bwrap_command, _run, make_code_tools   (Tasks 1, 2)
src/harness/config.py         sandbox: str = "bwrap"  (HARNESS_SANDBOX: bwrap | none | off)         (Task 1)
src/harness/cli.py            build_agent adds the tool unless sandbox == "off"                    (Task 1)
src/harness/evals/tasks.py    excel-duplicates task; run_python counts as honest work              (Task 3)
pyproject.toml                pandas                                                               (Task 1)
tests/test_code_tools.py, tests/test_config.py, tests/test_cli.py, tests/test_evals_tasks.py
docs/steps/07-sandbox.md, docs/architecture.md, README.md, docs/evals/
```

---

### Task 1: `run_python` with plain subprocess (7a)

**Files:**
- Create: `src/harness/code_tools.py`, `tests/test_code_tools.py`, `docs/steps/07-sandbox.md`
- Modify: `src/harness/config.py`, `src/harness/cli.py`, `pyproject.toml` (`uv add pandas`), `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `harness.tools.Tool`, `cap_output`, `MAX_TOOL_OUTPUT`; `harness.config.Settings`; `harness.cli.build_agent`.
- Produces:
  ```python
  # code_tools.py
  TIMEOUT_SECONDS = 30
  MEMORY_LIMIT_BYTES = 1024**3
  OUT_DIR = "out"          # inside the data folder
  SANDBOXES = ("bwrap", "none", "off")

  def run_python(data_dir: Path, code: str, sandbox: str = "bwrap") -> str
      # runs `code`, cwd = data_dir (or /sandbox/data inside bwrap), returns:
      #   stdout, then "[stderr]\n" + stderr when there is any, then "[exit code N]" when N != 0,
      #   then one "[wrote out/<name> (<n> KB)]" line per file in out/ that is new or changed since the run started.
      #   Empty stdout and nothing else -> "(no output)".
      #   Timeout -> "Error: the script ran longer than 30 seconds and was stopped." plus any stdout so far.
  def make_code_tools(data_dir: Path, sandbox: str) -> list[Tool]   # [] when sandbox == "off"

  # config.py
  Settings.sandbox: str = "bwrap"     # HARNESS_SANDBOX; load_settings rejects anything not in SANDBOXES
  ```
  Tool description (the model reads this): "Run a short Python script over the data folder and get its output. Use it for work that does not fit in a reply: counting, grouping, de-duplicating, comparing whole files or tables. pandas, openpyxl, pypdf and sqlite3 are available. The working directory is the data folder: open files with the same relative paths as the other tools. Write result files only to out/. Print what you want to see." Parameters: `code` (string, required).

- [ ] **Step 1: Add pandas**

Run: `uv add pandas`
Expected: `pyproject.toml` gains `pandas>=...`; `uv run python -c "import pandas"` works.

- [ ] **Step 2: Write the failing tests** in `tests/test_code_tools.py` (all in `sandbox="none"`)

```python
import pytest
from harness.code_tools import OUT_DIR, TIMEOUT_SECONDS, make_code_tools, run_python

def test_stdout_comes_back(tmp_path):
    assert run_python(tmp_path, "print(2 + 2)", sandbox="none") == "4\n"

def test_cwd_is_the_data_folder_and_files_are_readable(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    assert run_python(tmp_path, "print(open('a.txt').read())", sandbox="none") == "hello\n"

def test_stderr_and_exit_code_are_reported(tmp_path):
    out = run_python(tmp_path, "import sys; print('partial'); sys.exit(3)", sandbox="none")
    assert out.startswith("partial\n") and "[exit code 3]" in out

def test_a_crash_shows_the_traceback(tmp_path):
    out = run_python(tmp_path, "1/0", sandbox="none")
    assert "[stderr]" in out and "ZeroDivisionError" in out and "[exit code 1]" in out

def test_files_written_to_out_are_listed(tmp_path):
    code = "from pathlib import Path; Path('out/r.csv').write_text('a,b\\n1,2\\n')"
    out = run_python(tmp_path, code, sandbox="none")
    assert "[wrote out/r.csv (1 KB)]" in out and (tmp_path / OUT_DIR / "r.csv").read_text() == "a,b\n1,2\n"

def test_no_output_says_so(tmp_path):
    assert run_python(tmp_path, "x = 1", sandbox="none") == "(no output)"

def test_endless_script_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.TIMEOUT_SECONDS", 1)
    out = run_python(tmp_path, "print('start', flush=True)\nwhile True: pass", sandbox="none")
    assert out.startswith("Error: the script ran longer than 1 seconds") and "start" in out

def test_huge_output_does_not_block_or_fill_the_context(tmp_path):
    out = run_python(tmp_path, "print('x' * 10_000_000)", sandbox="none")
    assert len(out) < 4000 and out.startswith("[cut:")

def test_memory_limit_stops_a_big_allocation(tmp_path):
    out = run_python(tmp_path, "x = bytearray(2 * 1024**3); print('allocated')", sandbox="none")
    assert "MemoryError" in out and "allocated" not in out

def test_isolated_mode_ignores_a_planted_module(tmp_path):
    (tmp_path / "json.py").write_text("raise SystemExit('planted module imported')")
    assert run_python(tmp_path, "import json; print('ok')", sandbox="none") == "ok\n"

def test_off_means_no_tool(tmp_path):
    assert make_code_tools(tmp_path, "off") == []
    assert [t.name for t in make_code_tools(tmp_path, "none")] == ["run_python"]

# The hole. These pass in "none" mode on purpose: the step note shows them, Task 2 closes them.
def test_plain_mode_can_read_the_home_folder(tmp_path):
    out = run_python(tmp_path, "from pathlib import Path; print(sorted(p.name for p in Path.home().iterdir())[:3])", sandbox="none")
    assert out.startswith("[") and "Error" not in out

def test_plain_mode_can_write_outside_out(tmp_path):
    run_python(tmp_path, "open('escaped.txt', 'w').write('x')", sandbox="none")
    assert (tmp_path / "escaped.txt").exists()
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/test_code_tools.py -q`
Expected: FAIL with `ModuleNotFoundError: harness.code_tools`

- [ ] **Step 4: Write `code_tools.py`**: `_plain_command(data_dir, code) -> list[str]` is `[sys.executable, "-I", "-c", code]`; `_run(command, cwd, env)` does `subprocess.run(..., capture_output=True, text=True, timeout=TIMEOUT_SECONDS, preexec_fn=<setrlimit RLIMIT_AS>)` and catches `subprocess.TimeoutExpired` (its `.stdout` holds the partial output, as bytes); `run_python` snapshots `out/` (name → mtime, size) before, runs, formats as in Interfaces. `sandbox="bwrap"` raises `NotImplementedError` until Task 2. Keep the plain-mode env to `{"HOME": ..., "PATH": ...}` plus the two thread caps, so the two modes differ only in the command.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_code_tools.py -q`
Expected: 13 passed

- [ ] **Step 6: The setting and the wiring**, test first:

```python
# tests/test_config.py
def test_sandbox_setting_validated():
    assert load_settings({}).sandbox == "bwrap"
    assert load_settings({"HARNESS_SANDBOX": "none"}).sandbox == "none"
    with pytest.raises(ValueError, match="bwrap, none or off"):
        load_settings({"HARNESS_SANDBOX": "podman"})

# tests/test_cli.py
def test_build_agent_adds_run_python_unless_off(tmp_path):
    settings = Settings(data_dir=tmp_path, sandbox="none")
    assert "run_python" in build_agent(settings).tools
    assert "run_python" not in build_agent(Settings(data_dir=tmp_path, sandbox="off")).tools
```

Then `Settings.sandbox`, `load_settings` validation, and `build_agent` adding `*make_code_tools(settings.data_dir, settings.sandbox)` to the tool list.

- [ ] **Step 7: Run all tests**

Run: `uv run pytest -q`
Expected: 184 + 15 = 199 passed

- [ ] **Step 8: See the hole, live**

Run: `HARNESS_SANDBOX=none uv run harness` and ask: "Write a script that prints the names of the files in my home folder" and then "Write a script that creates a file called hello.txt one folder above the data folder". Record both results in the step note under "7a: the danger". Delete `hello.txt`.

- [ ] **Step 9: Start `docs/steps/07-sandbox.md`**: why a script tool (the Excel tasks at 0 of 5; a 56-row sheet is already too big to page by eye, a 5000-row one is hopeless), what the tool returns and why `out/` is inside `data/` (the file tools can read results), the memory and time limits, `python -I`, and the "7a: the danger" section with the two live results.

- [ ] **Step 10: Commit**

```
feat: add run_python, plain subprocess first
```

---

### Task 2: The same tool inside bwrap (7b)

**Files:**
- Modify: `src/harness/code_tools.py`, `tests/test_code_tools.py`, `docs/steps/07-sandbox.md`

**Interfaces:**
- Produces:
  ```python
  BWRAP = "bwrap"
  def _bwrap_command(data_dir: Path, code: str) -> list[str]
      # the command from Global Constraints. Paths: /usr read-only (+ the three symlinks), /proc, /dev, a fresh /tmp,
      # uv's python folder (Path(sys.executable).resolve().parents[2], i.e. the folder holding every uv python) and
      # the venv (Path(sys.prefix)) read-only at their real paths, data_dir read-only at /sandbox/data,
      # data_dir/out writable at /sandbox/data/out, --unshare-all, --die-with-parent, --new-session, --clearenv,
      # HOME=/tmp, the thread caps, --chdir /sandbox/data, then sys.executable -I -c code.
  ```
  `run_python(..., sandbox="bwrap")` uses it. When `bwrap` is not on PATH, or exits with code 1 before running Python (its own errors go to stderr and start with `bwrap:`), the result is `"Error: the sandbox could not start: <bwrap's message>. Install bubblewrap, or set HARNESS_SANDBOX=none to run scripts without a sandbox (unsafe)."`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_code_tools.py`)

```python
needs_bwrap = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not installed")

@needs_bwrap
def test_bwrap_runs_a_script_with_the_same_result(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    assert run_python(tmp_path, "print(open('a.txt').read())") == "hello\n"

@needs_bwrap
def test_bwrap_cannot_see_the_home_folder(tmp_path):
    out = run_python(tmp_path, f"import os; print(os.path.exists({str(Path.home())!r}))")
    assert out == "False\n"

@needs_bwrap
def test_bwrap_cannot_write_outside_out(tmp_path):
    out = run_python(tmp_path, "open('escaped.txt', 'w').write('x')")
    assert "Read-only file system" in out and not (tmp_path / "escaped.txt").exists()

@needs_bwrap
def test_bwrap_writes_to_out_arrive_on_the_host(tmp_path):
    out = run_python(tmp_path, "open('out/r.txt', 'w').write('x')")
    assert "[wrote out/r.txt" in out and (tmp_path / "out" / "r.txt").read_text() == "x"

@needs_bwrap
def test_bwrap_has_no_network(tmp_path):
    code = "import socket\ntry: socket.create_connection(('1.1.1.1', 53), timeout=2); print('connected')\nexcept OSError as e: print('refused', e.errno)"
    assert run_python(tmp_path, code) == "refused 101\n"

@needs_bwrap
def test_bwrap_endless_script_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.TIMEOUT_SECONDS", 1)
    assert run_python(tmp_path, "while True: pass").startswith("Error: the script ran longer")

@needs_bwrap
def test_bwrap_pandas_reads_the_practice_excel(tmp_path):
    make_all(tmp_path)
    out = run_python(tmp_path, "import pandas; print(len(pandas.read_excel('legacy/customers_export.xlsx')))")
    assert out == "55\n"

def test_missing_bwrap_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr("harness.code_tools.BWRAP", "/nonexistent/bwrap")
    out = run_python(tmp_path, "print(1)")
    assert out.startswith("Error: the sandbox could not start") and "HARNESS_SANDBOX=none" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_code_tools.py -q -k bwrap`
Expected: 8 FAIL (`NotImplementedError` / no clear error)

- [ ] **Step 3: Write `_bwrap_command` and the start-failure handling**

A `FileNotFoundError` from `subprocess.run` (no `bwrap`) and a non-zero exit whose stderr starts with `bwrap:` both become the clear error. `data_dir / "out"` is created before the run (bwrap refuses to bind a missing folder).

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -q`
Expected: 207 passed

- [ ] **Step 5: The same two scripts, live**

Run: `uv run harness` (default: bwrap). Ask the same two questions as Task 1 Step 8. Record the results under "7b: the same scripts in the sandbox". Then one useful one: "How many rows in the legacy customer export are exact duplicates of an earlier row? Ignore empty rows. Use a script." Record the script the model wrote and its answer.

- [ ] **Step 6: Step note**: what each `bwrap` flag does, in a table (mount, namespace, env, limits), why the venv and uv's python are mounted read-only at their real paths (the symlink chain), why `--die-with-parent` matters for the timeout, what is still not covered (CPU time, disk fill of `out/`, a kernel bug), and where a container would differ.

- [ ] **Step 7: Commit**

```
feat: run scripts inside a bwrap sandbox
```

---

### Task 3: Measure it (7c)

**Files:**
- Modify: `src/harness/evals/tasks.py`, `tests/test_evals_tasks.py`, `docs/steps/07-sandbox.md`, `docs/architecture.md`, `README.md`
- Create: `docs/evals/<date>-step7-*.md` (the run reports)

**Interfaces:**
- Produces, in `tasks.py`:
  - A new task `excel-duplicates`: "Ignoring empty rows, how many rows in the legacy customer export are exact duplicates of an earlier row?" → `number(3)`, trajectory `any_of(called("run_python"), paged_through_excel)`.
  - `looked_at_every_invoice` also accepts `called("run_python", "invoices")`: a script over the PDFs is honest work.
  - `excel-empty-rows` and `excel-row-count` trajectories accept `called("run_python")` as an alternative.
  - The pin test gains: the export has exactly 3 duplicate rows once empty rows are dropped (computed with openpyxl in the test).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_evals_tasks.py`)

```python
def test_a_script_over_the_invoices_counts_as_looking_at_every_invoice():
    assert looked_at_every_invoice([ToolCall("run_python", '{"code": "for p in Path(\'invoices\').glob(\'*.pdf\'): ..."}', "")])

def test_excel_tasks_accept_a_script():
    script = [ToolCall("run_python", '{"code": "import pandas"}', "")]
    assert all(task_by_id(id).trajectory(script) for id in ("excel-duplicates", "excel-empty-rows", "excel-row-count"))

def test_duplicate_count_matches_the_generated_data(tmp_path):
    make_all(tmp_path)
    rows = [r for r in openpyxl.load_workbook(tmp_path / "legacy/customers_export.xlsx").active.iter_rows(min_row=2, values_only=True) if any(r)]
    assert len(rows) - len(set(rows)) == 3
    assert len(TASKS) == 13
```

- [ ] **Step 2: Run them to see them fail**, then **Step 3: implement**, then **Step 4: `uv run pytest -q`** → 210 passed.

- [ ] **Step 5: The measurement**, in the background, about 40 minutes, the five tasks a script can help with, with and without the tool:

```
uv run evals --runs 5 --label step7-with-tool --task excel-empty-rows --task excel-row-count --task excel-duplicates --task invoice-mismatch --task unpaid-count
HARNESS_SANDBOX=off uv run evals --runs 5 --label step7-without-tool --task excel-empty-rows --task excel-row-count --task excel-duplicates --task invoice-mismatch --task unpaid-count
uv run evals --compare logs/evals/*-step7-with-tool.jsonl logs/evals/*-step7-without-tool.jsonl
```

`unpaid-count` is the control: a database question where the script should not be needed. Read the two reports and the table only. Into the step note: did the model reach for the script, did the trajectory show honest work, and did the pass counts move. Also the cost: tool calls, tokens and seconds per run, with and without.

- [ ] **Step 6: Diagram and README**: `run_python` under the Runner, a `bwrap` box around the script with its mounts (`/usr` ro, venv ro, `data/` ro, `data/out` rw, no network), a "Step 7" line under "What changed"; README step 7 row and `HARNESS_SANDBOX` in the run section.

- [ ] **Step 7: Commit**

```
feat: measure run_python with the evals
```

Then, per `AGENTS.md`: `/code-review medium`, fix with TDD, `/simplify`, one review commit, push.
