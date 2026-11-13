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

## 6c: A model as judge

### Why

"Summarize the supply agreement in three bullet points" has no single right string. `contains("Germany")` passes a summary that gets the payment terms wrong and fails a perfect one that says "the laws of Germany apply" in different words. For free text, the checker has to read.

So a second model call does. `judge_answer` (`src/harness/evals/judge.py`) sends the question, the answer and a rubric, and asks for JSON only: `{"pass": true or false, "reason": "..."}`. The rubric for the summary task names three facts that must be there (net 30, 1.5% per month, German law), a length limit, and "no clause that is not in the agreement". `uv run evals --judge` lets the judge's verdict replace the checker's on every task that has a rubric.

Two small things in the code that matter in practice:

- The judge gets **no tools**. It grades the text it is given. If it could look things up, you would be measuring the judge's research, not the answer.
- Qwen writes prose around its JSON, or forgets the JSON. The first `{...}` in the reply is parsed; no JSON means fail with the reason "judge gave no JSON", never a crash.

### Checking the judge

A judge is a model, with a model's biases. The known ones: long answers look thorough, confident answers look right, an answer in its own style looks good. So before the judge is trusted, it grades six answers that were graded by hand first (`JUDGE_CHECKS`). Each one tests one bias:

1. The plain correct answer (pass).
2. The same answer padded with filler (pass: length should not matter).
3. Three bullets with the penalty missing (fail).
4. The correct answer plus a confident, made-up clause about an early-payment discount (fail).
5. One terse line with all three facts (pass).
6. The correct answer plus "I checked every page carefully" (pass: self-praise is not a rubric point).

`uv run evals --check-judge` prints a table of hand grade against judge grade. Where they disagree is where the judge cannot be trusted, and that is a fact about the judge that you want to know before it grades a hundred runs.

### What we saw

`qwen3:8b` as judge agreed with the hand grade on all six, twice (two separate runs). Padding, terseness and self-praise did not move it, and it caught the invented discount clause. One thing in its reasons is worth knowing: for answer 3 it said the delivery clause was "not specified in the question". The delivery clause is real, it is in the agreement, but the judge never sees the agreement, only the rubric. So the rubric line "no clause that is not in the agreement" is really "no clause that is not in the rubric" to the judge. A true extra fact and an invented one look the same to it. The verdict was right; the reason was only half right.

Judging the summary task itself showed a problem with the *question*, not the model. The first version asked to "summarize the supply agreement in three bullet points". The model summarized page 1 (scope, prices, delivery) and the rubric failed it for not mentioning payment terms: 1 of 5. That is an unfair eval. The question now names what matters (payment terms, late penalty, governing law): 3 of 5 (`docs/evals/2026-11-13-judge.md`). The two failures said the penalty and the law were "not found in available documents" after reading the PDF, which is the model missing text that was in front of it.

The lesson: when a judged task fails, read the failures before blaming the model. The rubric and the question have to ask for the same thing.

## 6d: Benchmarking, one thing at a time

A benchmark is the same task set run with one thing changed. One thing, so the difference in the numbers has one cause. `uv run evals --compare a.jsonl b.jsonl ...` puts the runs side by side, one row each, with the meta that says what was different: model, prompt, context window, commit.

Three comparisons against the baseline:

| what changes | how |
|---|---|
| the model | `HARNESS_MODEL=qwen3:4b uv run evals --label qwen3-4b` (half the size, after `ollama pull qwen3:4b`) |
| the prompt | `uv run evals --system-prompt docs/evals/prompts/strict.txt --label strict-prompt`: the default prompt plus "Never report a result you did not get from a tool. If a question is about several files, say which ones you actually read." |
| the harness | `HARNESS_CONTEXT_WINDOW=3500 uv run evals --label window-3500`: the harness trims on every task, while Ollama's real window stays at 8192, so only the harness changes |

The harness version is the fourth axis, and it runs across time rather than across one afternoon: every report records its git commit, and every later step reruns the baseline and adds a row. That is how step 7 (a `run_python` tool) or step 10 (semantic search) will show whether they helped.

### Reading the numbers

The design doc's warning applies: five runs of an 8B model swing. One run in five is noise. A change counts as real when it moves several tasks the same way, or moves one task from 0 of 5 to 5 of 5. Tokens and seconds move with tool calls, so a cheaper run with the same pass count is a win too.

## Seeing the model think

A side change made while running these: the CLI now prints the model's reasoning as `[thinking] ...` lines before each tool call and the answer. Ollama returns Qwen3's thinking in a separate `reasoning` field, and until now the harness threw it away. The reasoning is often the most useful line on the screen: "the user didn't give a timezone, so UTC is safe" tells you why a tool was called with those arguments. Nothing shows until the model has finished the whole reply (there is no streaming yet), so the wait is the same; what changes is that the wait is followed by the why. The `on_thinking` hook sits on `OpenAIChatModel`, next to `on_tool_call` on the agent: the harness reports, the CLI decides what to print.

