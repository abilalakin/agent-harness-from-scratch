# Step 3: Data Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fake ERP practice data, plus tools that let the agent read files (text, PDF, Excel) and query the database, locked to `data/` and read-only.

**Architecture:** A generator script writes all practice data into `data/` from a fixed seed. File tools and SQL tools are built by factory functions that bind the data folder or database path, and return ordinary `Tool`s from step 2. `run_tool_call` cuts every tool result to a fixed size, so one big file can't fill the 8192-token context.

**Tech Stack:** Python ≥ 3.12, `sqlite3` (built in), `pypdf` (read PDFs), `fpdf2` (write the fake PDFs), `openpyxl` (read and write Excel).

**Spec:** `docs/design.md`, step 3. Builds on steps 0–2 (`docs/superpowers/plans/2026-11-03-steps-0-2-setup-chat-tools.md`).

## Global Constraints

- File tools only open files inside the data folder. Paths that lead outside it are refused.
- The database opens in read-only mode. A `DELETE` or `UPDATE` from the model cannot run.
- No real company data. Everything in `data/` is generated.
- Every tool result passes through `cap_output` (3000 characters). Proper paging waits for step 5.
- Messages stay plain OpenAI-format dicts. Tests use `FakeModel` and never call a real model.
- Every task updates `docs/architecture.md` and `docs/steps/03-data-tools.md`.
- Commits: show files and message, wait for the user's OK, then commit (signed, repo-local identity).

## Review Focus

1. **Path escape.** `../../.ssh/id_ed25519`, an absolute path like `/etc/passwd`, or a symlink inside `data/` pointing outside. All refused with a clear error. → Task 3b tests.
2. **Writes through SQL.** `DELETE`, `UPDATE`, `DROP`, two statements in one call, or `ATTACH` of another file. All refused, and the data is unchanged afterwards. → Task 3c tests.
3. **Huge results.** A long PDF, the whole Excel sheet, `SELECT * FROM orders`. Cut with a note that tells the model how to ask for less. → Task 3b (`cap_output`) and 3c (row limit) tests.
4. **Wrong tool for the file type.** `read_text` on a `.pdf`, `.xlsx` or `.db`. The error names the right tool. → Task 3b test.
5. **Data not made yet.** A fresh clone has no `data/`. The CLI says to run `uv run make-data`, and tools give the same hint instead of a confusing error. → Task 3b test.

## File Map

```
pyproject.toml                    + pypdf, fpdf2, openpyxl; script make-data (3a)
.gitignore                        + data/ (3a)
src/harness/config.py             + data_dir (3a)
src/harness/practice_data.py      generator + make-data entry point (3a)
src/harness/tools.py              + cap_output, applied in run_tool_call (3b)
src/harness/file_tools.py         safe_path, list/read tools, make_file_tools (3b)
src/harness/sql_tools.py          read-only connect, describe_tables, run_sql, make_sql_tools (3c)
src/harness/agent.py              system prompt mentions the data (3b)
src/harness/cli.py                wires the new tools, missing-data hint (3b, 3c)
tests/conftest.py                 session fixture: practice data in a temp folder (3a)
tests/test_practice_data.py       (3a)
tests/test_file_tools.py          (3b)
tests/test_sql_tools.py           (3c)
docs/steps/03-data-tools.md       grows across 3a–3c
```

Ruling (spec leaves it to the builder): `data/` is generated, so it is git-ignored. `uv run make-data` rebuilds it, the same every time.

---

### Task 3a: Practice data

**Files:**
- Create: `src/harness/practice_data.py`, `tests/conftest.py`, `tests/test_practice_data.py`, `docs/steps/03-data-tools.md`
- Modify: `pyproject.toml`, `.gitignore`, `src/harness/config.py`, `tests/test_config.py`, `docs/architecture.md`

