import sqlite3

import pytest

from harness import sql_tools
from harness.practice_data import make_all
from harness.sql_tools import MAX_ROWS, describe_tables, make_sql_tools, run_sql
from harness.tools import run_tool_call


@pytest.fixture
def db_path(data_dir):
    return data_dir / "erp.db"


def test_describe_tables_shows_every_table(db_path):
    out = describe_tables(db_path)
    for table in ["customers", "products", "orders", "order_lines", "invoices"]:
        assert f"CREATE TABLE {table}" in out


def test_select_returns_header_and_rows(db_path):
    lines = run_sql(db_path, "SELECT id, name FROM customers ORDER BY id LIMIT 2").splitlines()
    assert lines[0] == "id | name" and len(lines) == 3


def test_empty_result_says_no_rows(db_path):
    assert run_sql(db_path, "SELECT * FROM customers WHERE id = -1") == "(no rows)"


def test_more_than_max_rows_says_total_first(db_path):
    lines = run_sql(db_path, "SELECT id FROM orders").splitlines()
    assert lines[0] == "[showing rows 1-50 of 200. Use WHERE, GROUP BY, or LIMIT/OFFSET for other rows.]"
    assert lines[1] == "id" and len(lines) == 2 + MAX_ROWS


def test_exactly_max_rows_has_no_note(db_path):
    lines = run_sql(db_path, f"SELECT id FROM orders LIMIT {MAX_ROWS}").splitlines()
    assert lines[0] == "id" and len(lines) == 1 + MAX_ROWS


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM customers",
        "UPDATE customers SET name = 'x'",
        "DROP TABLE customers",
        "INSERT INTO products (sku) VALUES ('x')",
    ],
)
def test_writes_are_refused_and_data_unchanged(db_path, query):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        run_sql(db_path, query)
    assert run_sql(db_path, "SELECT COUNT(*) AS n FROM customers").splitlines()[1] == "50"


def test_two_statements_are_refused(db_path):
    with pytest.raises(sqlite3.ProgrammingError):
        run_sql(db_path, "SELECT 1; DELETE FROM customers")


def test_attach_is_refused(db_path, tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        run_sql(db_path, f"ATTACH DATABASE '{tmp_path / 'new.db'}' AS x")
    assert not (tmp_path / "new.db").exists()


def test_missing_database_gives_make_data_hint(tmp_path):
    with pytest.raises(ValueError, match="uv run make-data"):
        run_sql(tmp_path / "erp.db", "SELECT 1")
    assert not (tmp_path / "erp.db").exists()  # opening read-only must not create an empty file


def test_write_error_reaches_model_as_text(db_path):
    tools = {t.name: t for t in make_sql_tools(db_path)}
    out = run_tool_call(
        tools, {"id": "c1", "type": "function", "function": {"name": "run_sql", "arguments": '{"query": "DELETE FROM orders"}'}}
    )
    assert out.startswith("Error: tool 'run_sql' failed:") and "readonly" in out


def test_special_characters_in_path_keep_read_only(tmp_path):
    # SQLite reads the path as a URI, where "#" and "?" mean something. They must not drop mode=ro.
    data = tmp_path / "my#proj?x"
    make_all(data)
    db = data / "erp.db"
    assert run_sql(db, "SELECT COUNT(*) AS n FROM customers").splitlines()[1] == "50"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        run_sql(db, "CREATE TABLE pwn (a)")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["my#proj?x"]  # no stray database file


def test_runaway_query_is_stopped(db_path, monkeypatch):
    monkeypatch.setattr(sql_tools, "QUERY_TIME_LIMIT_SECONDS", 0.5)
    endless = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        run_sql(db_path, endless)
