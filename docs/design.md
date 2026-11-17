# Learn Harness Engineering: Design

Date: 2026-11-03

## Why

This is a learning project. The goal is to understand how an agent harness works by building one from the raw model API up. There is no fixed use case. Each step adds one idea and ends with something you can run and see working.

Practice topics come from real work: ERP data migrations, searching big company databases, reading PDFs and Excel files.

**Who does what:** Claude writes the code for each step. The user reads it, runs it, and asks questions. The user stages and commits.

## Goals

- Build a working agent harness step by step.
- Each step teaches one idea and is small enough to read in one sitting.
- Keep a system diagram that grows with the code, so the shape of the harness is always visible.
- End with a human-in-the-loop web page where a person approves the agent's uncertain decisions.

## Non-goals

- Production quality, speed, or scale.
- Using an agent framework (LangChain, Claude Agent SDK, etc.). The point is to write the loop ourselves.
- Paid or hosted models. Everything runs on the user's laptop.

## Anti-goals

These would make the project a failure even if the code works:

- Code too clever or too big to follow. If a step can't be read and understood in one sitting, it is too big.
- A step that doesn't run on its own. Each step must work before the next one starts.
- Real company data in the repo.
- A confidence threshold based only on the model's own opinion of itself.

## Decisions

Decided together:

- **Language:** Python.
- **Model:** an open model run locally with Ollama. The default is Qwen3 8B. It fits the laptop's RTX 5060 (8 GB video memory).
- **Model API:** the OpenAI-style chat format that Ollama serves. Switching to another local or hosted model only changes the URL and model name in settings.
- **Interface:** a terminal chat program for steps 1 to 8. A web page for step 9.
- **Web page:** React for the page, FastAPI for the backend.
- **Diagram:** a Mermaid diagram in `docs/architecture.md`, updated in the same change as the code at every step.
- **MCP:** both sides. We write our own MCP server and make the harness an MCP client.
- **Sandboxing:** limits on file and database tools from step 3. Code the model writes runs in a throwaway bubblewrap (`bwrap`) sandbox from step 7. Lighter than a container: no daemon, no image, starts in milliseconds, and Fedora ships it.
- **Human in the loop:** the agent pauses and asks a person when a computed score is below a threshold, or before any write. The person approves, rejects, or edits on a web page.
- **Evals and benchmarking (added 2026-11-12):** our own task set over the practice data, with checkers for answers and for what the agent did (trajectories). Run N times, scored, written to a markdown report. Every step after it reports its numbers.
- **Workflows, not only agents:** the migration is a pipeline where code does the steps and the model is called only where judgment is needed. Structured output (JSON that matches a schema, validated, retried) is how the model's part is kept honest.
- **RAG:** semantic search as one more tool the agent chooses to call, with a local embedding model through Ollama and vectors in SQLite. Compared against keyword search, not assumed better.

My calls (not discussed, change them if you disagree):

- **One program that grows.** No separate copy per step. The user sees each step as a git diff.
- **Big steps can be split** into several commits (3a, 3b, ...). Each commit still runs and passes its tests.
- **Tooling:** `uv` for Python and packages, `pytest` for tests. Vite and TypeScript for the React page.
- **Model client:** the `openai` Python package pointed at Ollama. It is a plain HTTP client, not an agent framework.
- **MCP library:** the official `mcp` Python SDK. Writing the protocol by hand would make step 4 several times bigger.
- **Practice data:** fake data made by a script. A small SQLite "ERP" database (customers, products, orders, invoices), a few PDFs (invoices, a contract), and a messy legacy Excel export of customers for the migration task.
- **Tests:** each step gets a few tests that replace the model with a fake. They are free and fast. A manual run against the local model checks each step by eye.
- **Git:** the folder becomes a git repo. Each step (or part of a step) is one commit.
- **Step notes:** each step gets a short note in `docs/steps/` that says what the step teaches, which files to read first, and what to try when running it.

## Steps

Each step ends with: code that runs, passing tests, an updated diagram, and a step note.

0. **Setup.** Install Ollama and pull the model. Repo `CLAUDE.md`, `uv` project, folder layout, `.gitignore`, first diagram.
1. **Chat loop.** Read user input, send the conversation to the model, print the reply, keep the history.
2. **Tools.** Define a tool, let the model ask for it, run it, send the result back, loop until the model is done. Handle the mistakes a small model makes: unknown tool names, bad arguments, endless loops.
3. **Data tools.** Generate the practice data. Add tools to read text files, PDFs and Excel sheets, and to run read-only SQL on the database. Basic limits come with them:
   - File tools only open files inside `data/`. Paths that lead outside it (like `../../.ssh`) are refused.
   - The database opens in read-only mode, so a `DELETE` or `UPDATE` from the model cannot run.
4. **MCP.** Write a database MCP server. Make the harness an MCP client that loads tools from it. Compare with the built-in SQL tool from step 3.
5. **Big data.** Handle results that don't fit in context: limit and page results, summarize, search instead of dumping whole files, trim old history.
6. **Evals and benchmarking.** Turn "the model seemed to do it" into a number. The step 5 run where the model read two invoice PDFs and claimed it had checked five is the first test case.
   - a. A task set over the practice data: about ten questions with known answers and a checker each (exact value, contains, number within tolerance). `uv run evals` runs each N times and writes a markdown report with pass rates.
   - b. Trajectory checks: not only the answer, but what the agent did. "Was `read_pdf` called for all five invoices?" A right answer reached by skipping work is a failure.
   - c. LLM as judge for free-text answers (summaries), graded against a rubric. Then its biases: longer answers, its own style. The judge is checked against a few hand-graded answers before it is trusted.
   - d. Benchmarking: the same task set with one thing varied, in one table: model (`qwen3:8b`, a smaller one, a hosted one if a key exists), prompt, harness version. Columns: pass rate, tool calls, tokens, seconds.
   - e. Public benchmarks, as reading: what MMLU, SWE-bench and τ-bench measure, and why a small eval set over your own task beats them for your own decisions.
