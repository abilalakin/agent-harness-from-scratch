"""Turn run results into a markdown report, and results into JSON and back."""

import json
from dataclasses import asdict
from pathlib import Path
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


def _passed(results: list[RunResult]) -> str:
    return f"{sum(r.passed for r in results)} of {len(results)}"


def _trajectory(results: list[RunResult]) -> str:
    """'3 of 5' over the runs that had a trajectory check, or '-' when none had one."""
    checked = [r for r in results if r.trajectory_ok is not None]
    return f"{sum(r.trajectory_ok for r in checked)} of {len(checked)}" if checked else "-"


def write_report(results: list[RunResult], tasks: list[Task], meta: dict[str, str]) -> str:
    lines = [f"# Evals: {meta.get('label', 'run')}", ""]
    lines += [f"- {key}: {value}" for key, value in meta.items()]
    lines += ["", "| task | passed | trajectory | tool calls | tokens | seconds |", "|---|---|---|---|---|---|"]

    for task in tasks:
        runs = [r for r in results if r.task_id == task.id]
        passed = _passed(runs)
        if errors := sum(r.error is not None for r in runs):
            passed += f" ({errors} error{'s' if errors > 1 else ''})"  # a crash is not a wrong answer
        lines.append(
            f"| {task.id} | {passed} | {_trajectory(runs)} | {_mean([len(r.calls) for r in runs])} "
            f"| {_mean([r.tokens for r in runs])} | {_mean([r.seconds for r in runs])} |"
        )
    total = f"**Total: {_passed(results)} runs passed"
    if errors := sum(r.error is not None for r in results):
        total += f", {errors} errored"
    if _trajectory(results) != "-":
        total += f", trajectory ok in {_trajectory(results)}"
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
            shown = (failed.error or failed.answer or "(no answer)")[:QUOTE_CHARS]
            if failed.judge_reason:
                shown += f"\njudge: {failed.judge_reason}"
            quoted = "\n".join(f"> {line}" for line in shown.splitlines())  # every line, or a list breaks out
            failures.append(f"**{task.id}** (run {failed.run}):\n{quoted}\n")
    if failures:
        lines += ["", "## Failures", ""] + failures
    return "\n".join(lines) + "\n"


def read_raw(path: Path) -> tuple[dict[str, str], list[RunResult]]:
    """A raw log back into meta and results."""
    first, *rest = path.read_text().splitlines()
    return json.loads(first)["meta"], [from_json(json.loads(line)) for line in rest]


def compare(raw_paths: list[Path]) -> str:
    """Several runs side by side, one row each. Vary one thing per run, and this table shows what it did."""
    lines = [
        "| label | model | prompt | context window | commit | passed | trajectory ok | tool calls | tokens | seconds |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for path in raw_paths:
        meta, results = read_raw(path)
        lines.append(
            f"| {meta.get('label', path.stem)} | {meta.get('model', '?')} | {meta.get('prompt', '?')} "
            f"| {meta.get('context_window', '?')} | {meta.get('commit', '?')} "
            f"| {_passed(results)} | {_trajectory(results)} "
            f"| {_mean([len(r.calls) for r in results])} | {_mean([r.tokens for r in results])} "
            f"| {_mean([r.seconds for r in results])} |"
        )
    return "\n".join(lines) + "\n"
