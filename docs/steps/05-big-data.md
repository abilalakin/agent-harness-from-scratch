# Step 5: Big data

Real data doesn't fit in a context window. Step 5 is about working with data that is bigger than what the model can see at once. It has four parts: partial-result notes (5a), paging (5b), search (5c) and trimming the conversation (5d).

The goal for the whole step: "does every invoice PDF match the database?" gets the right answer. In step 3 the model never even compared a total.

## 5a: Partial results say so, first

### What went wrong in step 3

The model ran `SELECT invoice_number FROM invoices`. There are 112 invoices. `run_sql` showed 50 and added, at the end:

```
...[more rows not shown, only the first 50. Use WHERE, GROUP BY or LIMIT.]
```

The model answered "the database contains 50 invoices". It had been told, and still got it wrong.

### What changed

A cut result now **starts** with a note, and the note has the **real total**:

```
[showing rows 1-50 of 112. Use WHERE, GROUP BY, or LIMIT/OFFSET for other rows.]
invoice_number
INV-2026-0001
...
```

Three reasons this works better:

1. **First beats last.** A model reads top to bottom. By row 50 its attention is on the data, and a note at the end can also be cut off by another limit (it was, in step 3's review: `SELECT * FROM invoices` hit the 3000-character cut before the note).
2. **A number beats a hint.** "only the first 50" leaves the total to guess. "1-50 of 112" doesn't.
3. **Say what to do next.** `LIMIT/OFFSET` tells the model how to get the other rows.

Complete results don't change. A note on every result would be noise the model learns to skip.

`run_sql` gets the total by reading the rest of the rows without keeping them (`sum(1 for _ in cursor)`). That's cheap for this database, and the 10-second limit from step 3 still stops a query that never ends.

`cap_output`, the 3000-character safety net from step 3, puts its note first too: `[cut: showing the first 3000 of 4181 characters. ...]`.

### Files to read

1. `src/harness/sql_tools.py`: the end of `run_sql`.
2. `src/harness/tools.py`: `cap_output`.

### What we saw with qwen3:8b

- **"how many invoices are there? list their numbers"**: the model called `list_files` on `invoices/`, found 5 PDFs and answered "5 invoices". Not wrong, just a different question: invoices live in two places, 5 PDFs and 112 database rows. A vague question gets whichever source the model looks at first.
- **"how many invoices are in the ERP database? list all their numbers"**: `describe_tables`, then `SELECT COUNT(*)` (112), then `SELECT invoice_number`, which came back with `[showing rows 1-50 of 112 ...]` on top. The answer said **112** and knew the list was partial. In step 3 the same data gave "50".
- But it **didn't fetch the rest itself**. It said "the first 50 are listed above" (you never saw them: tool results go to the model, not to you) and offered to use `OFFSET`. Knowing a result is partial is step one. Acting on it without being asked is something the model still has to choose to do.

## 5b: Paging through Excel

### What went wrong in step 3

The Excel export is about 4200 characters. `cap_output` cut it at row 41, and there was no way to ask for the rest. Rows 42 to 56 could not be reached by any tool. The cut note even said "ask for fewer rows", which `read_excel` couldn't do.

### What changed

`read_excel` now returns **one page of 30 rows**, and the second line says exactly where you are and what to call next:

```
Sheets: Customers
[rows 1-30 of 56. Next page: start_row=31]
1: Cust Name | E-Mail | Town | Country Code | Since
2: SILVERLINE LOGISTICS | info@silverline-logistics.example | Paris | fr | 17 Aug 2020
...
```

Call it again with `start_row=31` and you get rows 31 to 56, ending with `[rows 31-56 of 56, end of sheet]`. Three details worth noticing:

- **The note names the exact argument to send next.** A model copies what it's given. "Next page: start_row=31" turns into `read_excel(path, start_row=31)` without the model having to count.
- **Every page repeats the header row** (`1: Cust Name | ...`). On page 2 the model would otherwise see `31: Aurora Ltd | info@... | Milan | IT | 1 Jun 2026` and have to remember which column is which.
- **`"41"` works as well as `41`.** Small models send numbers as strings about half the time. One `int()` call avoids a pointless error round-trip.

`tests/test_file_tools.py::test_every_excel_row_is_reachable` does what the model is supposed to do: start at row 1, follow the `start_row=` note until "end of sheet", and check that all 56 rows were seen. If paging ever skips or repeats a row, that test fails.

### A small fix on the side

`read_pdf` on an `.xlsx` file used to say only "is not a PDF". Now all three readers share one error that names the right tool for each file type, as `read_text` already did. An error that says what to do next is worth more than one that only says no.

### Files to read

1. `src/harness/file_tools.py`: `read_excel`, and the `_wrong_type` helper above it.
2. `tests/test_file_tools.py`: `test_every_excel_row_is_reachable`.

### What we saw with qwen3:8b

Asked "how many customers in the legacy export are new, meaning not in the ERP database? read the whole sheet", the model:

1. Guessed a file name (`legacy_customers.xlsx`), got "no file ... Use list_files", listed the files, and found the right one. The error message did its job.
2. Called `read_excel` with **`max_rows: 1000`**. The first version of 5b allowed that. The whole sheet (4213 characters) came back, the 3000-character safety net cut it at about row 41, and the paging note inside the cut text still said `[rows 1-56 of 56, end of sheet]`. **The tool contradicted itself**, and the model believed the friendlier half: it thought it had read everything.
3. Pasted the names and emails it had seen into one SQL query with `name IN (...) AND email IN (...)`. The exact strings (`'Redwood  GmbH'`, `'INFO@POLARIS-AERO.EXAMPLE'`) match nothing in the clean database, so the count was 0.
4. Concluded that **all** customers are new, and gave the number as **4213**. That's the character count from the cut note. A model under pressure will grab any number in sight.

Two fixes came out of this. `max_rows` is now capped at the page size, so `read_excel` can never return more than the safety net allows, and the two notes can't disagree. And a lesson for 5c: comparing 56 messy names against a database by eye, in one SQL `IN (...)`, is the wrong tool. Step 7 computes a match score per row instead.

The right answer, for the record: 10 new customers (plus 3 duplicate rows and 2 empty ones). Nothing in the model's run got near it.

## 5c: Search instead of reading everything

### What this part teaches

**`grep`, not `cat`.** When a question spans many files, reading each one fills the context with text the model will mostly ignore. Searching returns only the lines that matter. "What is the total of every invoice?" used to need five `read_pdf` calls, about 2500 characters. Now it's one `search_files("total:")` call that returns five lines:

```
invoices/INV-2026-0001.pdf page 1: Total: 2521.35 EUR
invoices/INV-2026-0002.pdf page 1: Total: 977.12 EUR
...
```

### Every match says where it is

Each line starts with the file and a location: `page 1` for a PDF, `row 12` for Excel, `line 3` for a text file. Those are the same units the reading tools take, so the model can follow up precisely: `read_pdf(path, page=1)`, `read_excel(path, start_row=12)`. Search finds, read confirms.

### What it doesn't search

`erp.db` is binary, and a substring search over a database is the wrong tool anyway. The tool description says so and points to `run_sql`. A tool that says what it's *not* for saves the model a wasted call.

Search results are capped at 30 matches, with the note first, like everything else in step 5: `[showing 30 of 86 matches. Use a more specific query or a path.]`.

### Files to read

1. `src/harness/file_tools.py`: the three small generators (`_text_lines`, `_pdf_lines`, `_excel_rows`) and `search_files`. One generator per file type is all the structure it needs.
2. `src/harness/agent.py`: the one new sentence in `SYSTEM_PROMPT`.

### What we saw with qwen3:8b

- **"which files mention Blue Sky?"**: one `search_files("Blue Sky")` call, then a correct answer listing four rows of the Excel export, with row numbers. No file was read in full.
- **"list the total amount of every invoice PDF"**: `list_files` on `invoices/`, then one `search_files("Total", path="invoices")` call. It narrowed the search to the folder on its own. Five totals, all correct, in two tool calls. In step 3 the same question needed five `read_pdf` calls and the model gave up before comparing anything.

Both times the model picked search without being told to. The one sentence added to the system prompt, "search first instead of reading every file", plus a tool description that says what the tool is for, was enough.
