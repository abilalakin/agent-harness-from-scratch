"""Tools that query the ERP database, read-only.

The model writes the SQL, so the SQL can't be trusted. Instead of checking the
text of each query (easy to get wrong), the database itself refuses to change:
- the file is opened with mode=ro, so SQLite rejects every write,
- attaching other database files is turned off, so a query can't open (or create) another file.
"""

import sqlite3
from contextlib import closing
from functools import partial
from pathlib import Path

from harness.file_tools import MISSING_DATA_HINT
from harness.tools import Tool

MAX_ROWS = 50


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    # Check first: connecting to a missing file would otherwise fail with a vague error.
    if not db_path.is_file():
        raise ValueError(MISSING_DATA_HINT)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    return con


def describe_tables(db_path: Path) -> str:
    """The CREATE TABLE statement of every table: column names, types and links."""
    with closing(connect_read_only(db_path)) as con:
        rows = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    return "\n\n".join(sql for (sql,) in rows)


def run_sql(db_path: Path, query: str) -> str:
    """Run one SQL query. Returns a header line, then one line per row, at most MAX_ROWS rows."""
    # A new connection per call: nothing stays open between questions.
    with closing(connect_read_only(db_path)) as con:
        cursor = con.execute(query)  # Python's sqlite3 refuses more than one statement here
        if cursor.description is None:
            return "(no rows)"
        header = " | ".join(column[0] for column in cursor.description)
        # Ask for one row more than we show. If it arrives, we know the result was cut.
        rows = cursor.fetchmany(MAX_ROWS + 1)

    if not rows:
        return "(no rows)"
    lines = [header] + [" | ".join("" if v is None else str(v) for v in row) for row in rows[:MAX_ROWS]]
    if len(rows) > MAX_ROWS:
        lines.append(f"...[more rows not shown, only the first {MAX_ROWS}. Use WHERE, GROUP BY or LIMIT.]")
    return "\n".join(lines)


def make_sql_tools(db_path: Path) -> list[Tool]:
    """The two SQL tools, bound to one database file."""
    return [
        Tool(
            name="describe_tables",
            description="Show the tables of the ERP database (erp.db) and their columns. Call this before run_sql.",
            parameters={"type": "object", "properties": {}},
            fn=partial(describe_tables, db_path),
        ),
        Tool(
            name="run_sql",
            description=(
                "Run one read-only SQLite query on the ERP database and get the rows back. "
                f"At most {MAX_ROWS} rows are shown, so filter or aggregate in SQL. Writes are refused."
            ),
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "One SQLite SELECT statement"}},
                "required": ["query"],
            },
            fn=partial(run_sql, db_path),
        ),
    ]
