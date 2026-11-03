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
- **Interface:** a terminal chat program for steps 1 to 6. A web page for step 7.
- **Web page:** React for the page, FastAPI for the backend.
- **Diagram:** a Mermaid diagram in `docs/architecture.md`, updated in the same change as the code at every step.
- **MCP:** both sides. We write our own MCP server and make the harness an MCP client.
- **Sandboxing:** limits on file and database tools from step 3. Code the model writes runs in a throwaway Podman container from step 6.
- **Human in the loop:** the agent pauses and asks a person when a computed score is below a threshold, or before any write. The person approves, rejects, or edits on a web page.

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
6. **Code execution in a sandbox.** A tool that lets the agent write a short Python script (for example with pandas) and run it, so it can work through a big Excel file or table without loading it into context. Code the model writes is untrusted, so it runs in a Podman container:
   - no network,
   - `data/` mounted read-only, and a separate empty folder for output,
   - time and memory limits,
   - the container is thrown away after each run.
7. **Human in the loop.** The customer migration task (details below).
8. **Later, any order:** memory across sessions, subagents, a rules file (like `AGENTS.md`) that the harness loads into its system prompt. Each gets its own short design when we reach it.

### Step 7 in more detail

**Task:** migrate the messy legacy Excel export of customers into the ERP database. The same customer shows up as "ACME Ltd", "Acme Limited" and "ACME LTD." with small address typos.

**Score:** for each incoming row, code computes a match score against existing customers with a simple string-similarity check. The score comes from code, so it is real and repeatable.

**When the agent asks a person:**
- Score of 0.9 or more: the agent merges the row on its own.
- Score below 0.9: the agent pauses and the row goes into an approval queue.
- Any write to the database needs approval at first. This can be relaxed later.

**Model's own score:** the agent also gives its own confidence. The page shows it next to the computed score, so the user can see how often they disagree.

**Web page:** a list of waiting decisions. Each shows the incoming row, the best match, both scores, and the agent's reason. Buttons: Approve, Reject, Edit (with a note). The answer goes back to the agent as a tool result, and the agent carries on.

**Shape:** FastAPI holds the queue and exposes a JSON API. The React page reads the queue and sends answers. A few components: the queue list, one decision card, the buttons.

## Assumptions

- The laptop runs Fedora with working NVIDIA drivers (checked: RTX 5060, 8 GB video memory, 14 GB RAM).
- Python 3.12 or newer. Node.js for the React page in step 7. Podman for step 6 (Fedora ships it).
- The harness only reads data in steps 0 to 6. Writes start in step 7, always behind approval.

## Known risks

- **Small model, more mistakes.** An 8B model will sometimes call tools wrongly. Handling that is part of step 2. If it blocks progress, switch to a bigger local model or a hosted one by changing settings.
- **Ollama's context window.** Ollama's default context is small. Setup must raise it, or long tool results get cut without warning.

## Left to the builder

- Exact folder and module names.
- Which libraries read PDFs and Excel files, and which string-similarity method to use.
- The exact fake data: table columns, row counts, file contents.
- How the terminal output and the web page look.
- How the agent waits for an approval (polling, a blocking call, or something else).
