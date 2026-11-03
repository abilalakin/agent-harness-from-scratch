"""Fake ERP practice data: a database, invoice PDFs, a contract and a messy Excel export.

Everything comes from one seeded random generator, so `uv run make-data` makes the
same data every time. Two problems are planted on purpose:
- Invoice 3's PDF total is 100.00 EUR higher than the database says.
- The legacy Excel export writes existing customers in messy ways, for the step 7 migration.
"""

import random
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from fpdf import FPDF

from harness.config import load_settings

INVOICE_PDF_COUNT = 5
WRONG_PDF_INVOICE = 3  # the invoice whose PDF total doesn't match the database
WRONG_PDF_EXTRA = 100.00

NAME_STARTS = ["Atlas", "Northwind", "Blue Sky", "Meridian", "Falcon",
               "Harbor", "Summit", "Polaris", "Redwood", "Silverline"]
NAME_ENDS = ["Ltd", "GmbH", "Aero", "Logistics", "Trading", "Industries"]
NEW_NAME_STARTS = ["Orion", "Cedar", "Vertex", "Lumen", "Boreal",
                   "Kestrel", "Granite", "Aurora", "Tidewater", "Ironbridge"]
CITIES = [("Istanbul", "TR"), ("Ankara", "TR"), ("Berlin", "DE"), ("Munich", "DE"),
          ("London", "GB"), ("Paris", "FR"), ("Amsterdam", "NL"), ("Milan", "IT")]
PRODUCTS = ["Hydraulic pump", "Brake pad set", "Oil filter", "Fuel nozzle", "Cabin light panel",
            "Seat belt kit", "Tire 26x6.6", "Landing light", "Air filter", "Starter generator",
            "Pitot tube", "Window seal", "Battery 24V", "Oxygen mask", "Fire extinguisher",
            "Spark plug set", "Torque wrench", "Inspection mirror", "Cable harness", "Sealant tube"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SELLER = "Harness Practice Parts GmbH"


def invoice_number(n: int) -> str:
    return f"INV-2026-{n:04d}"


def make_all(data_dir: Path, seed: int = 42) -> None:
    """Write all practice data into data_dir. Same seed, same data."""
    rng = random.Random(seed)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "erp.db"
    db_path.unlink(missing_ok=True)

    con = sqlite3.connect(db_path)
    _make_db(con, rng)
    _make_invoice_pdfs(con, data_dir / "invoices")
    _make_contract_pdf(data_dir / "contracts")
    _make_excel(con, rng, data_dir / "legacy")
    _make_readme(data_dir)
    con.close()


# --- The database -----------------------------------------------------------


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _email(name: str) -> str:
    # .example is reserved for examples, so these can never be real addresses.
    return "info@" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".example"


def _make_db(con: sqlite3.Connection, rng: random.Random) -> None:
    con.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT,
                                city TEXT, country TEXT, created_at TEXT);
        CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, unit_price REAL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers,
                             order_date TEXT, status TEXT);
        CREATE TABLE order_lines (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders,
                                  product_id INTEGER REFERENCES products, quantity INTEGER, unit_price REAL);
        CREATE TABLE invoices (id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders,
                               invoice_number TEXT, issued_at TEXT, due_at TEXT, total REAL, paid INTEGER);
        """
    )

    names = rng.sample([f"{a} {b}" for a in NAME_STARTS for b in NAME_ENDS], 50)
    for name in names:
        city, country = rng.choice(CITIES)
        created = _random_date(rng, date(2020, 1, 1), date(2025, 12, 31))
        con.execute(
            "INSERT INTO customers (name, email, city, country, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, _email(name), city, country, created.isoformat()),
        )

    prices = {}
    for i, product in enumerate(PRODUCTS, start=1):
        prices[i] = round(rng.uniform(10, 2000), 2)
        con.execute("INSERT INTO products (sku, name, unit_price) VALUES (?, ?, ?)", (f"P-{i:03d}", product, prices[i]))

    next_invoice = 1
    for order_id in range(1, 201):
        order_date = _random_date(rng, date(2025, 1, 1), date(2026, 10, 31))
        status = rng.choices(["shipped", "open", "cancelled"], weights=[60, 25, 15])[0]
        con.execute(
            "INSERT INTO orders (id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
            (order_id, rng.randint(1, 50), order_date.isoformat(), status),
        )

        total = 0.0
        for product_id in rng.sample(range(1, 21), rng.randint(1, 4)):
            quantity = rng.randint(1, 10)
            total += quantity * prices[product_id]
            con.execute(
                "INSERT INTO order_lines (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (order_id, product_id, quantity, prices[product_id]),
            )

        if status == "shipped":
            issued = order_date + timedelta(days=rng.randint(1, 10))
            con.execute(
                "INSERT INTO invoices (order_id, invoice_number, issued_at, due_at, total, paid) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, invoice_number(next_invoice), issued.isoformat(),
                 (issued + timedelta(days=30)).isoformat(), round(total, 2), int(rng.random() < 0.7)),
            )
            next_invoice += 1
    con.commit()


# --- PDFs -------------------------------------------------------------------


def _new_pdf() -> FPDF:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)  # built-in font: plain ASCII text only
    return pdf


def _write(pdf: FPDF, text: str) -> None:
    pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")


def _make_invoice_pdfs(con: sqlite3.Connection, folder: Path) -> None:
    folder.mkdir(exist_ok=True)
    for n in range(1, INVOICE_PDF_COUNT + 1):
        number = invoice_number(n)
        order_id, issued, due, total, customer = con.execute(
            """SELECT i.order_id, i.issued_at, i.due_at, i.total, c.name
               FROM invoices i JOIN orders o ON o.id = i.order_id JOIN customers c ON c.id = o.customer_id
               WHERE i.invoice_number = ?""",
            (number,),
        ).fetchone()
        lines = con.execute(
            """SELECT p.name, l.quantity, l.unit_price FROM order_lines l
               JOIN products p ON p.id = l.product_id WHERE l.order_id = ? ORDER BY l.id""",
            (order_id,),
        ).fetchall()

        if n == WRONG_PDF_INVOICE:
            total += WRONG_PDF_EXTRA  # planted mistake: the PDF disagrees with the database

        pdf = _new_pdf()
        _write(pdf, f"INVOICE\nSeller: {SELLER}\nInvoice number: {number}\nOrder: {order_id}")
        _write(pdf, f"Customer: {customer}\nIssued: {issued}\nDue: {due}\n")
        for product, quantity, price in lines:
            _write(pdf, f"{product}  x{quantity}  @ {price:.2f}  = {quantity * price:.2f} EUR")
        _write(pdf, f"\nTotal: {total:.2f} EUR")
        pdf.output(str(folder / f"{number}.pdf"))


CONTRACT_PAGE_1 = f"""SUPPLY AGREEMENT

