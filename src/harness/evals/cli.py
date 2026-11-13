"""The command: `uv run evals`. Builds the agent, runs the tasks, saves the raw results and the report."""

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

from harness.agent import SYSTEM_PROMPT, Agent
from harness.config import Settings, load_settings
from harness.evals.report import to_json, write_report
from harness.evals.runner import RunResult, run_all
from harness.evals.tasks import TASKS, task_by_id
from harness.file_tools import make_file_tools
from harness.model import OpenAIChatModel
from harness.sql_tools import make_sql_tools
from harness.tools import BUILTIN_TOOLS

def build_agent(settings: Settings, system_prompt: str = SYSTEM_PROMPT) -> Agent:
    """The same agent the CLI builds, minus the MCP option: built-in SQL tools only."""
    tools = [*BUILTIN_TOOLS, *make_file_tools(settings.data_dir), *make_sql_tools(settings.data_dir / "erp.db")]
    model = OpenAIChatModel(settings)
    return Agent(model, system_prompt, tools, max_steps=settings.max_steps, context_window=settings.context_window)


def save_raw(path: Path, results: list[RunResult], meta: dict[str, str]) -> None:
    """JSON lines: the meta first, then one line per run. Enough to rebuild any report later."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(json.dumps({"meta": meta}) + "\n")
        for result in results:
            f.write(json.dumps(to_json(result)) + "\n")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="evals", description="Run the eval tasks and write a report.")
    parser.add_argument("--runs", type=int, default=5, help="runs per task (default 5)")
    parser.add_argument("--label", help="name for this run (default: the model name)")
    parser.add_argument("--task", action="append", help="only this task id; repeat for several")
    parser.add_argument("--system-prompt", type=Path, help="a file with a system prompt to use instead of the default")
    args = parser.parse_args(argv)

    try:
        tasks = [task_by_id(id) for id in args.task] if args.task else TASKS
    except KeyError as e:
        parser.error(str(e))

    settings = load_settings()
    system_prompt = args.system_prompt.read_text() if args.system_prompt else SYSTEM_PROMPT
    label = args.label or settings.model.replace(":", "-")
    meta = {
        "date": date.today().isoformat(),
        "label": label,
        "model": settings.model,
        "prompt": args.system_prompt.stem if args.system_prompt else "default",
        "context_window": str(settings.context_window),
        "runs": str(args.runs),
        "commit": _git_commit() or "unknown",
    }

    results = run_all(tasks, lambda: build_agent(settings, system_prompt), runs=args.runs)

    stem = f"{meta['date']}-{label}"
    save_raw(Path("logs/evals") / f"{stem}.jsonl", results, meta)
    report_path = Path("docs/evals") / f"{stem}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(write_report(results, tasks, meta))
    print(f"report: {report_path}")
