"""Tools that read files from the data folder: list, text, PDF and Excel.

Every path the model sends goes through safe_path first. That is the whole
sandbox for now: the model can name any path it likes, but only paths that
end up inside the data folder are opened.
"""

from functools import partial
from pathlib import Path

import openpyxl
from pypdf import PdfReader

from harness.tools import Tool

MISSING_DATA_HINT = "No practice data yet. Run: uv run make-data"
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json"}
EXCEL_PAGE_ROWS = 30  # rows per read_excel call; 30 rows of this sheet are about 2000 characters


def safe_path(data_dir: Path, relative: str) -> Path:
    """Turn a path from the model into a real path, refusing anything outside data_dir."""
    root = data_dir.resolve()
    if not root.is_dir():
        raise ValueError(MISSING_DATA_HINT)
    # resolve() removes ".." and follows symlinks, so the check below sees where the path really goes.
    # An absolute path like "/etc/passwd" replaces root entirely, and is caught the same way.
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path '{relative}' is outside the data folder")
    return target


def _existing_file(data_dir: Path, path: str) -> Path:
    target = safe_path(data_dir, path)
    if not target.is_file():
        raise ValueError(f"no file '{path}' in the data folder. Use list_files to see what exists.")
    return target


def _wrong_type(path: str, expected: str) -> ValueError:
    """The error for a reader given the wrong kind of file. It names the right tool for each kind."""
    return ValueError(
        f"'{path}' is not {expected}. Use read_text for .txt/.md/.csv/.json, read_pdf for .pdf, "
        "read_excel for .xlsx, run_sql for erp.db."
    )


def list_files(data_dir: Path, path: str = ".") -> str:
    folder = safe_path(data_dir, path)
    if not folder.is_dir():
        raise ValueError(f"'{path}' is not a folder in the data folder")
    root = data_dir.resolve()
    lines = []
    for file in sorted(p for p in folder.rglob("*") if p.is_file()):
        size_kb = max(1, round(file.stat().st_size / 1024))
        lines.append(f"{file.relative_to(root)}  ({size_kb} KB)")
    return "\n".join(lines) or "(no files)"


def read_text(data_dir: Path, path: str) -> str:
    file = _existing_file(data_dir, path)
    if file.suffix.lower() not in TEXT_SUFFIXES:
        raise _wrong_type(path, "a text file")
    return file.read_text(encoding="utf-8")


def read_pdf(data_dir: Path, path: str, page: int | None = None) -> str:
    file = _existing_file(data_dir, path)
    if file.suffix.lower() != ".pdf":
        raise _wrong_type(path, "a PDF")
    pages = PdfReader(file).pages
    total = len(pages)
    if page is None:
        numbers = range(1, total + 1)
    else:
        page = int(page)  # small models sometimes send "2" instead of 2
        if not 1 <= page <= total:
            raise ValueError(f"page {page} doesn't exist. This PDF has {total} pages.")
        numbers = [page]
    return "\n".join(f"--- page {n} of {total} ---\n{pages[n - 1].extract_text()}" for n in numbers)


def read_excel(
    data_dir: Path, path: str, sheet: str | None = None, start_row: int = 1, max_rows: int = EXCEL_PAGE_ROWS
) -> str:
    """Read one page of rows. The second line says which rows these are and where the next page starts."""
    file = _existing_file(data_dir, path)
    if file.suffix.lower() != ".xlsx":
        raise _wrong_type(path, "an .xlsx file")
    book = openpyxl.load_workbook(file, data_only=True)
    if sheet is not None and sheet not in book.sheetnames:
        raise ValueError(f"no sheet '{sheet}'. Sheets: {', '.join(book.sheetnames)}")
    ws = book[sheet] if sheet else book.active
    total = ws.max_row

    start_row, max_rows = int(start_row), int(max_rows)  # models send "41" as often as 41
    if not 1 <= start_row <= total:
        raise ValueError(f"start_row {start_row} is out of range. This sheet has rows between 1 and {total}.")
    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    # The page size is a ceiling, not a default. A model once asked for max_rows=1000; the whole
    # sheet came back, cap_output cut it, and the paging note still said "end of sheet".
    max_rows = min(max_rows, EXCEL_PAGE_ROWS)
    end_row = min(start_row + max_rows - 1, total)

    def row_line(n: int) -> str:
        # Row numbers match what you see in Excel, so the model can say "row 12".
        cells = []
        for cell in ws[n]:
            cells.append("" if cell.value is None else str(cell.value))
        return f"{n}: " + " | ".join(cells)

    if end_row < total:
        note = f"[rows {start_row}-{end_row} of {total}. Next page: start_row={end_row + 1}]"
    else:
        note = f"[rows {start_row}-{end_row} of {total}, end of sheet]"
    lines = [f"Sheets: {', '.join(book.sheetnames)}", note]
    if start_row > 1:
        lines.append(row_line(1))  # the header row, so every page shows the column names
    for n in range(start_row, end_row + 1):
        lines.append(row_line(n))
    return "\n".join(lines)


def make_file_tools(data_dir: Path) -> list[Tool]:
    """The four file tools, each bound to one data folder."""
    path_param = {"type": "string", "description": "Path inside the data folder, like invoices/INV-2026-0001.pdf"}
    return [
        Tool(
            name="list_files",
            description="List the files in the data folder (or a folder inside it), with sizes. Start here.",
            parameters={"type": "object", "properties": {"path": {**path_param, "description": "Folder. Default: all."}}},
            fn=partial(list_files, data_dir),
        ),
        Tool(
            name="read_text",
            description="Read a text file (.txt, .md, .csv, .json) from the data folder.",
            parameters={"type": "object", "properties": {"path": path_param}, "required": ["path"]},
            fn=partial(read_text, data_dir),
        ),
        Tool(
            name="read_pdf",
            description="Read the text of a PDF from the data folder. Use page=N to read one page of a long PDF.",
            parameters={
                "type": "object",
                "properties": {"path": path_param, "page": {"type": "integer", "description": "Page number, from 1"}},
                "required": ["path"],
            },
            fn=partial(read_pdf, data_dir),
        ),
        Tool(
            name="read_excel",
            description=(
                f"Read an Excel sheet (.xlsx) from the data folder, {EXCEL_PAGE_ROWS} numbered rows at a time. "
                "The reply says which rows it holds and the start_row of the next page."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": path_param,
                    "sheet": {"type": "string", "description": "Default: first sheet"},
                    "start_row": {"type": "integer", "description": "First row to read. Use the start_row from the [rows ...] note."},
                    "max_rows": {"type": "integer", "description": f"Rows per page, at most {EXCEL_PAGE_ROWS}."},
                },
                "required": ["path"],
            },
            fn=partial(read_excel, data_dir),
        ),
    ]
