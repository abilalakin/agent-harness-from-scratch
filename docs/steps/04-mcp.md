# Step 4: MCP

Step 4 has two parts: our own MCP server (4a) and the harness as an MCP client (4b).

## 4a: The MCP server

### What this part teaches

**MCP (Model Context Protocol) is a standard way for an agent to find and call tools that live in another program.** In step 3 the SQL tools lived inside the harness. Only our harness could use them. In step 4a the same tools move into a separate program, `erp-mcp`, and any MCP client can use them: Claude Code, the MCP Inspector, Cursor, or our own harness in 4b.

The server is small (`src/harness/mcp_server.py`) because it reuses `sql_tools.py`. The read-only lock, the 50-row limit and the 10-second limit come along for free.

### What actually goes over the wire

A stdio MCP server reads one JSON message per line from stdin and writes one per line to stdout. That's all. You can talk to it by hand:

```bash
{ printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"by-hand","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"run_sql","arguments":{"query":"SELECT name FROM products LIMIT 2"}}}' \
  '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"run_sql","arguments":{"query":"DELETE FROM orders"}}}'
  sleep 2; } | uv run erp-mcp 2>/dev/null
```

What came back (shortened):

```json
{"id":1,"result":{"protocolVersion":"2025-06-18","serverInfo":{"name":"erp"},"capabilities":{"tools":{...}}}}
{"id":2,"result":{"tools":[{"name":"describe_tables","description":"Show the tables ...","inputSchema":{...}}, {"name":"run_sql", ...}]}}
{"id":4,"result":{"content":[{"type":"text","text":"Error executing tool run_sql: attempt to write a readonly database"}],"isError":true}}
{"id":3,"result":{"content":[{"type":"text","text":"name\nHydraulic pump\nBrake pad set"}],"isError":false}}
```

Three things to notice:

1. **Three kinds of message do almost all the work.** `initialize` is the handshake (which protocol version, what each side can do). `tools/list` returns each tool's name, description and JSON Schema, the same three things our `Tool` class holds. `tools/call` runs one tool. Compare with step 2: it's the same idea, as messages between programs.
2. **Reply 4 came before reply 3.** The server answers when each call finishes, not in order. The `id` is how the client matches a reply to its request.
3. **Errors are results, not crashes.** The refused `DELETE` comes back as a normal reply with `"isError": true` and readable text, the same "errors are text" rule as step 2.

### Two rules for a stdio server

- **Never `print()`.** stdout *is* the protocol. One stray line of text and the client can't parse anything. Logs go to stderr.
- **Raise `ToolError` for failures.** If a tool raises an ordinary exception, the MCP library hides the message and the client only sees `Error executing tool run_sql`. The model can't fix what it can't see. So `mcp_server.py` catches every error and re-raises it as `ToolError(str(e))`, which keeps the real message, like `attempt to write a readonly database`.

### Why `--db` and not `HARNESS_DATA_DIR`

MCP clients start servers with only a few safe environment variables, not your whole environment. That's a deliberate safety choice: a server shouldn't see your API keys just because they're in your shell. So the database path goes in as a command-line argument, `erp-mcp --db path/to/erp.db`. Without it, the server uses `data/erp.db` relative to where it starts.

### Files to read, in order

1. `src/harness/mcp_server.py`: about 40 lines. `build_server` registers two tools, `main` starts the server.
2. `src/harness/sql_tools.py`: the two `..._DESCRIPTION` constants are now shared by the built-in tools and the server, so the model reads the same words either way.
3. `tests/test_mcp_server.py`: the tests connect to the server in-process (`Client(server)`), with no subprocess, so they're fast.

### Things to try

**Connect Claude Code to your server.** This changes your Claude Code settings for this project only, so run it yourself:

```bash
claude mcp add erp -- uv run --directory ~/Desktop/Personal/agent-harness-from-scratch erp-mcp
```

Then, in Claude Code: "use the erp tools: which product has sold the most units?". Claude Code will call `mcp__erp__describe_tables` and `mcp__erp__run_sql`, your code running inside someone else's agent. Remove it with `claude mcp remove erp`.

**Look at it in the MCP Inspector** (a web page for poking at any MCP server, needs Node):

```bash
npx @modelcontextprotocol/inspector uv run erp-mcp
```

## 4b: The harness as an MCP client

### What this part teaches

