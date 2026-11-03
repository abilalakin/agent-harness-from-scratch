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
claude mcp add erp -- uv run --directory ~/Desktop/Personal/learn-harness-engineering erp-mcp
```

Then, in Claude Code: "use the erp tools: which product has sold the most units?". Claude Code will call `mcp__erp__describe_tables` and `mcp__erp__run_sql`, your code running inside someone else's agent. Remove it with `claude mcp remove erp`.

**Look at it in the MCP Inspector** (a web page for poking at any MCP server, needs Node):

```bash
npx @modelcontextprotocol/inspector uv run erp-mcp
```
