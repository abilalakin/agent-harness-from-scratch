"""The eval task set: questions over the practice data with known answers.

A task is a question, a checker for the answer, and (later) a checker for what the
agent did to get it. The expected values come from the seed-42 practice data, and
tests/test_evals_tasks.py pins them to the generator.

Checkers are small functions from answer text to pass/fail, so the table at the
bottom reads like data: anyone can see the questions and expected answers at a glance.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

Check = Callable[[str], bool]

# Numbers the way people write them: "13,701.44", "1990", "-5". The comma is stripped before float().
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def contains(*needles: str) -> Check:
    """Every needle appears in the answer. Case does not matter."""
    return lambda answer: all(needle.lower() in answer.lower() for needle in needles)


def number_near(expected: float, tolerance: float = 1.0) -> Check:
    """Some number in the answer is within tolerance of expected."""

    def check(answer: str) -> bool:
        numbers = (float(m.replace(",", "")) for m in _NUMBER.findall(answer))
        return any(abs(n - expected) <= tolerance for n in numbers)

    return check


def all_of(*checks: Check) -> Check:
    return lambda answer: all(check(answer) for check in checks)


@dataclass(frozen=True)
class Task:
    id: str
    question: str
    check: Check


TASKS = [
    # Counting in the database. Step 3 answered "50" here, from a cut result.
    Task("invoice-count", "How many invoices are in the ERP database?", contains("112")),
    Task("unpaid-count", "How many invoices in the ERP database are unpaid?", contains("33")),
    # Needs a JOIN and GROUP BY, not just a count.
    Task("top-customer", "Which customer has the most orders in the ERP database?", contains("Meridian Trading")),
    Task(
        "priciest-product",
        "Which product has the highest unit price, and what is it?",
        all_of(contains("Cable harness"), number_near(1990.35)),
    ),
    Task("german-customers", "How many customers in the ERP database are in Germany (country DE)?", contains("15")),
    # Reading a PDF. The PDF of invoice 3 is 100 EUR higher than the database on purpose.
    Task("invoice-3-pdf-total", "What is the total on the PDF of invoice INV-2026-0003?", number_near(13701.44)),
    # The step 5 case: the model read two PDFs and claimed it had checked five.
    Task(
        "invoice-mismatch",
        "Does every invoice PDF in the invoices folder match the total in the ERP database? Name any that doesn't.",
        contains("INV-2026-0003"),
    ),
    # The step 5 search failure: "late payment penalty" found nothing, the PDF says "Late payments carry a penalty".
    Task("contract-penalty", "What penalty does the supply agreement set for late payments?", contains("1.5")),
    Task("contract-notice", "How many days notice does the supply agreement need to end it?", contains("90")),
    # Excel paging: the answer needs both pages of the sheet.
    Task(
        "excel-empty-rows",
        "How many rows in the legacy customer export have an empty name?",
        number_near(2, tolerance=0),
    ),
    Task(
        "excel-row-count",
        "How many rows, including the header, does the Customers sheet of the legacy customer export have?",
        contains("56"),
    ),
    # Free text. This check is weak on purpose; a model judge takes over in 6c.
    Task("contract-summary", "Summarize the supply agreement in three short bullet points.", contains("Germany")),
]


def task_by_id(id: str) -> Task:
    for task in TASKS:
        if task.id == id:
            return task
    raise KeyError(f"no task '{id}'. Known tasks: {', '.join(t.id for t in TASKS)}")
