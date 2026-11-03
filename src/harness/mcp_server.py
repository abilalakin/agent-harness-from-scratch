"""An MCP server that offers the ERP database's SQL tools to any MCP client.

It runs as its own program and talks MCP (JSON-RPC messages) over stdin/stdout.
Any MCP client can use it: Claude Code, the MCP Inspector, or our own harness (step 4b).

The tools themselves are the ones from sql_tools.py, so the read-only locks,
the row limit and the time limit come along unchanged.

Two rules for a stdio server:
- Never print(). stdout carries the protocol, and any stray text breaks it.
- Raise ToolError for failures. Any other exception reaches the client as only
  "Error executing tool run_sql", and the model never learns what went wrong.
"""

import argparse
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from harness import sql_tools
from harness.config import load_settings

SERVER_NAME = "erp"


def build_server(db_path: Path) -> MCPServer:
    server = MCPServer(SERVER_NAME)

    # The input schema comes from the type hints, the description from the shared constant.
    @server.tool(description=sql_tools.DESCRIBE_TABLES_DESCRIPTION)
    def describe_tables() -> str:
        try:
            return sql_tools.describe_tables(db_path)
        except Exception as e:
            raise ToolError(str(e)) from e

    @server.tool(description=sql_tools.RUN_SQL_DESCRIPTION)
    def run_sql(query: str) -> str:
        try:
            return sql_tools.run_sql(db_path, query)
        except Exception as e:
            raise ToolError(str(e)) from e

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for the practice ERP database (stdio).")
    # A command-line argument, because MCP clients pass only a few safe environment variables
    # to the servers they start, so HARNESS_DATA_DIR may not arrive here.
    parser.add_argument("--db", type=Path, default=load_settings().data_dir / "erp.db", help="path to erp.db")
    args = parser.parse_args(argv)
    build_server(args.db).run("stdio")


if __name__ == "__main__":
    main()
