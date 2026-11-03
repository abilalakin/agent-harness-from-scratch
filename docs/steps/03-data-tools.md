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
