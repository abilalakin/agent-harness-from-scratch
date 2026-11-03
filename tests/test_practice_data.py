import re
import sqlite3

import openpyxl
from pypdf import PdfReader

from harness.practice_data import INVOICE_PDF_COUNT, invoice_number, make_all


def db(data_dir) -> sqlite3.Connection:
    return sqlite3.connect(data_dir / "erp.db")


def pdf_text(path) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(path).pages)


def normalize(name: str) -> str:
    """How a careful person would compare company names."""
    name = re.sub(r"[^\w\s]", "", name.lower())
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"\blimited\b", "ltd", name)


def test_tables_and_row_counts(data_dir):
    con = db(data_dir)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["customers", "products", "orders"]}
    assert counts == {"customers": 50, "products": 20, "orders": 200}


def test_orders_have_one_to_four_lines(data_dir):
    rows = db(data_dir).execute("SELECT COUNT(*) FROM order_lines GROUP BY order_id").fetchall()
    assert len(rows) == 200
    assert all(1 <= n <= 4 for (n,) in rows)


def test_one_invoice_per_shipped_order(data_dir):
    con = db(data_dir)
    shipped = con.execute("SELECT COUNT(*) FROM orders WHERE status = 'shipped'").fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == shipped > 0


def test_invoice_total_matches_its_lines(data_dir):
    rows = db(data_dir).execute(
        """SELECT i.total, ROUND(SUM(l.quantity * l.unit_price), 2)
           FROM invoices i JOIN order_lines l ON l.order_id = i.order_id
           GROUP BY i.id"""
    ).fetchall()
    assert rows and all(abs(total - expected) < 0.005 for total, expected in rows)


def test_same_seed_same_data(tmp_path):
    make_all(tmp_path / "a")
    make_all(tmp_path / "b")
    query = "SELECT * FROM customers ORDER BY id"
    assert db(tmp_path / "a").execute(query).fetchall() == db(tmp_path / "b").execute(query).fetchall()


def test_invoice_pdfs_exist_and_exactly_one_total_disagrees(data_dir):
    pdfs = sorted((data_dir / "invoices").glob("*.pdf"))
    assert [p.stem for p in pdfs] == [invoice_number(n) for n in range(1, INVOICE_PDF_COUNT + 1)]

    con = db(data_dir)
    mismatches = []
    for pdf in pdfs:
        text = pdf_text(pdf)
        assert f"Invoice number: {pdf.stem}" in text
        pdf_total = float(re.search(r"Total: ([\d.]+) EUR", text).group(1))
        (db_total,) = con.execute("SELECT total FROM invoices WHERE invoice_number = ?", (pdf.stem,)).fetchone()
        if abs(pdf_total - db_total) > 0.005:
            mismatches.append(pdf.stem)
    assert mismatches == [invoice_number(3)]


def test_contract_pdf_has_two_pages_and_payment_terms(data_dir):
    path = data_dir / "contracts" / "supply-agreement.pdf"
    assert len(PdfReader(path).pages) == 2
    text = pdf_text(path)
    assert "net 30 days" in text and "1.5%" in text


def test_excel_export_is_messy_on_purpose(data_dir):
    rows = list(openpyxl.load_workbook(data_dir / "legacy" / "customers_export.xlsx").active.values)
    assert rows[0] == ("Cust Name", "E-Mail", "Town", "Country Code", "Since")
    data = rows[1:]
    assert len(data) == 55  # 40 existing + 10 new + 3 repeats + 2 empty
    assert sum(1 for r in data if all(c in (None, "") for c in r)) == 2

    db_names = {name for (name,) in db(data_dir).execute("SELECT name FROM customers")}
    db_normalized = {normalize(n) for n in db_names}
    variants = [r[0] for r in data if r[0] and r[0] not in db_names and normalize(r[0]) in db_normalized]
    assert len(variants) >= 10


def test_readme_lists_the_files(data_dir):
    text = (data_dir / "README.txt").read_text()
    assert all(name in text for name in ["erp.db", "invoices/", "contracts/", "legacy/"])