**Interfaces:**
- Consumes: `Settings`, `load_settings` (step 0).
- Produces:
  ```python
  # config.py: Settings gains
      data_dir: Path = Path("data")        # from HARNESS_DATA_DIR

  # practice_data.py
  INVOICE_PDF_COUNT = 5
  def invoice_number(n: int) -> str          # f"INV-2026-{n:04d}"
  def make_all(data_dir: Path, seed: int = 42) -> None
      # deletes and rewrites everything below; same seed → same data
  def main() -> None                         # script `make-data`: make_all(load_settings().data_dir), print a summary

  # tests/conftest.py
  @pytest.fixture(scope="session")
  def data_dir(tmp_path_factory) -> Path     # make_all() into a temp folder once per test run
  ```
  Files `make_all` writes:
  - `erp.db`, tables:
    - `customers(id INTEGER PRIMARY KEY, name TEXT, email TEXT, city TEXT, country TEXT, created_at TEXT)`: 50 rows
    - `products(id INTEGER PRIMARY KEY, sku TEXT, name TEXT, unit_price REAL)`: 20 rows
    - `orders(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers, order_date TEXT, status TEXT)`: 200 rows, status in `open`, `shipped`, `cancelled`
    - `order_lines(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders, product_id INTEGER REFERENCES products, quantity INTEGER, unit_price REAL)`: 1–4 lines per order
    - `invoices(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders, invoice_number TEXT, issued_at TEXT, due_at TEXT, total REAL, paid INTEGER)`: one per shipped order, numbered `invoice_number(1..)`, `total` = sum of its lines rounded to 2 decimals, `due_at` = issued + 30 days
  - `invoices/<invoice_number>.pdf`: the first 5 invoices. Text includes `Invoice number: INV-2026-0001`, customer name, one line per order line, and `Total: 1234.50 EUR`. **Invoice 3's PDF total is 100.00 higher than the database**, on purpose, for the agent to find.
  - `contracts/supply-agreement.pdf`: 2 pages of plain contract text, including payment terms "net 30 days" and a late-payment penalty of 1.5% per month.
  - `legacy/customers_export.xlsx`: sheet `Customers`, header `Cust Name | E-Mail | Town | Country Code | Since`. 40 rows are existing customers written messily (case changes, `Ltd`↔`Limited`, trailing dots, extra spaces, email in capitals, dates as `2024-03-05`, `05/03/2024` or `5 Mar 2024`), 10 rows are new customers, 3 rows repeat earlier rows exactly, and 2 rows are empty.
  - `README.txt`: what each file and table is, in plain words.
  - All text is plain ASCII (fpdf2's built-in fonts are Latin-1 only).

- [ ] **Step 1: Add dependencies and settings.** Run: `uv add pypdf fpdf2 openpyxl`. Add `make-data = "harness.practice_data:main"` under `[project.scripts]`, and `data/` to `.gitignore`.

- [ ] **Step 2: Write the failing tests**

`tests/test_config.py`:
```python
def test_data_dir_default_and_override():
    assert load_settings({}).data_dir == Path("data")
    assert load_settings({"HARNESS_DATA_DIR": "/tmp/x"}).data_dir == Path("/tmp/x")
```

`tests/test_practice_data.py` (uses the `data_dir` fixture; `db(data_dir)` opens `erp.db`):
```python
def test_tables_and_row_counts(data_dir):
    counts = {t: db(data_dir).execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["customers", "products", "orders"]}
    assert counts == {"customers": 50, "products": 20, "orders": 200}

def test_one_invoice_per_shipped_order(data_dir):
    con = db(data_dir)
    shipped = con.execute("SELECT COUNT(*) FROM orders WHERE status='shipped'").fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == shipped > 0

def test_invoice_total_matches_its_lines(data_dir):
    # for every invoice: total == round(sum(quantity * unit_price) of its order's lines, 2)

def test_same_seed_same_data(tmp_path):
    make_all(tmp_path / "a"); make_all(tmp_path / "b")
    # customers table identical in both

def test_invoice_pdfs_exist_and_exactly_one_total_disagrees(data_dir):
    pdfs = sorted((data_dir / "invoices").glob("*.pdf"))
    assert [p.stem for p in pdfs] == [invoice_number(n) for n in range(1, INVOICE_PDF_COUNT + 1)]
    # read each with pypdf, parse "Total: X EUR", compare with invoices.total
    assert mismatches == [invoice_number(3)]

def test_contract_pdf_has_payment_terms(data_dir):
    text = pdf_text(data_dir / "contracts" / "supply-agreement.pdf")
    assert "net 30 days" in text and "1.5%" in text

def test_excel_export_is_messy_on_purpose(data_dir):
    rows = list(openpyxl.load_workbook(data_dir / "legacy" / "customers_export.xlsx").active.values)
    assert rows[0] == ("Cust Name", "E-Mail", "Town", "Country Code", "Since")
    data = rows[1:]
    assert len(data) == 55                                         # 40 + 10 + 3 + 2 empty
    assert sum(1 for r in data if all(c in (None, "") for c in r)) == 2
    names = {r[0] for r in con.execute("SELECT name FROM customers")}
    # at least 10 Excel names are not in the DB as written, but match a DB name after
    # normalize(): lowercase, drop punctuation, collapse spaces, "limited" -> "ltd"

def test_readme_lists_the_files(data_dir):
    text = (data_dir / "README.txt").read_text()
    assert all(name in text for name in ["erp.db", "invoices/", "contracts/", "legacy/"])
```

- [ ] **Step 3: Run and see them fail.** Run: `uv run pytest -q` — Expected: FAIL, `harness.practice_data` missing and `data_dir` not on `Settings`.

- [ ] **Step 4: Add `data_dir` to `Settings`, then implement `practice_data.py`.** Use `random.Random(seed)`, never the global `random`. Company names come from short fixed word lists combined (e.g. `["Atlas", "Northwind", "Blue Sky", ...]` × `["Ltd", "GmbH", "Aero", "Logistics", ...]`). Keep the file readable top to bottom: one function per output file (`_make_db`, `_make_invoice_pdfs`, `_make_contract_pdf`, `_make_excel`, `_make_readme`).

- [ ] **Step 5: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 6: Run the script.** Run: `uv run make-data && ls -R data | head -20` — Expected: a short summary, then `erp.db`, `README.txt`, `invoices/` (5 PDFs), `contracts/`, `legacy/`. `git status` doesn't list `data/`.

- [ ] **Step 7: Docs.** Diagram: a `data/` box (`erp.db`, PDFs, Excel, README) next to the harness, not connected yet. Start `docs/steps/03-data-tools.md`: what's in the practice data, why it's fake and seeded, the planted problems (invoice 3, the messy Excel) and why they're there.

- [ ] **Step 8: Commit** (after the user's OK). Message: `feat: add practice data generator`

---

### Task 3b: File tools

**Files:**
- Create: `src/harness/file_tools.py`, `tests/test_file_tools.py`
- Modify: `src/harness/tools.py`, `tests/test_tools.py`, `src/harness/agent.py`, `src/harness/cli.py`, `docs/architecture.md`, `docs/steps/03-data-tools.md`

**Interfaces:**
- Consumes: `Tool`, `run_tool_call` (step 2); `data_dir` fixture, `make_all` (3a); `Settings.data_dir` (3a).
- Produces:
  ```python
  # tools.py
  MAX_TOOL_OUTPUT = 3000
  def cap_output(text: str, limit: int = MAX_TOOL_OUTPUT) -> str
      # longer text → first `limit` chars + "\n...[cut: N more characters. Ask for less, for example one page or fewer rows.]"
  # run_tool_call now returns cap_output(result) for successful tool runs

  # file_tools.py
  MISSING_DATA_HINT = "No practice data yet. Run: uv run make-data"
  def safe_path(data_dir: Path, relative: str) -> Path
      # resolve (follows symlinks); ValueError(f"path '{relative}' is outside the data folder") if not inside data_dir.resolve()
  def list_files(data_dir: Path, path: str = ".") -> str        # every file below path, one per line: "invoices/INV-2026-0001.pdf  (2 KB)"
  def read_text(data_dir: Path, path: str) -> str               # .txt .md .csv .json only
  def read_pdf(data_dir: Path, path: str, page: int | None = None) -> str   # "--- page 1 of 2 ---" before each page
  def read_excel(data_dir: Path, path: str, sheet: str | None = None) -> str
      # first line "Sheets: Customers"; then each row as cells joined by " | ", empty cells as ""
  def make_file_tools(data_dir: Path) -> list[Tool]
      # Tool fns are functools.partial(fn, data_dir); names list_files, read_text, read_pdf, read_excel
  ```
  Error texts (raised as `ValueError`, so `run_tool_call` turns them into `Error: tool '<name>' failed: ...`):
  - data folder missing → `MISSING_DATA_HINT`
  - file missing → `no file '<path>' in the data folder. Use list_files to see what exists.`
  - `read_text` on another type → `'<path>' is not a text file. Use read_pdf for .pdf, read_excel for .xlsx, run_sql for erp.db.`

- [ ] **Step 1: Write the failing tests**

`tests/test_tools.py`:
```python
def test_cap_output_short_text_unchanged():
    assert cap_output("abc", limit=10) == "abc"

def test_cap_output_cuts_and_says_how_much():
    out = cap_output("x" * 25, limit=10)
    assert out.startswith("x" * 10) and "[cut: 15 more characters" in out

def test_run_tool_call_caps_long_results():
    big = Tool("big", "", {"type": "object", "properties": {}}, lambda: "y" * 5000)
    out = run_tool_call({"big": big}, call("big", "{}"))
    assert len(out) < 3200 and "[cut: 2000 more characters" in out
```

`tests/test_file_tools.py`:
```python
def test_safe_path_allows_inside(data_dir):
    assert safe_path(data_dir, "invoices/INV-2026-0001.pdf").is_file()

@pytest.mark.parametrize("bad", ["../secret.txt", "../../.ssh/id_ed25519", "/etc/passwd", "invoices/../../x"])
def test_safe_path_refuses_outside(data_dir, bad):
    with pytest.raises(ValueError, match="outside the data folder"):
        safe_path(data_dir, bad)

def test_safe_path_refuses_symlink_leading_outside(tmp_path):
    make_all(tmp_path / "d"); (tmp_path / "secret.txt").write_text("s")
    (tmp_path / "d" / "link.txt").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(ValueError, match="outside the data folder"):
        safe_path(tmp_path / "d", "link.txt")

def test_list_files_shows_relative_paths(data_dir):
    out = list_files(data_dir)
    assert "invoices/INV-2026-0001.pdf" in out and "legacy/customers_export.xlsx" in out

def test_read_text_reads_readme(data_dir):
    assert "erp.db" in read_text(data_dir, "README.txt")

@pytest.mark.parametrize("path, tool", [("invoices/INV-2026-0001.pdf", "read_pdf"),
                                        ("legacy/customers_export.xlsx", "read_excel"),
                                        ("erp.db", "run_sql")])
def test_read_text_points_to_the_right_tool(data_dir, path, tool):
    with pytest.raises(ValueError, match=tool):
        read_text(data_dir, path)

def test_read_pdf_marks_pages_and_can_pick_one(data_dir):
    full = read_pdf(data_dir, "contracts/supply-agreement.pdf")
    assert "--- page 1 of 2 ---" in full and "--- page 2 of 2 ---" in full
    assert "--- page 2 of 2 ---" in read_pdf(data_dir, "contracts/supply-agreement.pdf", page=2)
    assert "--- page 1 of 2 ---" not in read_pdf(data_dir, "contracts/supply-agreement.pdf", page=2)

def test_read_excel_lists_sheets_and_header(data_dir):
    out = read_excel(data_dir, "legacy/customers_export.xlsx")
    assert out.splitlines()[0] == "Sheets: Customers"
    assert "Cust Name | E-Mail | Town | Country Code | Since" in out

def test_missing_file_says_use_list_files(data_dir):
    with pytest.raises(ValueError, match="Use list_files"):
        read_pdf(data_dir, "invoices/nope.pdf")

def test_missing_data_folder_gives_make_data_hint(tmp_path):
    with pytest.raises(ValueError, match="uv run make-data"):
        list_files(tmp_path / "nothing-here")

def test_tools_run_through_run_tool_call(data_dir):
    tools = {t.name: t for t in make_file_tools(data_dir)}
    out = run_tool_call(tools, {"id": "c1", "type": "function",
                                "function": {"name": "read_text", "arguments": '{"path": "../../etc/passwd"}'}})
    assert out.startswith("Error: tool 'read_text' failed:") and "outside the data folder" in out
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest -q` — Expected: FAIL, `cap_output` and `harness.file_tools` missing.

- [ ] **Step 3: Implement `cap_output` and apply it in `run_tool_call`.**

- [ ] **Step 4: Implement `file_tools.py`.** Each public function starts with `safe_path` (which also does the missing-folder check). Tool descriptions say what the tool is for and when to use another one (e.g. `read_pdf`: "Read a PDF from the data folder. Use page=N for one page of a long PDF.").

- [ ] **Step 5: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 6: Wire into the CLI and prompt.** `main` adds `make_file_tools(settings.data_dir)` to the tools, and prints `MISSING_DATA_HINT` at startup when the folder doesn't exist. `SYSTEM_PROMPT` gains one sentence: "Practice data lives in a data folder: files and an ERP database. Look before you guess."

- [ ] **Step 7: Manual run.** Run: `uv run harness`. Try: "what files are in the data folder?", "summarize the supply agreement", "what's in the legacy customer export?", "read ../../.ssh/id_ed25519". Expected: `[tool]` lines with the right tools, the last one refused. Note what the 8B model does in the step note.

- [ ] **Step 8: Docs.** Diagram: `Runner` → `file tools` → `data/` (with a "safe_path: inside data/ only" label) and `cap_output` on the way back. Step note: why every path goes through `safe_path`, what `resolve()` does about `..` and symlinks, and why outputs are cut.

- [ ] **Step 9: Commit** (after the user's OK). Message: `feat: add file tools locked to the data folder`

---

### Task 3c: SQL tool

**Files:**
- Create: `src/harness/sql_tools.py`, `tests/test_sql_tools.py`
- Modify: `src/harness/cli.py`, `docs/architecture.md`, `docs/steps/03-data-tools.md`

**Interfaces:**
- Consumes: `Tool`, `run_tool_call` (step 2); `data_dir` fixture (3a); `MISSING_DATA_HINT` (3b).
- Produces:
  ```python
  MAX_ROWS = 50
  def connect_read_only(db_path: Path) -> sqlite3.Connection
      # sqlite3.connect(f"file:{db_path}?mode=ro", uri=True); setlimit(SQLITE_LIMIT_ATTACHED, 0)
      # missing file → ValueError(MISSING_DATA_HINT)
  def describe_tables(db_path: Path) -> str     # the CREATE TABLE statement of every table
  def run_sql(db_path: Path, query: str) -> str
      # "col1 | col2" header, then rows; "(no rows)" when empty;
      # more than MAX_ROWS → first 50 plus "...[more rows not shown. Use WHERE, GROUP BY or LIMIT.]"
  def make_sql_tools(db_path: Path) -> list[Tool]   # names describe_tables, run_sql
  ```
  A new connection per call, closed after. Simple, and nothing stays open between questions.

- [ ] **Step 1: Write the failing tests** in `tests/test_sql_tools.py` (`db_path = data_dir / "erp.db"`)

```python
def test_describe_tables_shows_every_table(data_dir):
    out = describe_tables(db_path)
    for t in ["customers", "products", "orders", "order_lines", "invoices"]:
        assert f"CREATE TABLE {t}" in out

def test_select_returns_header_and_rows(data_dir):
    out = run_sql(db_path, "SELECT id, name FROM customers ORDER BY id LIMIT 2")
    lines = out.splitlines()
    assert lines[0] == "id | name" and len(lines) == 3

def test_empty_result_says_no_rows(data_dir):
    assert run_sql(db_path, "SELECT * FROM customers WHERE id = -1") == "(no rows)"

def test_more_than_max_rows_is_cut_with_hint(data_dir):
    out = run_sql(db_path, "SELECT id FROM orders")
    assert len(out.splitlines()) == 1 + MAX_ROWS + 1 and "Use WHERE, GROUP BY or LIMIT" in out

@pytest.mark.parametrize("query", ["DELETE FROM customers", "UPDATE customers SET name = 'x'",
                                   "DROP TABLE customers", "INSERT INTO products (sku) VALUES ('x')"])
def test_writes_are_refused_and_data_unchanged(data_dir, query):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        run_sql(db_path, query)
    assert run_sql(db_path, "SELECT COUNT(*) AS n FROM customers").splitlines()[1] == "50"

def test_two_statements_are_refused(data_dir):
    with pytest.raises(sqlite3.ProgrammingError):
        run_sql(db_path, "SELECT 1; DELETE FROM customers")

def test_attach_is_refused(data_dir, tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        run_sql(db_path, f"ATTACH DATABASE '{tmp_path / 'new.db'}' AS x")
    assert not (tmp_path / "new.db").exists()

def test_missing_database_gives_make_data_hint(tmp_path):
    with pytest.raises(ValueError, match="uv run make-data"):
        run_sql(tmp_path / "erp.db", "SELECT 1")

def test_write_error_reaches_model_as_text(data_dir):
    tools = {t.name: t for t in make_sql_tools(db_path)}
    out = run_tool_call(tools, {"id": "c1", "type": "function",
                                "function": {"name": "run_sql", "arguments": '{"query": "DELETE FROM orders"}'}})
    assert out.startswith("Error: tool 'run_sql' failed:") and "readonly" in out
```

- [ ] **Step 2: Run and see them fail.** Run: `uv run pytest tests/test_sql_tools.py -q` — Expected: FAIL, module missing.

- [ ] **Step 3: Implement `sql_tools.py`.** `run_sql` uses `fetchmany(MAX_ROWS + 1)` to find out whether there are more rows without reading them all. `describe_tables` reads `sql` from `sqlite_master WHERE type='table'`. The `run_sql` description tells the model to call `describe_tables` first and that the database is read-only.

- [ ] **Step 4: Run and see them pass.** Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Wire into the CLI.** `main` adds `make_sql_tools(settings.data_dir / "erp.db")`.

- [ ] **Step 6: Manual run.** Run: `uv run harness`. Try: "which 3 customers have the most unpaid invoices?", "delete all cancelled orders", "does every invoice PDF match the database?". Expected: `describe_tables` then `run_sql`; the delete is refused and the model says so. The last question needs 5 PDF reads plus SQL, and may run into the 8192-token context or `max_steps`. Write down what happens in the step note. It sets up step 5.

- [ ] **Step 7: Docs.** Diagram: `Runner` → `sql tools` → `erp.db (read-only)`. Step note: the two locks (`mode=ro` and no `ATTACH`), why the model should look at the table layout first, the row limit, and what happened with the invoice-check question.

- [ ] **Step 8: Commit** (after the user's OK), then push. Message: `feat: add read-only SQL tools`