**To the model, an MCP tool is just a tool.** With `HARNESS_SQL_VIA=mcp`, the harness starts `erp-mcp`, asks it `tools/list`, and wraps each tool it gets back as a normal `Tool` from step 2: same name, description and JSON Schema, plus a function that sends `tools/call`. The agent loop in `agent.py` didn't change by a single line. That's the point of MCP: the agent doesn't care where a tool lives.

```bash
HARNESS_SQL_VIA=mcp uv run harness
```

### The names: `mcp__erp__run_sql`

Both paths offer a `run_sql`. If both were loaded, the model would see two tools with the same name. So MCP tools get a prefix, `mcp__<server>__<tool>`. Claude Code uses the same convention, which is why it showed your tools as `mcp__erp__run_sql` in 4a.

### The bridge: sync harness, async library

The `mcp` library is built on asyncio. The harness is plain synchronous code. Rewriting the agent loop as async would touch every file. Instead, `McpConnection` gives the async client its own thread:

```
harness (main thread)                    background thread (asyncio event loop)
conn.call_tool("run_sql", {...})  --->   client.call_tool(...)  ---> erp-mcp process
      ... waits ...                                              <--- reply
gets the result                   <---
```

`asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)` is the whole trick: hand a job to the other thread's loop, then wait for the answer.

One rule from the library shaped the code: **a connection must be opened and closed by the same asyncio task.** The first try opened it in one call and closed it in another, and crashed with `Attempted to exit cancel scope in a different task`. So `_own_connection` is one long-lived task. It opens the connection, waits until `close()` sets a stop event, then closes it. The calls run in their own short tasks beside it.

Two more details you'll see in `mcp_client.py`:

- **Fail fast, and say why.** If the server dies at startup, the owner task ends early. `__init__` notices within 0.1 s and raises `MCP server failed to start: Connection closed`, instead of waiting 30 s for a connection that will never come. asyncio first wraps that error in groups (`unhandled errors in a TaskGroup (1 sub-exception)`), which tells you nothing, so `_root_cause` unwraps it. The server's own log in `logs/mcp-erp.log` has the details.
- **A call that hangs.** Each call waits at most 30 s. Then the harness cancels the request on the background loop too, and the model gets `MCP server did not answer within 30 s`. The first version gave it an empty error (`failed: ` and nothing more), because Python's `TimeoutError` has no message. The model can't act on silence.
- **Clean up.** `close()` stops the task (which ends the server process), stops the loop, waits for the thread, and closes the loop. The first version forgot the last step, and only a test run with warnings switched on showed it: `ResourceWarning: unclosed event loop`.

### Who checks the arguments now

For built-in tools, `run_tool_call` checks the model's arguments against the Python function. MCP tools take `**arguments`, so that check lets everything through, and the **server** checks them against its schema instead. A missing `query` comes back as the server's validation error, and the model reads it the same way as before.

### What we saw

Same question, "which product has sold the most units?", both ways:

| | built in | MCP |
|---|---|---|
| Tool calls | `describe_tables`, `run_sql` | `mcp__erp__describe_tables`, `mcp__erp__run_sql` |
| Answer | Fire extinguisher, 191 units (correct) | Fire extinguisher, 191 units (correct) |
| Whole run | 33 s | 31 s |
| Server start | none | about 0.8 s |
| One `run_sql` call | 0.08 ms | 4 ms |

The extra process costs almost nothing you'd notice. The model's thinking takes nearly all the time. Also: this time Qwen3 called `describe_tables` **first**, both ways. In step 3 it guessed column names three times. The only change was one sentence in the `run_sql` description: "Call describe_tables first to see the column names."

### When to use MCP and when not

**Use MCP** when the same tools should work in several agents (your harness, Claude Code, Cursor), when the tool is written in another language, or when it runs on another machine or needs its own permissions.

**Keep a tool built in** when only this harness uses it. It's one process, there's nothing to start or shut down, calls are faster, and errors are easier to follow.

### Files to read, in order

1. `src/harness/mcp_client.py`: the comment at the top, then `McpConnection`, then `make_mcp_tools`.
2. `src/harness/cli.py`: `start_erp_mcp_server` and the `sql_via` switch in `main`.
3. `tests/test_mcp_client.py`: a server that dies at startup, errors crossing the protocol, calls after `close()`.

### Things to try

```bash
HARNESS_SQL_VIA=mcp uv run harness
```

- Ask the same question as with `uv run harness` and compare the `[tool]` lines.
- While it runs, in another terminal: `ps -eo pid,args | grep "[h]arness.mcp_server"` shows the server process. After `/exit`, it's gone.
- `tail -f logs/mcp-erp.log` shows the server's own log, which stays out of your chat.
