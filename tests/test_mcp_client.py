import sys
import time

import pytest
from mcp import StdioServerParameters

from harness.mcp_client import McpConnection, make_mcp_tools
from harness.mcp_server import build_server
from harness.sql_tools import make_sql_tools
from harness.tools import run_tool_call


def call(name, args):
    return {"id": "c1", "type": "function", "function": {"name": name, "arguments": args}}


@pytest.fixture
def conn(data_dir):
    """A connection to the server in-process: no subprocess, so the test is fast."""
    connection = McpConnection(build_server(data_dir / "erp.db"))
    yield connection
    connection.close()


def test_tools_get_prefixed_names_and_server_schemas(conn):
    tools = make_mcp_tools(conn, "erp")
    assert sorted(t.name for t in tools) == ["mcp__erp__describe_tables", "mcp__erp__run_sql"]
    assert {t.name: t for t in tools}["mcp__erp__run_sql"].parameters["required"] == ["query"]


def test_no_clash_with_builtin_sql_tools(conn, data_dir):
    names = [t.name for t in make_sql_tools(data_dir / "erp.db") + make_mcp_tools(conn, "erp")]
    assert len(names) == len(set(names))


def test_query_through_run_tool_call(conn):
    tools = {t.name: t for t in make_mcp_tools(conn, "erp")}
    out = run_tool_call(tools, call("mcp__erp__run_sql", '{"query": "SELECT COUNT(*) AS n FROM products"}'))
    assert out.splitlines() == ["n", "20"]


def test_refused_write_reaches_model_with_real_message(conn):
    tools = {t.name: t for t in make_mcp_tools(conn, "erp")}
    out = run_tool_call(tools, call("mcp__erp__run_sql", '{"query": "DROP TABLE orders"}'))
    assert out.startswith("Error: tool 'mcp__erp__run_sql' failed:") and "readonly" in out


def test_missing_argument_is_checked_by_the_server(conn):
    tools = {t.name: t for t in make_mcp_tools(conn, "erp")}
    out = run_tool_call(tools, call("mcp__erp__run_sql", "{}"))
    assert out.startswith("Error: tool 'mcp__erp__run_sql' failed:") and "query" in out


def test_real_subprocess_over_stdio(data_dir, tmp_path):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "harness.mcp_server", "--db", str(data_dir / "erp.db")]
    )
    with open(tmp_path / "server.log", "w") as log:
        connection = McpConnection(params, errlog=log)
        try:
            assert [t.name for t in connection.list_tools()] == ["describe_tables", "run_sql"]
        finally:
            connection.close()


def test_server_that_dies_fails_fast(tmp_path):
    params = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(3)"])
    start = time.monotonic()
    with open(tmp_path / "server.log", "w") as log, pytest.raises(RuntimeError, match="failed to start"):
        McpConnection(params, errlog=log, timeout=30)
    assert time.monotonic() - start < 10


def test_calls_after_close_fail_clearly(data_dir):
    connection = McpConnection(build_server(data_dir / "erp.db"))
    connection.close()
    connection.close()  # a second close is harmless
    with pytest.raises(RuntimeError, match="closed"):
        connection.list_tools()
