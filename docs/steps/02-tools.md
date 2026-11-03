# Step 2: Tools

## What this step teaches

**The model never runs anything.** It can only write text. A "tool call" is a special kind of reply that says, in effect, "please run `calculate` with `{"a": 17.5, "op": "*", "b": 4}`". The harness decides whether to run it, runs it, and sends the result back as a new message. Then it calls the model again.

So one question can take several model calls:

```
user:       what is 17.5 times 4?
assistant:  (tool_calls: calculate {"a": 17.5, "op": "*", "b": 4})     <- model call 1
tool:       70.0                                                       <- harness ran it
assistant:  17.5 multiplied by 4 equals 70.                            <- model call 2
```

That loop is the core of every agent harness, Claude Code included. Everything later in this project (files, databases, MCP, the sandbox, approvals) is more tools, or rules about when a tool may run.

### How the model knows the tools exist

Each call sends a list of tool **schemas**: a name, a one-line description, and a JSON Schema for the arguments (`Tool.schema()`). The model reads the descriptions to decide when to use a tool, so write them for the model, like you'd write them for a new colleague.

### Errors are text, not exceptions

`run_tool_call` never raises. A made-up tool name, broken JSON, a missing argument or a crashing tool all come back as `Error: ...` text in a `tool` message. The model reads it and can fix its arguments, try something else, or explain the problem. A Python exception would stop the conversation, and the model would never learn what went wrong.

Small models make these mistakes often, which is why the calculator accepts `"6"` as well as `6`, and why arguments are checked against the function before it runs.

### Stopping

A model can keep asking for tools forever. `max_steps` (default 10, setting `HARNESS_MAX_STEPS`) caps the model calls per question. When it runs out, the agent says so.

## Files to read, in order

1. `src/harness/tools.py`: `Tool`, `run_tool_call`, and the two tools.
2. `src/harness/agent.py`: `ask` is now a loop. Follow one question through it.
3. `src/harness/cli.py`: `show_tool_call` prints the `[tool]` lines.

## Things to try

```bash
uv run harness
```

- "what is 17.5 times 4?": one `[tool] calculate` line, then the answer.
- "what time is it in Tokyo?": the model picks the `Asia/Tokyo` time zone by itself.
- "what is 10 divided by 0? use the calculator": the tool fails, the error goes back, and the model explains it.

## What we saw with qwen3:8b

- It picked the right tool and arguments for simple questions.
- For "Mars/Base" it **didn't call the tool at all**. It already knew that isn't a real time zone. Models decide for themselves whether a tool is worth calling.
- Asked to use the time zone `Europe/Istambul` (with a typo), it **fixed the typo** before calling the tool.
- Divide by zero came back as `Error: tool 'calculate' failed: float division by zero`, and the model turned it into a plain answer.
