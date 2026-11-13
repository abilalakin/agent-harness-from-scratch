"""Turn run results into a markdown report, and results into JSON and back."""

from dataclasses import asdict
from statistics import mean

from harness.evals.runner import RunResult
from harness.evals.tasks import Task, ToolCall

QUOTE_CHARS = 300  # how much of a failed answer the report shows


def to_json(result: RunResult) -> dict:
    return asdict(result)


def from_json(d: dict) -> RunResult:
    return RunResult(**{**d, "calls": [ToolCall(**c) for c in d["calls"]]})


def _mean(values: list[float]) -> str:
    """A whole number, or '-' when there is nothing to average."""
    return f"{mean(values):.0f}" if values else "-"


def write_report(results: list[RunResult], tasks: list[Task], meta: dict[str, str]) -> str:
    lines = [f"# Evals: {meta.get('label', 'run')}", ""]
    lines += [f"- {key}: {value}" for key, value in meta.items()]
    lines += ["", "| task | passed | trajectory | tool calls | tokens | seconds |", "|---|---|---|---|---|---|"]

    for task in tasks:
        runs = [r for r in results if r.task_id == task.id]
        passed = sum(r.passed for r in runs)
        checked = [r for r in runs if r.trajectory_ok is not None]
        trajectory = f"{sum(r.trajectory_ok for r in checked)} of {len(checked)}" if checked else "-"
        lines.append(
            f"| {task.id} | {passed} of {len(runs)} | {trajectory} | {_mean([len(r.calls) for r in runs])} "
            f"| {_mean([r.tokens for r in runs])} | {_mean([r.seconds for r in runs])} |"
        )
    total = f"**Total: {sum(r.passed for r in results)} of {len(results)} runs passed"
    checked = [r for r in results if r.trajectory_ok is not None]
    if checked:
        total += f", trajectory ok in {sum(r.trajectory_ok for r in checked)} of {len(checked)}"
    lines += ["", total + "**"]

    # The interesting failures: the answer was right, but the work was skipped.
    skipped = [r for r in results if r.passed and r.trajectory_ok is False]
    if skipped:
        lines += ["", "## Right answer, skipped work", ""]
        lines += [f"- {r.task_id} run {r.run}, calls: {', '.join(c.name for c in r.calls) or '(none)'}" for r in skipped]

    # One failed answer per task, so the report says what "failed" looked like without opening the raw log.
    failures = []
    for task in tasks:
        failed = next((r for r in results if r.task_id == task.id and not r.passed), None)
        if failed:
            shown = failed.error or failed.answer or "(no answer)"
            judge = f"\n> judge: {failed.judge_reason}" if failed.judge_reason else ""
            failures.append(f"**{task.id}** (run {failed.run}):\n> {shown[:QUOTE_CHARS]}{judge}\n")
    if failures:
        lines += ["", "## Failures", ""] + failures
    return "\n".join(lines) + "\n"
