"""The harness as an MCP client: connect to an MCP server and use its tools as ordinary Tools.

The mcp library is async (asyncio). The harness is plain synchronous code. Rather than
rewrite the agent loop as async, McpConnection runs the async side on its own thread:

    harness (main thread)                    background thread (asyncio event loop)
    ---------------------                    --------------------------------------
    conn.call_tool("run_sql", {...})  --->   client.call_tool(...)  ---> server
          ... waits for the answer ...                                <--- reply
    gets the CallToolResult           <---

One rule from the mcp library shapes the code: the connection must be opened and closed
by the same asyncio task. So one long-lived task (_own_connection) opens it, waits until
close() is called, and closes it. Each call runs in its own short task next to it.
"""

import asyncio
import sys
import threading
from typing import TextIO

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from harness.tools import Tool


class McpConnection:
    def __init__(
        self,
        server: StdioServerParameters | MCPServer,
        errlog: TextIO = sys.stderr,
        timeout: float = 30.0,
    ):
        """Start the server (or connect in-process to a server object, for tests) and connect."""
        self.timeout = timeout
        self._closed = False
        self._connected = threading.Event()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._owner = asyncio.run_coroutine_threadsafe(self._own_connection(server, errlog), self._loop)

        # Wait until connected. If the owner task ends first, the server failed: say so now,
        # instead of waiting for the full timeout.
        waited = 0.0
        while not self._connected.wait(0.1):
            waited += 0.1
            if self._owner.done() or waited >= timeout:
                error = _root_cause(self._owner.exception()) if self._owner.done() else "timed out"
                self._closed = True
                self._stop_loop()
                raise RuntimeError(f"MCP server failed to start: {error}")

    def _run_loop(self) -> None:
        self._loop.run_forever()  # runs until _stop_loop()
        self._loop.close()

    def _stop_loop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(self.timeout)

    async def _own_connection(self, server: StdioServerParameters | MCPServer, errlog: TextIO) -> None:
        self._stop = asyncio.Event()
        # A command line → start it as a subprocess and talk over its stdin/stdout.
        # A server object → connect to it in this process (fast, used by tests).
        transport = stdio_client(server, errlog=errlog) if isinstance(server, StdioServerParameters) else server
        async with Client(transport) as client:
            self._client = client
            self._connected.set()
            await self._stop.wait()  # stay connected until close()

    def _run(self, coro):
        """Run one async call on the background loop and wait for its result."""
        if self._closed:
            coro.close()  # never started; close it so Python doesn't warn
            raise RuntimeError("MCP connection is closed")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(self.timeout)
        except TimeoutError:
            future.cancel()  # stop waiting on the background loop too, not only here
            raise RuntimeError(f"MCP server did not answer within {self.timeout:g} s") from None

    def list_tools(self) -> list[McpTool]:
        return self._run(self._client.list_tools()).tools

    def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return self._run(self._client.call_tool(name, arguments))

    def close(self) -> None:
        """Disconnect and end the server process. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._stop.set)
        self._owner.result(self.timeout)  # the owner task closes the connection
        self._stop_loop()


def _root_cause(error: BaseException) -> BaseException:
    """asyncio wraps failures in ExceptionGroups ("unhandled errors in a TaskGroup").
    Unwrap them to the first real error, like "Connection closed", which says what happened."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def make_mcp_tools(connection: McpConnection, server_name: str) -> list[Tool]:
    """Turn each tool the server offers into a normal Tool. The agent can't tell the difference.

    Names get a prefix, mcp__<server>__<tool>, like in Claude Code, so a server's
    run_sql can't clash with a built-in run_sql.
    """

    def make_fn(mcp_name: str):
        # **arguments: the server checks the arguments against its own schema, not run_tool_call.
        def fn(**arguments) -> str:
            result = connection.call_tool(mcp_name, arguments)
            text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
            if result.is_error:
                raise ValueError(text)  # run_tool_call turns this into "Error: tool '...' failed: ..."
            return text

        return fn

    return [
        Tool(
            name=f"mcp__{server_name}__{t.name}",
            description=t.description or "",
            parameters=t.input_schema,
            fn=make_fn(t.name),
        )
        for t in connection.list_tools()
    ]
