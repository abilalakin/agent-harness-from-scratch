"""Tools that read files from the data folder: list, text, PDF and Excel.

Every path the model sends goes through safe_path first. That is the whole
sandbox for now: the model can name any path it likes, but only paths that
end up inside the data folder are opened.
"""

from functools import partial
from pathlib import Path

import openpyxl
from pypdf import PdfReader

from harness.tools import MAX_TOOL_OUTPUT, Tool

MISSING_DATA_HINT = "No practice data yet. Run: uv run make-data"
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json"}
EXCEL_PAGE_ROWS = 30  # rows per read_excel call, at most
MAX_MATCHES = 30  # search results per call


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


def _files_below(data_dir: Path, path: str) -> list[Path]:
    """Every file below a folder in the data folder, sorted. A symlink that leads outside is left out:
    safe_path checked the folder, but rglob would happily follow a link inside it to anywhere."""
    folder = safe_path(data_dir, path)
    if not folder.is_dir():
        raise ValueError(f"'{path}' is not a folder in the data folder")
    root = data_dir.resolve()
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.resolve().is_relative_to(root))


def list_files(data_dir: Path, path: str = ".") -> str:
    root = data_dir.resolve()
    lines = []
    for file in _files_below(data_dir, path):
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
    # read_only: only the rows we ask for are read, instead of every cell in the file.
    book = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        if sheet is not None and sheet not in book.sheetnames:
            raise ValueError(f"no sheet '{sheet}'. Sheets: {', '.join(book.sheetnames)}")
        ws = book[sheet] if sheet else book.active
        total = ws.max_row
        if total is None:  # a file written without a size hint: count the rows
            total = sum(1 for _ in ws.iter_rows())

        start_row, max_rows = int(start_row), int(max_rows)  # models send "41" as often as 41
        if not 1 <= start_row <= total:
            raise ValueError(f"start_row {start_row} is out of range. This sheet has rows between 1 and {total}.")
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1")
        # EXCEL_PAGE_ROWS is a ceiling, whatever the model asks for. The character budget below is
        # what really keeps a page under the output cap; the ceiling keeps pages a readable size.
        last_wanted = min(start_row + min(max_rows, EXCEL_PAGE_ROWS) - 1, total)

        def row_lines(first: int, last: int):
            # Row numbers match what you see in Excel, so the model can say "row 12".
            for n, values in enumerate(ws.iter_rows(min_row=first, max_row=last, values_only=True), first):
                yield f"{n}: " + row_text(values)

        lines = [f"Sheets: {', '.join(book.sheetnames)}"]
        if start_row > 1:
            lines += row_lines(1, 1)  # the header row, so every page shows the column names

        # A page is limited by rows AND by characters, so cap_output never has to cut one.
        # Count what is already in the page, plus room for the note (its longest form).
        size = sum(len(line) + 1 for line in lines)
        size += len(f"[rows {start_row}-{total} of {total}. Next page: start_row={total + 1}]") + 1
        rows_out = []
        for line in row_lines(start_row, last_wanted):
            if rows_out and size + len(line) + 1 > MAX_TOOL_OUTPUT:
                break
            rows_out.append(line)
            size += len(line) + 1
    finally:
        book.close()

    # The note is written after, from the rows that really made it, so it is always true.
    end_row = start_row + len(rows_out) - 1
    if end_row < total:
        note = f"[rows {start_row}-{end_row} of {total}. Next page: start_row={end_row + 1}]"
    else:
        note = f"[rows {start_row}-{end_row} of {total}, end of sheet]"
    lines.insert(1, note)
    return "\n".join(lines + rows_out)


def row_text(values) -> str:
    """One row as 'a | b | c'. Empty cells become empty strings. Shared with the SQL tool."""
    return " | ".join("" if v is None else str(v) for v in values)


# --- Search ---------------------------------------------------------------
#
# One small generator per file type. Each yields (location, text) pairs, where
# location is what the model needs to follow up: "page 1" → read_pdf page=1,
# "row 12" → read_excel start_row=12.


def _text_lines(file: Path):
    for n, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        yield f"line {n}", line


def _pdf_lines(file: Path):
    for n, page in enumerate(PdfReader(file).pages, 1):
        for line in (page.extract_text() or "").splitlines():
            yield f"page {n}", line


def _excel_rows(file: Path):
    book = openpyxl.load_workbook(file, read_only=True, data_only=True)
    for sheet in book.worksheets:
        # With several sheets, "row 12" alone would send read_excel to the wrong one.
        where = f"sheet {sheet.title} row" if len(book.worksheets) > 1 else "row"
        for n, row in enumerate(sheet.iter_rows(values_only=True), 1):
            yield f"{where} {n}", row_text(row)


_SEARCHERS = {".pdf": _pdf_lines, ".xlsx": _excel_rows}
for suffix in TEXT_SUFFIXES:
    _SEARCHERS[suffix] = _text_lines


def search_files(data_dir: Path, query: str, path: str = ".") -> str:
    """Find a word or number in every file below path. Returns only the matching lines, with where they are.

    Case-insensitive. Files no searcher understands (like erp.db) are skipped: use run_sql for those.
    """
    query = query.strip()
    if not query:
        raise ValueError("the query is empty")
    root = data_dir.resolve()
    needle = query.lower()

    matches, total = [], 0  # keep the first MAX_MATCHES, count the rest
    for file in _files_below(data_dir, path):
        searcher = _SEARCHERS.get(file.suffix.lower())
        if searcher is None:
            continue
        for location, text in searcher(file):
            if needle in text.lower():
                total += 1
                if len(matches) < MAX_MATCHES:
                    matches.append(f"{file.relative_to(root)} {location}: {text.strip()}")

    if not matches:
        return f"(no matches for '{query}')"
    if total > MAX_MATCHES:
        matches.insert(0, f"[showing {MAX_MATCHES} of {total} matches. Use a more specific query or a path.]")
    return "\n".join(matches)


def make_file_tools(data_dir: Path) -> list[Tool]:
    """The five file tools, each bound to one data folder."""
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
        Tool(
            name="search_files",
            description=(
                "Find a word or number in all text, PDF and Excel files in the data folder. Returns only the "
                "matching lines, with the file and page or row. Use it for questions about many files, "
                "instead of reading each file. The database is not searched: use run_sql."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to look for, case does not matter"},
                    "path": {**path_param, "description": "Folder to search. Default: all."},
                },
                "required": ["query"],
            },
            fn=partial(search_files, data_dir),
        ),
    ]
