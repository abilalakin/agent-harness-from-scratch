# Step 6: Evals and benchmarking

Up to now, "does it work?" was answered by running a question once and reading the answer. Step 5 showed why that is not enough: the model read two invoice PDFs and said it had checked five. It looked right. It was not.

An eval turns "it seemed to work" into a number. Step 6 builds one for this harness: a set of questions with known answers (6a), checks on what the agent *did* and not only what it said (6b), a model that grades free text (6c), and the same set run with one thing changed at a time (6d). It ends with a short reading note on the public benchmarks (6e).

## 6a: A task set and a runner

### What an eval is

Three things: a question, a known answer, and a checker that compares the two. Here:

```python
Task("invoice-count", "How many invoices are in the ERP database?", contains("112"))
```

The checker is a small function from answer text to pass/fail. Three kinds are enough for now:

- `contains("112")`: the text appears, any case.
- `number_near(13701.44)`: some number in the answer is within 1.0 of the expected one. It strips thousands separators, so `13,701.44 EUR` passes too.
- `all_of(...)`: every check passes.

Twelve tasks over the practice data (`src/harness/evals/tasks.py`). They were picked to cover what the earlier steps got wrong: counting in a cut result (step 3), the invoice check (step 5), the search that found nothing because the wording differed (step 5), and Excel paging. The expected values come from the seed-42 practice data, and one test regenerates the data and checks every value against it. If the generator changes, that test fails before the evals do.

### Why N runs

An 8B model is noisy. The same question gets different tool calls and different answers from one run to the next. One run tells you what happened once. Five runs tell you how often. The report shows counts, `4 of 5`, not only a percentage: with five runs, a percentage hides how little data there is.

### How the runner measures without touching the harness

Nothing in `agent.py` changed for this step. The runner (`src/harness/evals/runner.py`) watches from the outside:

- **Tool calls** come through `on_tool_call`, the hook the CLI already uses to print `[tool] ...` lines.
- **Tokens** are counted by wrapping the model: `TokenCounter` sits between the agent and the real model, adds up the estimated size of every request, and passes the call through. The agent never knows.
- **Errors** are caught per run and stored, so one crash does not lose an hour of results. Ctrl+C still stops everything.
- **Every run gets a fresh agent**, a fresh history. Otherwise task 3 would see the tool results of tasks 1 and 2, and the numbers would depend on the order.

### Files to read

1. `src/harness/evals/tasks.py`: the checkers, then the table of tasks.
2. `src/harness/evals/runner.py`: `TokenCounter`, `run_task`, `run_all`.
3. `tests/test_evals_tasks.py`: the test that pins the expected answers to the generator.

## 6b: Scoring what the agent did

### The problem with answer checks

In step 5 the model answered "only INV-2026-0003 is off" after reading two of the five PDFs. The answer was right. The work was not done. An answer checker gives that run a pass, and a pass is exactly the wrong signal: it rewards a guess that happened to land.

### What changed

A task can now carry a second check that looks at the recorded tool calls instead of the answer text:

```python
Task("invoice-mismatch", "Does every invoice PDF ... match ...?", contains("INV-2026-0003"), looked_at_every_invoice)
```

`looked_at_every_invoice` passes if `read_pdf` was called for each of the five invoices, or if `search_files` was run over them. Both are honest ways to do the work. Two PDFs and a guess is not.

The other tasks get simpler checks: `called("run_sql")` for database questions, `paged_through_excel` (at least two `read_excel` calls, since the sheet has two pages) for the Excel ones. They are all in `src/harness/evals/tasks.py`, above the task table.

The report gets a `trajectory` column next to `passed`, and a section **Right answer, skipped work** that lists every run where the answer passed but the trajectory did not. That list is the point of 6b: it is the fake thoroughness from step 5, counted.

### Why both checks, not one

A trajectory check alone would reward a model that reads all five PDFs and then answers wrong. An answer check alone rewards the guess. A run is good when both pass, and the two failure kinds mean different things: a wrong answer is a reasoning or reading problem, a skipped trajectory is the model not doing what it said. They get different fixes (a stricter prompt, a different tool, a bigger model), so they are counted apart.
