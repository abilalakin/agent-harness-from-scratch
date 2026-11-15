"""The command: `uv run evals`. Builds the agent, runs the tasks, saves the raw results and the report."""

import argparse
import json
import subprocess
from datetime import date
from functools import partial
from pathlib import Path

from harness.agent import SYSTEM_PROMPT
from harness.cli import build_agent
from harness.config import load_settings
from harness.evals.judge import check_judge, judge_result
from harness.evals.report import compare, to_json, write_report
from harness.evals.runner import RunResult, run_all
from harness.evals.tasks import TASKS, task_by_id
from harness.model import OpenAIChatModel

class RawLog:
    """JSON lines on disk: the meta first, then one line per run, written the moment the run ends."""

    def __init__(self, path: Path, meta: dict[str, str]):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("x")  # create only: an existing run is never overwritten
        self._write({"meta": meta})

    def add(self, result: RunResult) -> None:
        self._write(to_json(result))

    def _write(self, record: dict) -> None:
        self.file.write(json.dumps(record) + "\n")
        self.file.flush()  # so a killed run keeps every finished result


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout
    except OSError:
        out = ""
    return out.strip() or "unknown"  # no git, or not a repo


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="evals", description="Run the eval tasks and write a report.")
    parser.add_argument("--runs", type=int, default=5, help="runs per task (default 5)")
    parser.add_argument("--label", help="name for this run (default: the model name)")
    parser.add_argument("--task", action="append", help="only this task id; repeat for several")
    parser.add_argument("--system-prompt", type=Path, help="a file with a system prompt to use instead of the default")
    parser.add_argument("--judge", action="store_true", help="let a model judge grade the tasks that have a rubric")
    parser.add_argument("--check-judge", action="store_true", help="grade the hand-graded answers and stop")
    parser.add_argument("--compare", nargs="+", type=Path, metavar="JSONL", help="print one table over these raw logs and stop")
    args = parser.parse_args(argv)

    if args.compare:
        print(compare(args.compare), end="")
        return
    settings = load_settings()
    if args.check_judge:
        disagreements = check_judge(OpenAIChatModel(settings))
        print(f"\nThe judge disagreed with the hand grade {disagreements} time(s).")
        return

    try:
        tasks = [task_by_id(id) for id in args.task] if args.task else TASKS
    except KeyError as e:
        parser.error(e.args[0])  # str(KeyError) would wrap the message in quotes

    system_prompt = args.system_prompt.read_text() if args.system_prompt else SYSTEM_PROMPT
    label = args.label or settings.model.replace(":", "-")
    meta = {
        "date": date.today().isoformat(),
        "label": label,
        "model": settings.model,
        "prompt": args.system_prompt.stem if args.system_prompt else "default",
        "context_window": str(settings.context_window),
        "runs": str(args.runs),
        "judge": "yes" if args.judge else "no",
        "commit": _git_commit(),
    }

    stem = f"{meta['date']}-{label}"
    try:
        raw = RawLog(Path("logs/evals") / f"{stem}.jsonl", meta)
    except FileExistsError as e:
        parser.error(f"{e.filename} already exists. Pick another --label, or delete it.")
    judge = OpenAIChatModel(settings) if args.judge else None

    def finish(result: RunResult, task) -> None:
        if judge:
            judge_result(judge, result, task)  # before the log line, so the log carries the judge's verdict
        raw.add(result)

    results = run_all(
        tasks,
        lambda: build_agent(settings, system_prompt),
        runs=args.runs,
        log=partial(print, flush=True),  # flush: when the output goes to a file, tail -f should still show progress
        on_result=finish,
    )
    raw.file.close()

    report_path = Path("docs/evals") / f"{stem}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(write_report(results, tasks, meta))
    print(f"report: {report_path}")
