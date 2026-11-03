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
        raise ValueError(
            f"'{path}' is not a text file. Use read_pdf for .pdf, read_excel for .xlsx, run_sql for erp.db."
        )
    return file.read_text(encoding="utf-8")


def read_pdf(data_dir: Path, path: str, page: int | None = None) -> str:
    file = _existing_file(data_dir, path)
    if file.suffix.lower() != ".pdf":
        raise ValueError(f"'{path}' is not a PDF")
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


def read_excel(data_dir: Path, path: str, sheet: str | None = None) -> str:
    file = _existing_file(data_dir, path)
    if file.suffix.lower() != ".xlsx":
        raise ValueError(f"'{path}' is not an .xlsx file")
    book = openpyxl.load_workbook(file, data_only=True)
    if sheet is not None and sheet not in book.sheetnames:
        raise ValueError(f"no sheet '{sheet}'. Sheets: {', '.join(book.sheetnames)}")
    rows = (book[sheet] if sheet else book.active).iter_rows(values_only=True)
    # Row numbers match what you see in Excel, so the model can say "row 12".
    lines = [f"{n}: " + " | ".join("" if cell is None else str(cell) for cell in row) for n, row in enumerate(rows, 1)]
    return f"Sheets: {', '.join(book.sheetnames)}\n" + "\n".join(lines)


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
            description="Read an Excel sheet (.xlsx) from the data folder. Each line is one numbered row.",
            parameters={
                "type": "object",
                "properties": {"path": path_param, "sheet": {"type": "string", "description": "Default: first sheet"}},
                "required": ["path"],
            },
            fn=partial(read_excel, data_dir),
        ),
    ]
