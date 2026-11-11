"""Tools that query the ERP database, read-only.

The model writes the SQL, so the SQL can't be trusted. Instead of checking the
text of each query (easy to get wrong), the database itself refuses to change:
- the file is opened with mode=ro, so SQLite rejects every write,
- attaching other database files is turned off, so a query can't open (or create) another file.
"""

import sqlite3
import time
from contextlib import closing
from functools import partial
from pathlib import Path

from harness.file_tools import MISSING_DATA_HINT
from harness.tools import Tool

MAX_ROWS = 50
QUERY_TIME_LIMIT_SECONDS = 10

# Written for the model. Shared by the built-in tools below and the MCP server (mcp_server.py).
DESCRIBE_TABLES_DESCRIPTION = "Show the tables of the ERP database (erp.db) and their columns. Call this before run_sql."
RUN_SQL_DESCRIPTION = (
    "Run one read-only SQLite query on the ERP database and get the rows back. "
    "Call describe_tables first to see the column names. "
    f"At most {MAX_ROWS} rows are shown, so filter or aggregate in SQL. Writes are refused."
)


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    # Check first: connecting to a missing file would otherwise fail with a vague error.
    if not db_path.is_file():
        raise ValueError(MISSING_DATA_HINT)
    # The path goes into a URI, where "#", "?" and "%" have special meanings. as_uri() escapes
    # them. Without it, a folder like "my#proj" would cut off "?mode=ro" and open a writable file.
    con = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    con.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)  # also blocks VACUUM INTO, which writes a copy

    # Stop queries that run too long. SQLite calls the handler every 10,000 steps.
    # Returning True makes it abort with "interrupted", which reaches the model as an error.
    deadline = time.monotonic() + QUERY_TIME_LIMIT_SECONDS
    con.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
    return con


def describe_tables(db_path: Path) -> str:
    """The CREATE TABLE statement of every table: column names, types and links."""
    with closing(connect_read_only(db_path)) as con:
        rows = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    return "\n\n".join(sql for (sql,) in rows)


def run_sql(db_path: Path, query: str) -> str:
    """Run one SQL query. Returns a header line, then one line per row, at most MAX_ROWS rows.

    When there are more rows, a first line says how many: "[showing rows 1-50 of 112. ...]".
    """
    # A new connection per call: nothing stays open between questions.
    with closing(connect_read_only(db_path)) as con:
        cursor = con.execute(query)  # Python's sqlite3 refuses more than one statement here
        if cursor.description is None:
            return "(no rows)"
        header = " | ".join(column[0] for column in cursor.description)
        rows = cursor.fetchmany(MAX_ROWS)
        # Count the rows we won't show, so the note can give the real total.
        # (Counting is cheap; the time limit still stops a query that never ends.)
        total = len(rows) + sum(1 for _ in cursor)

    if not rows:
        return "(no rows)"
    lines = [header] + [" | ".join("" if v is None else str(v) for v in row) for row in rows]
    if total > len(rows):
        # The note goes first, with the real total. In step 3 the model read a note at the end,
        # "only the first 50", as "there are 50 invoices". There were 112.
        note = f"[showing rows 1-{len(rows)} of {total}. Use WHERE, GROUP BY, or LIMIT/OFFSET for other rows.]"
        lines.insert(0, note)
    return "\n".join(lines)


def make_sql_tools(db_path: Path) -> list[Tool]:
    """The two SQL tools, bound to one database file."""
    return [
        Tool(
            name="describe_tables",
            description=DESCRIBE_TABLES_DESCRIPTION,
            parameters={"type": "object", "properties": {}},
            fn=partial(describe_tables, db_path),
        ),
        Tool(
            name="run_sql",
            description=RUN_SQL_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "One SQLite SELECT statement"}},
                "required": ["query"],
            },
            fn=partial(run_sql, db_path),
        ),
    ]
