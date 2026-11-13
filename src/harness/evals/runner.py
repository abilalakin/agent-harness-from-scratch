"""Run eval tasks through the real agent and score each run.

The harness is measured from the outside. Tool calls come through the agent's
on_tool_call hook, and tokens are counted by wrapping the model, so the agent
never knows it is being watched. Every run gets a fresh agent: a fresh history,
nothing carried over from the run before.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from harness.agent import Agent
from harness.context import estimate_tokens
from harness.evals.tasks import Task
from harness.model import ChatModel, Message

STORED_RESULT_CHARS = 500  # tool results in the log are cut: enough to see what came back, not the whole thing


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str
    result: str


@dataclass
class RunResult:
    task_id: str
    run: int  # 1-based
    answer: str
    calls: list[ToolCall]
    passed: bool
    trajectory_ok: bool | None  # None: the task has no trajectory check
    tokens: int  # estimated request size, summed over every model call
    model_calls: int
    seconds: float
    error: str | None  # the exception, or None


class TokenCounter:
    """A ChatModel that passes calls through and counts them. Wrapping is how you measure without touching the agent."""

    def __init__(self, model: ChatModel):
        self.model = model
        self.tokens = 0
        self.calls = 0

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        self.tokens += estimate_tokens(messages, tools)
        self.calls += 1
        return self.model.complete(messages, tools)


def run_task(task: Task, make_agent: Callable[[], Agent], run: int = 1) -> RunResult:
    """One run of one task on a fresh agent. An exception becomes a failed run, not a crash (Ctrl+C still stops)."""
    agent = make_agent()
    counter = TokenCounter(agent.model)
    agent.model = counter
    calls: list[ToolCall] = []
    agent.on_tool_call = lambda name, arguments, result: calls.append(
        ToolCall(name, arguments, result[:STORED_RESULT_CHARS])
    )

    answer, error = "", None
    start = time.perf_counter()
    try:
        answer = agent.ask(task.question)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    seconds = time.perf_counter() - start

    return RunResult(
        task_id=task.id,
        run=run,
        answer=answer,
        calls=calls,
        passed=error is None and task.check(answer),
        trajectory_ok=None,
        tokens=counter.tokens,
        model_calls=counter.calls,
        seconds=seconds,
        error=error,
    )


def run_all(
    tasks: list[Task], make_agent: Callable[[], Agent], runs: int = 5, log: Callable[[str], None] = print
) -> list[RunResult]:
    """Every task, `runs` times each, one after the other. One log line per run so you can watch progress."""
    results = []
    for task in tasks:
        for run in range(1, runs + 1):
            result = run_task(task, make_agent, run)
            results.append(result)
            status = "pass" if result.passed else "FAIL"
            log(f"{task.id} run {run}: {status} ({result.seconds:.0f}s, {len(result.calls)} tool calls)")
    return results
