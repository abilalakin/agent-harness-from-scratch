"""Turn run results into a markdown report, and results into JSON and back."""

from dataclasses import asdict
from statistics import mean

from harness.evals.runner import RunResult, ToolCall
from harness.evals.tasks import Task

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
    lines += ["", "| task | passed | tool calls | tokens | seconds |", "|---|---|---|---|---|"]

    for task in tasks:
        runs = [r for r in results if r.task_id == task.id]
        passed = sum(r.passed for r in runs)
        lines.append(
            f"| {task.id} | {passed} of {len(runs)} | {_mean([len(r.calls) for r in runs])} "
            f"| {_mean([r.tokens for r in runs])} | {_mean([r.seconds for r in runs])} |"
        )
    lines += ["", f"**Total: {sum(r.passed for r in results)} of {len(results)} runs passed**"]

    # One failed answer per task, so the report says what "failed" looked like without opening the raw log.
    failures = []
    for task in tasks:
        failed = next((r for r in results if r.task_id == task.id and not r.passed), None)
        if failed:
            shown = failed.error or failed.answer or "(no answer)"
            failures.append(f"**{task.id}** (run {failed.run}):\n> {shown[:QUOTE_CHARS]}\n")
    if failures:
        lines += ["", "## Failures", ""] + failures
    return "\n".join(lines) + "\n"
