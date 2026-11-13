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
