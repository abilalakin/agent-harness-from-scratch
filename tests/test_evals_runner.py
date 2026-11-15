import pytest
from fakes import BIG, FakeModel, tool_reply
from harness.agent import Agent
from harness.evals.cli import main
from harness.evals.runner import TokenCounter, run_all, run_task
from harness.evals.tasks import Task, contains
from harness.tools import BUILTIN_TOOLS

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
    agent = lambda: Agent(FakeModel([tool_reply("big", "{}"), {"role": "assistant", "content": "4"}]), tools=[BIG])
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


def test_main_refuses_an_unknown_task_id(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--task", "typo"])
    assert e.value.code == 2 and "invoice-count" in capsys.readouterr().err


def test_main_writes_raw_log_and_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = lambda settings, system_prompt: Agent(FakeModel([{"role": "assistant", "content": "112"}]), max_steps=2)
    monkeypatch.setattr("harness.evals.cli.build_agent", fake)
    main(["--runs", "1", "--task", "invoice-count", "--label", "test"])
    report = next((tmp_path / "docs" / "evals").glob("*-test.md")).read_text()
    raw = next((tmp_path / "logs" / "evals").glob("*-test.jsonl")).read_text().splitlines()
    assert "| invoice-count | 1 of 1 |" in report and '"meta"' in raw[0] and len(raw) == 2


def test_run_all_hands_each_result_over_as_soon_as_it_is_done():
    seen = []
    run_all([TASK], make_agent([{"role": "assistant", "content": "4"}]), runs=2, log=lambda s: None, on_result=lambda r, t: seen.append((r.run, t.id)))
    assert seen == [(1, "t"), (2, "t")]


def test_main_saves_each_run_before_the_next_starts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lines_when_second_run_started = []

    def fake(settings, system_prompt):
        raw = list((tmp_path / "logs" / "evals").glob("*.jsonl"))
        lines_when_second_run_started.append(len(raw[0].read_text().splitlines()) if raw else 0)
        return Agent(FakeModel([{"role": "assistant", "content": "112"}]), max_steps=2)

    monkeypatch.setattr("harness.evals.cli.build_agent", fake)
    main(["--runs", "2", "--task", "invoice-count", "--label", "test"])
    assert lines_when_second_run_started == [1, 2]  # meta line only, then meta + run 1


def test_main_judge_flag_lets_the_judge_override_the_checker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = lambda settings, system_prompt: Agent(FakeModel([{"role": "assistant", "content": "Germany"}]), max_steps=2)
    judge = lambda settings: FakeModel([{"role": "assistant", "content": '{"pass": false, "reason": "no penalty"}'}])
    monkeypatch.setattr("harness.evals.cli.build_agent", agent)
    monkeypatch.setattr("harness.evals.cli.OpenAIChatModel", judge)
    main(["--runs", "1", "--task", "contract-summary", "--judge", "--label", "test"])
    report = next((tmp_path / "docs" / "evals").glob("*-test.md")).read_text()
    assert "| contract-summary | 0 of 1 |" in report and "no penalty" in report and "- judge: yes" in report
    raw = next((tmp_path / "logs" / "evals").glob("*-test.jsonl")).read_text().splitlines()
    assert '"judge_reason": "no penalty"' in raw[1] and '"passed": false' in raw[1]  # the log carries the verdict too


def test_main_check_judge_runs_no_tasks(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("harness.evals.cli.build_agent", lambda *a: pytest.fail("a task was run"))
    judge = lambda settings: FakeModel([{"role": "assistant", "content": '{"pass": true, "reason": "ok"}'}] * 6)
    monkeypatch.setattr("harness.evals.cli.OpenAIChatModel", judge)
    main(["--check-judge"])
    out = capsys.readouterr().out
    assert "| hand grade | judge |" in out and "disagree" in out and not (tmp_path / "docs").exists()


def test_progress_line_says_error_not_fail_for_a_crashed_run():
    lines = []
    run_all([TASK], make_agent([RuntimeError("boom")]), runs=1, log=lines.append)
    assert lines == ["t run 1: ERROR RuntimeError: boom (0s, 0 tool calls)"]


def test_main_refuses_to_overwrite_an_existing_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake = lambda settings, system_prompt: Agent(FakeModel([{"role": "assistant", "content": "112"}]), max_steps=2)
    monkeypatch.setattr("harness.evals.cli.build_agent", fake)
    main(["--runs", "1", "--task", "invoice-count", "--label", "test"])
    with pytest.raises(SystemExit) as e:
        main(["--runs", "1", "--task", "invoice-count", "--label", "test"])
    assert e.value.code == 2 and "already exists" in capsys.readouterr().err


def test_unknown_task_error_is_not_wrapped_in_quotes(capsys):
    with pytest.raises(SystemExit):
        main(["--task", "typo"])
    assert "error: no task 'typo'" in capsys.readouterr().err
