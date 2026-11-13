# Evals: baseline

- date: 2026-11-13
- label: baseline
- model: qwen3:8b
- prompt: default
- context_window: 8192
- runs: 5
- commit: 2663b14

| task | passed | trajectory | tool calls | tokens | seconds |
|---|---|---|---|---|---|
| invoice-count | 5 of 5 | 5 of 5 | 2 | 3216 | 14 |
| unpaid-count | 5 of 5 | 5 of 5 | 2 | 3524 | 18 |
| top-customer | 5 of 5 | 5 of 5 | 2 | 3562 | 20 |
| priciest-product | 5 of 5 | 5 of 5 | 2 | 3545 | 16 |
| german-customers | 5 of 5 | 5 of 5 | 2 | 3535 | 14 |
| invoice-3-pdf-total | 5 of 5 | 5 of 5 | 1 | 2356 | 32 |
| invoice-mismatch | 4 of 5 | 4 of 5 | 4 | 7502 | 136 |
| contract-penalty | 3 of 5 | 5 of 5 | 4 | 6267 | 50 |
| contract-notice | 1 of 5 | 5 of 5 | 4 | 5642 | 25 |
| excel-empty-rows | 0 of 5 | 0 of 5 | 2 | 4039 | 26 |
| excel-row-count | 0 of 5 | 1 of 5 | 3 | 4520 | 60 |
| contract-summary | 0 of 5 | 0 of 5 | 0 | 982 | 2 |

**Total: 38 of 60 runs passed, trajectory ok in 45 of 60**

## Failures

**invoice-mismatch** (run 4):
> The first two invoices checked (INV-2026-0001 and INV-2026-0002) match their ERP totals. To ensure all invoices are verified, a full comparison of every PDF total with the ERP database would be needed. Since this requires checking all 112 invoices, a script or automated tool would be necessary to co

**contract-penalty** (run 3):
> The penalty for late payments in the supply agreement is not found in the data folder files or the ERP database tables (customers, invoices, orders, etc.). Check signed contracts in the data folder manually or contact the relevant department for details.

**contract-notice** (run 2):
> The question about the supply agreement's notice period couldn't be answered with the available tools. The search for "days notice" yielded no results, and the ERP database tables (customers, invoices, orders, etc.) don't include supply agreement terms. Check if the agreement file exists in the data

**excel-empty-rows** (run 1):
> The `legacy_customer_export` table does not exist in the ERP database. However, checking the `customers` table, there are **0 rows** with an empty name (`name IS NULL OR name = ''`). 

If you meant a different table, please clarify!

**excel-row-count** (run 1):
> The "legacy customer export" file could not be found in the data folder or its subfolders. Please verify the file name, path, or format (e.g., .xlsx) and try again. If this is a database table, use `run_sql` with `SELECT COUNT(*) FROM customers;` to get the row count.

**contract-summary** (run 1):
> APIConnectionError: Connection error.

