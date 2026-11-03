import asyncio

from mcp import Client

from harness.mcp_server import build_server


def call(server, fn):
    """Run fn(client) against the server in-process (no subprocess) and return its result."""

    async def go():
        async with Client(server) as client:
            return await fn(client)

    return asyncio.run(go())


def test_lists_both_tools_with_schemas(data_dir):
    tools = call(build_server(data_dir / "erp.db"), lambda c: c.list_tools())
    by_name = {t.name: t for t in tools.tools}
    assert set(by_name) == {"describe_tables", "run_sql"}
    assert by_name["run_sql"].input_schema["required"] == ["query"]
    assert "describe_tables" in by_name["run_sql"].description  # tells the model to look first


def test_run_sql_returns_rows(data_dir):
    r = call(
        build_server(data_dir / "erp.db"),
        lambda c: c.call_tool("run_sql", {"query": "SELECT COUNT(*) AS n FROM customers"}),
    )
    assert not r.is_error and r.content[0].text.splitlines() == ["n", "50"]


def test_refused_write_keeps_the_real_message(data_dir):
    r = call(build_server(data_dir / "erp.db"), lambda c: c.call_tool("run_sql", {"query": "DELETE FROM customers"}))
    assert r.is_error and "readonly" in r.content[0].text


def test_missing_database_gives_make_data_hint(tmp_path):
    r = call(build_server(tmp_path / "erp.db"), lambda c: c.call_tool("describe_tables", {}))
    assert r.is_error and "uv run make-data" in r.content[0].text
