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


@dataclass(frozen=True)
class ToolCall:
    """One tool call the agent made: what it asked for and what came back."""

    name: str
    arguments: str
    result: str


TrajectoryCheck = Callable[[list[ToolCall]], bool]

# Numbers the way people write them: "13,701.44", "1990", "-5". The comma is stripped before float().
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def contains(*needles: str) -> Check:
    """Every needle appears in the answer. Case does not matter."""
    return lambda answer: all(needle.lower() in answer.lower() for needle in needles)


def number(expected: float, tolerance: float = 0) -> Check:
    """Some number in the answer equals expected, or is within tolerance of it."""

    def check(answer: str) -> bool:
        numbers = (float(m.replace(",", "")) for m in _NUMBER.findall(answer))
        return any(abs(n - expected) <= tolerance for n in numbers)

    return check


def all_of(*checks: Check) -> Check:
    return lambda answer: all(check(answer) for check in checks)


# --- Trajectory checks ----------------------------------------------------
#
# A right answer reached by skipping the work is a failure. These look at the
# tool calls, not the answer text.


def called(name: str, *needles: str) -> TrajectoryCheck:
    """Some call to `name` has every needle in its arguments. No needles: any call to `name`."""
    return lambda calls: any(
        c.name == name and all(n.lower() in c.arguments.lower() for n in needles) for c in calls
    )


def any_of(*checks: TrajectoryCheck) -> TrajectoryCheck:
    return lambda calls: any(check(calls) for check in checks)


def looked_at_every_invoice(calls: list[ToolCall]) -> bool:
    """read_pdf on each of the five invoices, or one search over them. Either is honest work.
    Reading two PDFs and guessing the rest (the step 5 run) is not."""
    read_each = all(called("read_pdf", f"INV-2026-000{n}")(calls) for n in range(1, 6))
    searched = called("search_files", "invoices")(calls) or called("search_files", "total")(calls)
    scripted = called("run_python", "invoices")(calls)  # step 7: a script over the PDFs
    return read_each or searched or scripted


def paged_through_excel(calls: list[ToolCall]) -> bool:
    """read_excel at least twice: the sheet has two pages, so one call cannot have seen it all."""
    return sum(c.name == "read_excel" for c in calls) >= 2


_read_contract = any_of(called("read_pdf", "supply-agreement"), called("search_files"))
_scripted = called("run_python")  # step 7: a script is honest work for any table question


@dataclass(frozen=True)
class Task:
    id: str
    question: str
    check: Check
    trajectory: TrajectoryCheck | None = None
    rubric: str | None = None  # when set, a model judge grades the answer instead of `check` (6c)


TASKS = [
    # Counting in the database. Step 3 answered "50" here, from a cut result.
    Task("invoice-count", "How many invoices are in the ERP database?", number(112), called("run_sql")),
    Task("unpaid-count", "How many invoices in the ERP database are unpaid?", number(33), called("run_sql")),
    # Needs a JOIN and GROUP BY, not just a count.
    Task(
        "top-customer",
        "Which customer has the most orders in the ERP database?",
        contains("Meridian Trading"),
        called("run_sql"),
    ),
    Task(
        "priciest-product",
        "Which product has the highest unit price, and what is it?",
        all_of(contains("Cable harness"), number(1990.35, tolerance=1)),
        called("run_sql"),
    ),
    Task(
        "german-customers",
        "How many customers in the ERP database are in Germany (country DE)?",
        number(15),
        called("run_sql"),
    ),
    # Reading a PDF. The PDF of invoice 3 is 100 EUR higher than the database on purpose.
    Task(
        "invoice-3-pdf-total",
        "What is the total on the PDF of invoice INV-2026-0003?",
        number(13701.44, tolerance=1),
        any_of(called("read_pdf", "0003"), called("search_files")),
    ),
    # The step 5 case: the model read two PDFs and claimed it had checked five.
    Task(
        "invoice-mismatch",
        "Does every invoice PDF in the invoices folder match the total in the ERP database? Name any that doesn't.",
        contains("INV-2026-0003"),
        looked_at_every_invoice,
    ),
    # The step 5 search failure: "late payment penalty" found nothing, the PDF says "Late payments carry a penalty".
    Task(
        "contract-penalty",
        "What penalty does the supply agreement set for late payments?",
        number(1.5),
        _read_contract,
    ),
    Task(
        "contract-notice",
        "How many days notice does the supply agreement need to end it?",
        number(90),
        _read_contract,
    ),
    # Excel paging: the answer needs both pages of the sheet.
    Task(
        "excel-empty-rows",
        "How many rows in the legacy customer export have an empty name?",
        number(2),
        any_of(_scripted, paged_through_excel),
    ),
    Task(
        "excel-row-count",
        "How many rows, including the header, does the Customers sheet of the legacy customer export have?",
        number(56),
        any_of(_scripted, called("read_excel")),  # the first page's note already says "of 56"
    ),
    # Needs every row compared with every other: a script, or a very patient reader.
    Task(
        "excel-duplicates",
        "Ignoring empty rows, how many rows in the legacy customer export are exact duplicates of an earlier row?",
        number(3),
        any_of(_scripted, paged_through_excel),
    ),
    # Free text. This check is weak on purpose; a model judge takes over in 6c.
    Task(
        "contract-summary",
        "Summarize the supply agreement's payment terms, late payment penalty and governing law in three short bullet points.",
        contains("Germany"),
        called("read_pdf", "supply-agreement"),
        rubric=(
            "Mentions all three: net 30 day payment terms, the 1.5% per month late penalty, and German law. "
            "Three bullet points or fewer. No clause that is not in the agreement."
        ),
    ),
]


def task_by_id(id: str) -> Task:
    for task in TASKS:
        if task.id == id:
            return task
    raise KeyError(f"no task '{id}'. Known tasks: {', '.join(t.id for t in TASKS)}")
