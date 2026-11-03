import pytest

from harness.file_tools import list_files, make_file_tools, read_excel, read_pdf, read_text, safe_path
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


def test_read_excel_lists_sheets_and_header(data_dir):
    out = read_excel(data_dir, "legacy/customers_export.xlsx")
    assert out.splitlines()[0] == "Sheets: Customers"
    assert "Cust Name | E-Mail | Town | Country Code | Since" in out


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