Between {SELLER} ("Seller") and the Buyer named in each order ("Buyer").

1. Scope. The Seller supplies aircraft spare parts and tools listed in its product catalogue.
Each order placed by the Buyer is a separate purchase under this agreement.

2. Prices. Prices are the catalogue prices on the order date, in EUR, without VAT.
The Seller may change catalogue prices with 60 days written notice.

3. Delivery. The Seller ships within 10 working days after accepting an order.
Risk passes to the Buyer when the goods are handed to the carrier.
"""

CONTRACT_PAGE_2 = """4. Invoices and payment. The Seller invoices each order when it ships.
Payment terms are net 30 days from the invoice date.
Late payments carry a penalty of 1.5% per month on the open amount.

5. Term. This agreement runs for two years and renews for one year at a time,
unless either party ends it with 90 days written notice.

6. Law. This agreement is governed by the laws of Germany.
"""


def _make_contract_pdf(folder: Path) -> None:
    folder.mkdir(exist_ok=True)
    pdf = _new_pdf()
    _write(pdf, CONTRACT_PAGE_1)
    pdf.add_page()
    _write(pdf, CONTRACT_PAGE_2)
    pdf.output(str(folder / "supply-agreement.pdf"))


# --- The messy Excel export -------------------------------------------------


def _messy_name(rng: random.Random, name: str) -> str:
    """The same company, written the way old systems and tired people write it."""
    if name.endswith(" Ltd") and rng.random() < 0.4:
        return name[: -len("Ltd")] + "Limited"
    return rng.choice([str.upper, str.lower, lambda s: s + ".", lambda s: s.replace(" ", "  ") + " "])(name)


def _messy_date(rng: random.Random, iso: str) -> str:
    d = date.fromisoformat(iso)
    return rng.choice([d.isoformat(), d.strftime("%d/%m/%Y"), f"{d.day} {MONTHS[d.month - 1]} {d.year}"])


def _make_excel(con: sqlite3.Connection, rng: random.Random, folder: Path) -> None:
    folder.mkdir(exist_ok=True)
    rows = []

    customers = con.execute("SELECT name, email, city, country, created_at FROM customers").fetchall()
    for name, email, city, country, created in rng.sample(customers, 40):
        rows.append((
            _messy_name(rng, name),
            email.upper() if rng.random() < 0.3 else email,
            city if rng.random() < 0.7 else city.lower() + " ",
            country if rng.random() < 0.7 else country.lower(),
            _messy_date(rng, created),
        ))

    for start in NEW_NAME_STARTS:
        name = f"{start} {rng.choice(NAME_ENDS)}"
        city, country = rng.choice(CITIES)
        rows.append((name, _email(name), city, country, _messy_date(rng, "2026-06-01")))

    rows += rng.sample(rows, 3)  # exact duplicates, as old exports often have
    rng.shuffle(rows)
    empty = (None, None, None, None, None)
    rows.insert(10, empty)  # empty rows in the middle, where a reader can't skip them by accident
    rows.insert(30, empty)

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Customers"
    sheet.append(["Cust Name", "E-Mail", "Town", "Country Code", "Since"])
    for row in rows:
        sheet.append(list(row))
    book.save(folder / "customers_export.xlsx")


# --- README -----------------------------------------------------------------

README = """PRACTICE DATA (all fake, made by `uv run make-data`)

erp.db          SQLite database of a small spare-parts seller.
                Tables: customers, products, orders, order_lines, invoices.
                An invoice exists for every shipped order. paid is 1 or 0.
invoices/       PDF copies of the first 5 invoices (INV-2026-0001 to INV-2026-0005).
contracts/      supply-agreement.pdf: the terms between the seller and its buyers.
legacy/         customers_export.xlsx: a customer list exported from an old system.
                It is messy: names, dates and emails are written in different ways.
"""


def _make_readme(data_dir: Path) -> None:
    (data_dir / "README.txt").write_text(README)


def main() -> None:
    data_dir = load_settings().data_dir
    make_all(data_dir)
    print(f"Practice data written to {data_dir.resolve()}:")
    for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        print(f"  {path.relative_to(data_dir)}")
