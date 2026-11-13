import sqlite3

import pytest

from harness.evals.tasks import (
    TASKS,
    ToolCall,
    all_of,
    called,
    contains,
    looked_at_every_invoice,
    number_near,
    paged_through_excel,
    task_by_id,
)
from harness.file_tools import read_excel, read_pdf
from harness.practice_data import make_all


def test_contains_ignores_case():
    assert contains("Meridian Trading")("It is meridian trading.")
    assert not contains("112")("There are 50 invoices")


def test_number_near_reads_numbers_the_way_people_write_them():
    check = number_near(13701.44)
    assert check("The total is 13,701.44 EUR")
    assert check("Total: 13701 EUR")  # within the default tolerance of 1.0
    assert not check("Total: 13601.44 EUR")  # the database total, 100 off
    assert not check("no numbers here")


def test_number_near_exact_when_tolerance_is_zero():
    assert number_near(2, tolerance=0)("Rows 12 and 32 are empty, so 2 rows")
    assert not number_near(2, tolerance=0)("Row 12 is empty")


def test_all_of_needs_every_check():
    check = all_of(contains("Cable harness"), number_near(1990.35))
    assert check("Cable harness at 1990.35")
    assert not check("Cable harness at 199.35")


def test_task_ids_are_unique_and_lookup_names_the_known_ids():
    assert len({t.id for t in TASKS}) == len(TASKS) == 12
    with pytest.raises(KeyError, match="invoice-count"):
        task_by_id("typo")


def test_expected_answers_match_the_generated_data(tmp_path):
    """The expected values in TASKS come from the seed-42 practice data. If the generator changes, this fails first."""
    make_all(tmp_path)
    con = sqlite3.connect(tmp_path / "erp.db")
    assert con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 112
    assert con.execute("SELECT COUNT(*) FROM invoices WHERE paid = 0").fetchone()[0] == 33
    assert con.execute("SELECT COUNT(*) FROM customers WHERE country = 'DE'").fetchone()[0] == 15
    assert (
        con.execute(
            "SELECT c.name FROM orders o JOIN customers c ON c.id = o.customer_id "
            "GROUP BY c.id ORDER BY COUNT(*) DESC LIMIT 1"
        ).fetchone()[0]
        == "Meridian Trading"
    )
    assert con.execute("SELECT name, unit_price FROM products ORDER BY unit_price DESC LIMIT 1").fetchone() == (
        "Cable harness",
        1990.35,
    )
    assert "Total: 13701.44 EUR" in read_pdf(tmp_path, "invoices/INV-2026-0003.pdf")
    assert "of 56" in read_excel(tmp_path, "legacy/customers_export.xlsx").splitlines()[1]  # header + 55 rows


# --- Trajectory checks: what the agent did, not what it said ---------------


def pdf(n):
    return ToolCall("read_pdf", f'{{"path": "invoices/INV-2026-000{n}.pdf"}}', "")


def test_called_matches_name_and_arguments():
    assert called("read_pdf", "0003")([pdf(3)])
    assert not called("read_pdf", "0003")([pdf(2)])
    assert called("run_sql")([ToolCall("run_sql", "{}", "")]) and not called("run_sql")([])


def test_every_invoice_means_all_five_pdfs_or_a_search():
    assert looked_at_every_invoice([pdf(n) for n in range(1, 6)])
    assert not looked_at_every_invoice([pdf(1), pdf(2)])  # the step 5 fake
    assert looked_at_every_invoice([ToolCall("search_files", '{"query": "Total", "path": "invoices"}', "")])


def test_paging_means_read_excel_at_least_twice():
    one = ToolCall("read_excel", "{}", "")
    assert paged_through_excel([one, one]) and not paged_through_excel([one])


def test_every_task_has_a_trajectory_check():
    assert all(t.trajectory for t in TASKS)


def test_row_count_needs_one_read_excel_because_the_note_gives_the_total():
    # read_excel's first page says "[rows 1-30 of 56 ...]". Answering 56 from that is right, not skipped work.
    assert task_by_id("excel-row-count").trajectory([ToolCall("read_excel", "{}", "")])
    assert not task_by_id("excel-row-count").trajectory([ToolCall("run_sql", "{}", "")])
