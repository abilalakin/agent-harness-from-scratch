# Step 3: Data tools

Step 3 has three parts: practice data (3a), file tools (3b) and SQL tools (3c).

## 3a: Practice data

### What this part teaches

An agent is only as interesting as the data it can reach. Real company data can't go in a learning repo, so `src/harness/practice_data.py` makes a small fake company: a spare-parts seller with customers, orders and invoices.

```bash
uv run make-data
```

| File | What it is |
|---|---|
| `data/erp.db` | SQLite database: `customers` (50), `products` (20), `orders` (200), `order_lines` (1 to 4 per order), `invoices` (one per shipped order) |
| `data/invoices/INV-2026-000N.pdf` | PDF copies of the first 5 invoices |
| `data/contracts/supply-agreement.pdf` | A 2-page contract with payment terms and a late-payment penalty |
| `data/legacy/customers_export.xlsx` | A customer list from an "old system" |
| `data/README.txt` | What all of the above is |

### Why it's seeded

Everything comes from `random.Random(42)`. Run `make-data` twice and you get the same data. That makes tests stable, and it means "invoice 3" means the same invoice for you, for me and for the agent.

`data/` is git-ignored. It's generated, so the script is the source of truth, not the files.

### Problems planted on purpose

Real data is never clean, and an agent that only sees clean data teaches you nothing. Two problems are hidden in it:

1. **Invoice 3's PDF disagrees with the database.** The PDF total is 100.00 EUR higher. A good agent should find this by comparing the PDFs with the `invoices` table.
2. **The Excel export is messy.** It has 55 rows: 40 existing customers written differently (`SILVERLINE LOGISTICS`, `Redwood  GmbH `, `Atlas Limited` for `Atlas Ltd`), 10 new customers, 3 exact repeats, and 2 empty rows. Dates come in three formats: `2024-03-05`, `05/03/2024` and `5 Mar 2024`. Step 7's migration is about cleaning this up with a human in the loop.

### Files to read

1. `src/harness/practice_data.py`: top to bottom, one function per output file.
2. `tests/test_practice_data.py`: what the data promises (row counts, the one wrong PDF, the messy Excel).
3. `tests/conftest.py`: the `data_dir` fixture that makes the data once per test run.

### Things to try

```bash
uv run make-data
sqlite3 data/erp.db "SELECT status, COUNT(*) FROM orders GROUP BY status"
xdg-open data/invoices/INV-2026-0003.pdf
```

## 3b: File tools

### What this part teaches

**The model can ask for any path. The harness decides what it gets.** Four tools read the data folder: `list_files`, `read_text`, `read_pdf` and `read_excel`. Each one sends the path through `safe_path` before touching the disk:

```python
root = data_dir.resolve()
target = (root / relative).resolve()
if not target.is_relative_to(root):
    raise ValueError(f"path '{relative}' is outside the data folder")
```

`resolve()` does the real work. It turns `invoices/../../x` into the real folder it points to, and it follows symlinks, so a link inside `data/` that points at your home folder is caught too. An absolute path like `/etc/passwd` replaces `root` entirely when joined, so the same check catches it. Only after the check does any file get opened.

This is the simplest kind of sandbox: **check the input before acting on it.** It works because the harness runs every tool and the model can't get around it. Step 6 needs a stronger kind, because the code it runs comes from the model.

### Tool errors that teach

A small model picks the wrong tool sometimes. When it calls `read_text` on a PDF, the error names the right tool: `Use read_pdf for .pdf, read_excel for .xlsx, run_sql for erp.db.` A missing file says `Use list_files to see what exists.` An error that tells the model what to do next works far better than a bare "failed".

### Cutting long results

The model sees 8192 tokens in total. A whole PDF or Excel sheet could fill that by itself. So `run_tool_call` now passes every result through `cap_output`, which keeps the first 3000 characters and adds a note like `...[cut: 2140 more characters. Ask for less, for example one page or fewer rows.]`. That's why `read_pdf` takes a `page`. It's a blunt fix. Step 5 does it properly.

### Files to read, in order

1. `src/harness/file_tools.py`: `safe_path` first, then the four tools, then `make_file_tools`.
2. `src/harness/tools.py`: `cap_output`, and the one line in `run_tool_call` that uses it.
3. `tests/test_file_tools.py`: the escape attempts (`../`, `/etc/passwd`, a symlink) that must fail.

`make_file_tools` uses `functools.partial` to fix the data folder into each function. The model only sees `path` (and `page` or `sheet`). It can't choose a different data folder.

### Things to try

```bash
uv run harness
```

- "what files are in the data folder?"
- "summarize the supply agreement in 3 bullet points"
- "what is in the legacy customer export? describe the problems you see in it"
- "read the file ../../.ssh/id_ed25519": refused.

### What we saw with qwen3:8b

- **"what files are in the data folder?"**: one `list_files` call and a correct list.
- **"summarize the supply agreement"**: it read **only page 1** (`page: 1`), so the summary covers scope, prices and delivery and misses the payment terms on page 2. The whole contract is about 1000 characters and would have fit. The `page` option made the model cautious in the wrong place.
- **"problems in the legacy export"**: it found the mixed date formats, the mixed-case country codes, the lowercase towns and the **empty rows 12 and 32**, by row number, which is exactly why `read_excel` numbers rows. But:
  - the sheet is about 4200 characters, so `cap_output` cut it at row 41. The model never said it only saw part of the file.
  - it called "Blue Sky Ltd" and "Blue Sky GmbH" duplicates. They are two different companies. The real duplicates (exact repeats, `Atlas Limited` vs `Atlas Ltd`) it missed.
- **"read ../../.ssh/id_ed25519"**: the model **refused by itself and never called a tool**. Good manners, but not security. A different model, or a cleverer prompt, might call `read_text` anyway. The check in `safe_path` is what actually protects the file, and `tests/test_file_tools.py` proves it works whatever the model decides.

Two lessons for later steps: a model doesn't notice a cut result unless it's told loudly (step 5), and spotting duplicates by eye is not reliable (step 7 computes a score instead).
