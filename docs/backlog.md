# Backlog

Open points, ideas and small findings that are not part of the current step. Add a line when something comes up; move it to a step plan when it gets picked. Each line says where it came from, so the reason is not lost.

## Ideas and improvements

- **Tool schemas in every call.** All nine tool schemas go with every model call, about 1000 tokens of the 8192 window before the conversation starts, and more tools make the choice harder. Options to measure with the evals: a smaller tool set per question type, a "tool search" tool that returns a schema on request, prompt caching on hosted models. (Step 7 discussion, 2026-11-17.) Candidate for step 11.
- **Streaming.** Nothing shows until the model finishes a reply; `[thinking]` lines appear after the fact. Streaming the reply (and the thinking) would make the wait visible. Needs the streaming form of the OpenAI client and a change to how `complete` returns tool calls. (Step 6, when the thinking display was added.)
- **Rebuild a report from a raw log.** `uv run evals --report logs/evals/x.jsonl` so a report can be regenerated after the report format changes, without rerunning an hour of GPU. (Step 6: the first baseline's report is in the old format.)
- **Rescore trajectories from a raw log.** Tool calls are stored, so trajectory checks could be recomputed when a check changes, instead of rerunning. (Step 6: the row-count trajectory fix.)
- **Schema-driven argument coercion.** `read_pdf`, `read_excel` and `calculate` each call `int()`/`float()` on arguments because small models send `"2"` for `2`. One general coercion in `run_tool_call`, driven by the JSON schema, would replace the three. (Step 5 review.)
- **A running total in `fit_to_budget`.** It re-serializes the whole message list once per candidate stub or drop, about 50 ms per question at this size. A running total of per-message sizes would fix it; plain code was preferred at the time. (Step 5 review.)
- **An index for `search_files`.** Every search re-parses every PDF. Fits step 10, where chunks are stored anyway. (Step 5 review.)
- **`MAX_MATCHES` counts, other tools count characters.** A wide search result can get two notes (the match cap and the character cap). (Step 5 review.)
- **MCP `run_sql` schema has no description for `query`.** The built-in tool says "One SQLite SELECT statement"; the MCP one should too, with `Annotated[str, Field(description=...)]`. (Step 4 review.)
- **`McpConnection` startup timeout** leaves a server that ignores stdin running. erp-mcp exits on EOF, so no effect today. Fix: cancel the owner task and let it clean up before stopping the loop. Also: `close()` can re-raise an owner-task error inside the CLI `finally`; `make_mcp_tools` runs before the CLI `try/finally`; the `logs/mcp-erp.log` handle is never closed and `logs/` is relative to the current folder. (Step 4 review.)
- **`calculate` uses float**, so huge whole numbers get rounded. (Step 2 review.)
- **`run_python` limits that are not covered**: CPU time (a script can spin for 30 s), filling the disk through `out/`, and the sandbox being only as strong as user namespaces. A container or a VM is the next level up. (Step 7.)

## Measured problems (from the evals)

- **Keyword search misses rephrasings.** `contract-notice` 1 of 5, `contract-penalty` 3 of 5 with the trajectory fine: "notice period" does not match "90 days written notice". Step 10 (semantic search) is the planned answer; these two tasks are the number to beat. (First baseline, 2026-11-13.)
- **The model answers from the wrong source.** Both Excel tasks 0 of 5: it queried the database for a table named after the file and never called `list_files`. Step 7's `run_python` and a better prompt are the candidates; the strict-prompt run (pending) will say. (First baseline.)
- **The step 5 fake, counted.** `invoice-mismatch` 4 of 5 with one run reading two PDFs and claiming five. Trajectory checks catch it; what reduces it is open (prompt, a script over all five, a bigger model). (First baseline.)
- **The judge sees the rubric, not the agreement.** It fails a true clause that is not in the rubric for the same reason as an invented one. Giving the judge the source text would let it tell them apart, at the cost of a longer judge prompt. (Step 6c.)

## Pending work

- **Step 6 benchmark runs.** Baseline, `qwen3:4b`, strict prompt and a 3500-token window, about four hours of GPU, then the compare table and the "Results" part of `docs/steps/06-evals.md`. The command chain is in that note under 6d.

## Small things, deferred from reviews

- Missing tests: the 200-character cut in `show_tool_call`, the other `APIError` path, two tool calls in one reply, `VACUUM INTO` and `load_extension` refusal in `run_sql`, the missing-data startup hint, a plain-mode startup warning for `HARNESS_SANDBOX=none`, an MCP server dying mid-session. (Steps 2 to 7 reviews.)
- `agent.py` prints dict arguments as a Python dict in the tool-call line. (Step 2 review.)
- Stale wording in early step notes: 00-setup says "2 tests pass"; 01-chat-loop suggests adding `print(self.messages)` "at the end of ask", which now has two return points. (Step 2 review.)
