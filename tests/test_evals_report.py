import json

from harness.evals.report import from_json, to_json, write_report
from harness.evals.runner import RunResult
from harness.evals.tasks import ToolCall
from harness.evals.tasks import Task, contains

T = Task(id="t", question="q", check=contains("4"))
META = {"model": "qwen3:8b", "runs": "5"}


def result(run, passed, answer="4", error=None, calls=1, tokens=1000, seconds=10.0):
    return RunResult("t", run, answer, [ToolCall("x", "{}", "r")] * calls, passed, None, tokens, 2, seconds, error)


def test_report_shows_counts_and_means():
    results = [result(i, passed=i < 5, answer="4" if i < 5 else "five") for i in range(1, 6)]
    text = write_report(results, [T], META)
    assert "| t | 4 of 5 | - | 1 | 1000 | 10 |" in text
    assert "**Total: 4 of 5 runs passed**" in text
    assert "model: qwen3:8b" in text


def test_report_quotes_the_first_failure():
    results = [result(1, False, answer="five"), result(2, False, error="RuntimeError: boom", answer="")]
    text = write_report(results, [T], META)
    assert "## Failures" in text and "> five" in text and "boom" not in text  # only the first failure per task


def test_report_with_no_runs_for_a_task_shows_dashes():
    assert "| t | 0 of 0 | - | - | - | - |" in write_report([], [T], META)


def test_results_survive_json():
    r = result(1, True)
    assert from_json(json.loads(json.dumps(to_json(r)))) == r


def test_report_separates_right_answers_reached_by_skipping_work():
    r = result(1, True)
    r.trajectory_ok = False
    text = write_report([r], [T], META)
    assert "| t | 1 of 1 | 0 of 1 |" in text and "## Right answer, skipped work" in text and "- t run 1, calls: x" in text
