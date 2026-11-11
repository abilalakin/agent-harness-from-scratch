import pytest

from harness.file_tools import (
    MAX_MATCHES,
    list_files,
    make_file_tools,
    read_excel,
    read_pdf,
    read_text,
    safe_path,
    search_files,
)
from harness.practice_data import make_all
from harness.tools import run_tool_call


def test_safe_path_allows_inside(data_dir):
    assert safe_path(data_dir, "invoices/INV-2026-0001.pdf").is_file()


@pytest.mark.parametrize("bad", ["../secret.txt", "../../.ssh/id_ed25519", "/etc/passwd", "invoices/../../x"])
def test_safe_path_refuses_outside(data_dir, bad):
    with pytest.raises(ValueError, match="outside the data folder"):
        safe_path(data_dir, bad)


def test_safe_path_refuses_symlink_leading_outside(tmp_path):
    make_all(tmp_path / "d")
    (tmp_path / "secret.txt").write_text("s")
    (tmp_path / "d" / "link.txt").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(ValueError, match="outside the data folder"):
        safe_path(tmp_path / "d", "link.txt")


def test_list_files_shows_relative_paths(data_dir):
    out = list_files(data_dir)
    assert "invoices/INV-2026-0001.pdf" in out and "legacy/customers_export.xlsx" in out


def test_read_text_reads_readme(data_dir):
    assert "erp.db" in read_text(data_dir, "README.txt")


@pytest.mark.parametrize(
    "path, tool",
    [("invoices/INV-2026-0001.pdf", "read_pdf"), ("legacy/customers_export.xlsx", "read_excel"), ("erp.db", "run_sql")],
)
def test_read_text_points_to_the_right_tool(data_dir, path, tool):
    with pytest.raises(ValueError, match=tool):
        read_text(data_dir, path)


def test_read_pdf_marks_pages_and_can_pick_one(data_dir):
    full = read_pdf(data_dir, "contracts/supply-agreement.pdf")
    assert "--- page 1 of 2 ---" in full and "--- page 2 of 2 ---" in full
    page_two = read_pdf(data_dir, "contracts/supply-agreement.pdf", page=2)
    assert "--- page 2 of 2 ---" in page_two and "--- page 1 of 2 ---" not in page_two


EXPORT = "legacy/customers_export.xlsx"


def test_read_excel_first_page_says_where_next_page_starts(data_dir):
    lines = read_excel(data_dir, EXPORT).splitlines()
    assert lines[0] == "Sheets: Customers"
    assert lines[1] == "[rows 1-30 of 56. Next page: start_row=31]"
    assert lines[2].startswith("1: Cust Name | E-Mail") and lines[-1].startswith("30: ")


def test_read_excel_last_page_repeats_header_and_says_end(data_dir):
    lines = read_excel(data_dir, EXPORT, start_row="41").splitlines()  # a string, as models send it
    assert lines[1] == "[rows 41-56 of 56, end of sheet]"
    assert lines[2].startswith("1: Cust Name") and lines[3].startswith("41: ") and lines[-1].startswith("56: ")


def test_read_excel_max_rows(data_dir):
    note = read_excel(data_dir, EXPORT, start_row=10, max_rows=5).splitlines()[1]
    assert note == "[rows 10-14 of 56. Next page: start_row=15]"


def test_read_excel_max_rows_cannot_exceed_the_page_size(data_dir):
    # A model asked for max_rows=1000 once, got the whole sheet, and cap_output cut it while the
    # paging note still said "end of sheet". The page size is the ceiling.
    note = read_excel(data_dir, EXPORT, max_rows=1000).splitlines()[1]
    assert note == "[rows 1-30 of 56. Next page: start_row=31]"


@pytest.mark.parametrize("start_row", [0, -1, 57, 99])
def test_read_excel_start_row_out_of_range(data_dir, start_row):
    with pytest.raises(ValueError, match="between 1 and 56"):
        read_excel(data_dir, EXPORT, start_row=start_row)


def test_every_excel_row_is_reachable(data_dir):
    seen, start = set(), 1
    while True:
        lines = read_excel(data_dir, EXPORT, start_row=start).splitlines()
        seen |= {int(line.split(":")[0]) for line in lines[2:]}
        if "end of sheet" in lines[1]:
            break
        start = int(lines[1].split("start_row=")[1].rstrip("]"))
    assert seen == set(range(1, 57))


@pytest.mark.parametrize(
    "reader, path, right_tool",
    [(read_pdf, "legacy/customers_export.xlsx", "read_excel"), (read_excel, "invoices/INV-2026-0001.pdf", "read_pdf")],
)
def test_wrong_reader_names_the_right_tool(data_dir, reader, path, right_tool):
    with pytest.raises(ValueError, match=right_tool):
        reader(data_dir, path)


def test_missing_file_says_use_list_files(data_dir):
    with pytest.raises(ValueError, match="Use list_files"):
        read_pdf(data_dir, "invoices/nope.pdf")


def test_missing_data_folder_gives_make_data_hint(tmp_path):
    with pytest.raises(ValueError, match="uv run make-data"):
        list_files(tmp_path / "nothing-here")


def test_tools_run_through_run_tool_call(data_dir):
    tools = {t.name: t for t in make_file_tools(data_dir)}
    out = run_tool_call(
        tools,
        {"id": "c1", "type": "function", "function": {"name": "read_text", "arguments": '{"path": "../../etc/passwd"}'}},
    )
    assert out.startswith("Error: tool 'read_text' failed:") and "outside the data folder" in out


def test_search_finds_every_invoice_total_with_location(data_dir):
    lines = search_files(data_dir, "total:").splitlines()
    pdf_lines = [line for line in lines if line.startswith("invoices/")]
    assert [line.split(" page")[0] for line in pdf_lines] == [f"invoices/INV-2026-000{n}.pdf" for n in range(1, 6)]
    assert all(" page 1: Total: " in line and line.endswith(" EUR") for line in pdf_lines)


def test_search_excel_rows_case_insensitive(data_dir):
    out = search_files(data_dir, "BLUE SKY", path="legacy")
    assert out and all(line.startswith("legacy/customers_export.xlsx row ") for line in out.splitlines())


def test_search_text_files_by_line(data_dir):
    assert search_files(data_dir, "SQLite database").startswith("README.txt line ")


def test_search_no_match(data_dir):
    assert search_files(data_dir, "zzz-not-there") == "(no matches for 'zzz-not-there')"


def test_search_many_matches_says_total_first(data_dir):
    first = search_files(data_dir, "info@").splitlines()[0]
    assert first.startswith(f"[showing {MAX_MATCHES} of ") and "matches" in first


def test_search_skips_the_database_file(data_dir):
    assert "erp.db" not in search_files(data_dir, "customers")


def test_search_refuses_paths_outside(data_dir):
    with pytest.raises(ValueError, match="outside the data folder"):
        search_files(data_dir, "x", path="../")


def test_search_empty_query(data_dir):
    with pytest.raises(ValueError, match="empty"):
        search_files(data_dir, "  ")


def test_search_is_a_tool(data_dir):
    assert "search_files" in {t.name for t in make_file_tools(data_dir)}