7. **Code execution in a sandbox.** A `run_python` tool: the model writes a short script (pandas, openpyxl, pypdf are available) and gets stdout, stderr and any file it wrote to an output folder. The point is working through a big Excel file or table without loading it into context.
   - a. Plain `subprocess` first, to see the danger: the script can read `~/.ssh` and delete files.
   - b. Then `bwrap`: no network, `data/` read-only, one writable output folder, nothing else visible, a time and memory limit, thrown away after each run. The same script now fails.
   - **Done when:** the two escape scripts from 7a (list the home folder, write outside `out/`) fail inside the sandbox, with tests that prove it; an endless script and a 2 GB allocation are stopped; the model cannot choose the sandbox mode; and the Excel eval tasks are run with and without the tool, with the numbers in the step note.
8. **Structured output and the migration pipeline.** Two things that belong together.
   - Structured output: ask the model for JSON matching a schema (pydantic), validate it, send the error back and retry on failure. Used first to extract invoice fields from the PDFs.
   - The pipeline: extract (Excel, PDF) → normalize → validate against the schema → match score against existing customers → proposed change. Code does every step; the model is called only for the fuzzy ones. Every row carries where it came from. Anything uncertain goes to a queue instead of through. No database writes yet.
   - **Done when:** all five invoice PDFs come out as validated JSON and the planted mismatch on INV-2026-0003 is flagged by code, not by the model's say-so; a model reply that fails validation is retried with the error and the retry count is reported; the Excel export becomes one proposed change per row with a match score and its source row, the three duplicates and two empty rows are caught, and every row under the threshold is in the queue rather than through; nothing is written to the database.
9. **Human in the loop.** The web page on top of the step 8 queue (details below).
   - **Done when:** the queue is served by FastAPI and shown on a React page with the incoming row, the best match, both scores and the agent's reason; Approve, Reject and Edit send an answer back and the pipeline carries on; a write to the database happens only after an approval; and the page shows how often the computed score and the model's own confidence disagree.
10. **Semantic search (RAG).** An embedding model through Ollama (`nomic-embed-text` or similar), chunks and vectors in SQLite, a `search_semantic` tool next to `search_files`. The practice data grows (about fifty generated contracts with varied wording) so that keyword search fails where meaning search works. Measured with the step 6 evals, including the cases where RAG retrieves the wrong contract or cuts a chunk in the wrong place.
    - **Done when:** `search_semantic` returns the right contract chunk for a question worded differently from the text; the two contract eval tasks that fail on wording today (`contract-notice` 1 of 5, `contract-penalty` 3 of 5) pass more often with it than without, in one compare table; and the step note shows at least one case where it retrieves the wrong contract or a badly cut chunk, with what that does to the answer.
11. **Later, any order:** subagents (a fresh context per task, only the summary comes back), memory across sessions, a rules file (like `AGENTS.md`) that the harness loads into its system prompt. Each gets its own short design when we reach it.
    - **Done when**, per part: a subagent answers a sub-question in its own context and only its summary enters the parent's history, measured on a task where the parent alone runs out of context; a fact from one session is available in the next without being in the practice data; a rules file changes the agent's behaviour on an eval task in a way the compare table shows. The tool-schema question in `docs/backlog.md` (all schemas in every call) is measured here too.

### Step 9 in more detail

**Task:** migrate the messy legacy Excel export of customers into the ERP database. The same customer shows up as "ACME Ltd", "Acme Limited" and "ACME LTD." with small address typos. Step 8 built the pipeline that produces proposed changes and a queue of uncertain ones; step 9 puts a person on that queue.

**Score:** for each incoming row, code computes a match score against existing customers with a simple string-similarity check. The score comes from code, so it is real and repeatable.

**When the agent asks a person:**
- Score of 0.9 or more: the row is merged on its own.
- Score below 0.9: the row goes into the approval queue.
- Any write to the database needs approval at first. This can be relaxed later.

**Model's own score:** the agent also gives its own confidence. The page shows it next to the computed score, so the user can see how often they disagree.

**Web page:** a list of waiting decisions. Each shows the incoming row, the best match, both scores, and the agent's reason. Buttons: Approve, Reject, Edit (with a note). The answer goes back to the pipeline, and it carries on.

**Shape:** FastAPI holds the queue and exposes a JSON API. The React page reads the queue and sends answers. A few components: the queue list, one decision card, the buttons.

## Assumptions

- The laptop runs Fedora with working NVIDIA drivers (checked: RTX 5060, 8 GB video memory, 14 GB RAM).
- Python 3.12 or newer. Node.js for the React page in step 9. `bwrap` for step 7 (checked: bubblewrap 0.12.0 is installed).
- The harness only reads data in steps 0 to 8. Writes start in step 9, always behind approval.

## Known risks

- **Small model, more mistakes.** An 8B model will sometimes call tools wrongly. Handling that is part of step 2. If it blocks progress, switch to a bigger local model or a hosted one by changing settings.
- **Ollama's context window.** Ollama's default context is small. Setup must raise it, or long tool results get cut without warning.
- **Evals on a small model are noisy.** An 8B model at N=5 runs still swings. Reports show counts (4 of 5), not only percentages, and a change needs a clear gap to count as better.

## Left to the builder

- Exact folder and module names.
- Which libraries read PDFs and Excel files, and which string-similarity method to use.
- The exact fake data: table columns, row counts, file contents.
- How the terminal output and the web page look.
- How the agent waits for an approval (polling, a blocking call, or something else).