## What we saw with qwen3:8b

The first baseline (`docs/evals/2026-11-13-first-baseline.md`, 12 tasks, 5 runs each, about 55 minutes):

| group | result | what happened |
|---|---|---|
| five database questions | 25 of 25, 2 tool calls each | `describe_tables`, then one query. Solid. The step 3 "50 invoices" mistake is gone. |
| invoice-3-pdf-total | 5 of 5, 1 tool call | One `read_pdf`. |
| invoice-mismatch | 4 of 5, trajectory 4 of 5 | The failed run is the step 5 fake, word for word: "The first two invoices checked (INV-2026-0001 and INV-2026-0002) match their ERP totals." The trajectory check caught it too: 2 PDFs read, not 5. |
| contract-penalty, contract-notice | 3 of 5 and 1 of 5, trajectory 5 of 5 | The model did the right thing (searched the contract) and still failed. `search_files` for "days notice" or "notice period" finds nothing: the PDF says "90 days written notice". After three or four failed searches the model gave up and said the data doesn't have it. The one run that passed searched for the single word "notice". |
| excel-empty-rows, excel-row-count | 0 of 5, 0 of 5 | The question says "legacy customer export". The file is `legacy/customers_export.xlsx`. The model never called `list_files` and instead queried a database table `legacy_customer_export` (which doesn't exist), then the `customers` table, and answered "0 rows with an empty name". Confidently wrong, from the wrong source. |
| the last 8 runs | errors | Ollama was killed by the kernel's out-of-memory killer during run 3 of excel-row-count (`journalctl -u ollama` shows `oom-kill`). Every run after that was a connection error in 2 seconds. |

Three lessons from one hour of GPU time:

1. **The failure kinds are different, and the report tells them apart.** Database questions pass. The invoice check fails by skipping work (trajectory). The contract questions fail with the trajectory fine (the tool is too weak for the wording). The Excel questions fail by never looking (wrong source). A single pass rate of 38 of 60 would hide all of that.
2. **Keyword search is the weak link.** Two tasks fail because "notice period" does not match "90 days written notice". This is the case for step 10, semantic search, and now there is a number to beat.
3. **An eval harness needs to count errors apart from failures.** The first version of the report showed `contract-summary: 0 of 5` with no hint that the model never ran. The report now shows `0 of 5 (5 errors)` and `8 errored` in the totals line. The lost runs were rerun separately.

## 6e: The public benchmarks, and why they don't answer our question

You will see three names in every model announcement. What each one measures:

- **MMLU** (Massive Multitask Language Understanding): about 14,000 multiple-choice questions across 57 subjects, from high-school maths to law. It measures knowledge and reading. There are no tools, no files, no multi-step work. A model picks A, B, C or D.
- **SWE-bench**: real GitHub issues from real Python repos. The model gets the repo and the issue text and has to produce a patch. The patch passes if the repo's own tests pass. It measures agentic coding: reading a codebase, finding the right place, changing it, not breaking the rest. SWE-bench Verified is the human-checked subset.
- **τ-bench** (tau-bench): tool-using agents in a simulated customer-service setting (airline, retail). A second model plays the customer. The agent has tools over a database and a policy document it must follow. A run passes if the final database state matches the expected one, whatever path the agent took. Scores are reported as **pass^k**: the share of tasks that pass *all* of k tries, which punishes an agent that gets it right one time in three.

Two of those ideas are already in our small set, seen from the other side. τ-bench scores the final state and not the transcript; our trajectory check does the reverse, and both exist because an answer and the work behind it can disagree. pass^k is our "4 of 5" turned into a stricter number: with five runs, pass^5 is 1 only for tasks that never fail.

What none of them can tell you: whether `qwen3:8b` reads five invoices or two, or whether it finds "90 days written notice" when asked about the "notice period". A public score says how a model does on someone else's task, averaged over thousands of cases. Your decision is about your task, your data and your tools. Twelve questions, five runs each, over your own files answer that in an hour, and they keep answering it after every change you make. That is the reason to own a small eval set, even a rough one, before trusting any leaderboard.

## Things to try

- `uv run evals --runs 1 --task invoice-mismatch`, then open the raw log in `logs/evals/` and read the tool calls. Did it read five PDFs, or search, or guess?
- Write a thirteenth task. Pick a question you asked the agent in an earlier step, decide the right answer, and add a `Task(...)` line. Run it five times.
- Break the judge on purpose: add a seventh answer to `JUDGE_CHECKS` that is wrong but long and confident, and see whether `--check-judge` catches it.
- Run `HARNESS_CONTEXT_WINDOW=3500 uv run evals --task invoice-mismatch --label small` and compare it with the baseline row. Trimming has a cost; this shows it.
