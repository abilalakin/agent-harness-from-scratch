"""A model as judge: grading free-text answers against a rubric.

Some answers have no single right string. A contract summary can be right in many
wordings, so a checker like contains() is too weak. Instead a second model call reads
the question, the answer and a rubric, and returns pass or fail with a reason.

A judge is a model too, with a model's biases: long answers look thorough, confident
answers look right, its own style looks good. So the judge is checked against a few
answers graded by hand before it is trusted (JUDGE_CHECKS, check_judge).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from harness.evals.runner import RunResult
from harness.evals.tasks import Task, task_by_id
from harness.model import ChatModel

JUDGE_PROMPT = (
    "You grade an answer against a rubric. Reply with JSON only: "
    '{"pass": true or false, "reason": "one sentence"}. Pass only if every rubric point is met.'
)

_JSON_BLOCKS = re.compile(r"\{[^{}]*\}")  # every brace pair without nesting; the verdict is one of them


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


def judge_answer(model: ChatModel, question: str, answer: str, rubric: str) -> Verdict:
    """One model call, no tools. The first {...} that parses and has a "pass" key is the verdict; none means fail."""
    content = f"Question:\n{question}\n\nRubric:\n{rubric}\n\nAnswer to grade:\n{answer}"
    reply = model.complete([{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": content}])
    for block in _JSON_BLOCKS.findall(reply.get("content") or ""):
        try:
            verdict = json.loads(block)
        except ValueError:
            continue  # prose in braces, not the verdict
        if isinstance(verdict, dict) and "pass" in verdict:
            # Compared as text: bool("false") would be True, and models do quote their booleans.
            return Verdict(str(verdict["pass"]).lower() == "true", str(verdict.get("reason", "")))
    return Verdict(False, "judge gave no JSON")


def judge_result(model: ChatModel, result: RunResult, task: Task) -> None:
    """If the task has a rubric, the judge's verdict replaces the checker's. Called right after each run."""
    if not task.rubric or result.error is not None:
        return
    try:
        verdict = judge_answer(model, task.question, result.answer, task.rubric)
    except Exception as e:  # one lost verdict, not a lost run
        result.passed, result.error = False, f"judge: {type(e).__name__}: {e}"
        return
    result.passed = verdict.passed
    result.judge_reason = verdict.reason


# --- Checking the judge ------------------------------------------------------
#
# Six answers to the contract-summary question, graded by hand. Each pair tests one
# bias: does length, confidence or self-praise move the judge where it should not?

_GOOD = "- Payment is net 30 days from the invoice date.\n- Late payments cost 1.5% per month.\n- German law applies."
_FILLER = " This is an important point that both parties should keep in mind. It applies to every order."
JUDGE_CHECKS: list[tuple[str, bool, str]] = [
    (_GOOD, True, "The plain correct answer."),
    (_GOOD.replace("\n", _FILLER + "\n") + _FILLER, True, "Padded. Length should not matter."),
    ("- Payment is net 30 days from the invoice date.\n- Delivery within 10 working days.\n- German law applies.",
     False, "The 1.5% penalty is missing."),
    (_GOOD + "\n- A 5% discount applies to payment within 10 days, as clearly stated in section 4.",
     False, "A made-up clause, written confidently."),
    ("Net 30, 1.5%/month late fee, German law.", True, "Terse but complete."),
    (_GOOD + "\n\nI checked every page carefully.", True, "Self-praise is not a rubric point either way."),
]


def check_judge(model: ChatModel, log: Callable[[str], None] = print) -> int:
    """Judge the hand-graded answers and print a table. Returns how often the judge disagreed with the hand grade."""
    task = task_by_id("contract-summary")
    log("| # | hand grade | judge | reason |")
    log("|---|---|---|---|")
    disagreements = 0
    for n, (answer, expected, why) in enumerate(JUDGE_CHECKS, 1):
        verdict = judge_answer(model, task.question, answer, task.rubric or "")
        agrees = verdict.passed == expected
        disagreements += not agrees
        mark = "" if agrees else " (disagrees)"
        log(f"| {n} | {'pass' if expected else 'fail'}: {why} | {'pass' if verdict.passed else 'fail'}{mark} | {verdict.reason} |")
    return disagreements
