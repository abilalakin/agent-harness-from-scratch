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
