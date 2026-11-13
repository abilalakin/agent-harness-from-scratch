import pytest
from fakes import FakeModel, tool_reply
from harness.agent import Agent
from harness.evals.runner import TokenCounter, run_all, run_task
from harness.evals.tasks import Task, contains
from harness.tools import BUILTIN_TOOLS, Tool

TASK = Task(id="t", question="what is 2+2?", check=contains("4"))


def make_agent(replies):
    return lambda: Agent(FakeModel(list(replies)), tools=BUILTIN_TOOLS, max_steps=3)


def test_a_run_records_answer_calls_tokens_and_pass():
    replies = [tool_reply("calculate", '{"a": 2, "op": "+", "b": 2}'), {"role": "assistant", "content": "It is 4"}]
    result = run_task(TASK, make_agent(replies))
    assert result.passed and result.answer == "It is 4" and result.error is None
    assert [c.name for c in result.calls] == ["calculate"] and result.calls[0].result == "4.0"
    assert result.model_calls == 2 and result.tokens > 0 and result.seconds >= 0


def test_a_wrong_answer_fails():
    assert not run_task(TASK, make_agent([{"role": "assistant", "content": "five"}])).passed


def test_a_model_error_is_recorded_and_fails():
    result = run_task(TASK, make_agent([RuntimeError("boom")]))
    assert not result.passed and result.error == "RuntimeError: boom" and result.answer == ""


def test_running_out_of_steps_fails_without_crashing():
    replies = [tool_reply("calculate", '{"a": 2, "op": "+", "b": 2}', id=f"c{i}") for i in range(3)]
    result = run_task(TASK, make_agent(replies))
    assert not result.passed and "Stopped after 3" in result.answer


def test_ctrl_c_is_not_swallowed():
    with pytest.raises(KeyboardInterrupt):
        run_task(TASK, make_agent([KeyboardInterrupt()]))


def test_stored_tool_results_are_cut_to_500_characters():
    big = Tool("big", "", {"type": "object", "properties": {}}, lambda: "z" * 4000)
    agent = lambda: Agent(FakeModel([tool_reply("big", "{}"), {"role": "assistant", "content": "4"}]), tools=[big])
    assert len(run_task(TASK, agent).calls[0].result) == 500


def test_run_all_makes_a_fresh_agent_for_every_run():
    made = []

    def make():
        agent = Agent(FakeModel([{"role": "assistant", "content": "4"}]))
        made.append(agent)
        return agent

    results = run_all([TASK], make, runs=3, log=lambda s: None)
    assert len(made) == 3 and [r.run for r in results] == [1, 2, 3]
    assert all(len(a.messages) == 3 for a in made)  # system, user, assistant: nothing leaked between runs


def test_token_counter_adds_up_every_call():
    counter = TokenCounter(FakeModel([{"role": "assistant", "content": "a"}, {"role": "assistant", "content": "b"}]))
    counter.complete([{"role": "user", "content": "x" * 400}])
    counter.complete([{"role": "user", "content": "x" * 400}])
    assert counter.calls == 2 and 200 <= counter.tokens <= 230
