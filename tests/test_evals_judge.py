from fakes import FakeModel
from harness.evals.judge import JUDGE_CHECKS, Verdict, check_judge, judge_answer, judge_result
from harness.evals.runner import RunResult
from harness.evals.tasks import Task, contains


def reply(text):
    return FakeModel([{"role": "assistant", "content": text}])


def test_judge_reads_json_from_a_wordy_reply():
    v = judge_answer(reply('Sure. {"pass": true, "reason": "all points"} Hope that helps.'), "q", "a", "r")
    assert v == Verdict(True, "all points")


def test_judge_without_json_fails_with_a_reason():
    assert judge_answer(reply("looks fine to me"), "q", "a", "r") == Verdict(False, "judge gave no JSON")


def test_judge_sends_question_answer_and_rubric_without_tools():
    model = reply('{"pass": false, "reason": "no"}')
    judge_answer(model, "QQ", "AA", "RR")
    sent = model.calls[0]
    assert sent["tools"] is None and all(s in sent["messages"][-1]["content"] for s in ("QQ", "AA", "RR"))


def test_judge_result_overrides_pass_only_for_a_task_with_a_rubric():
    judged = Task("j", "q", check=contains("x"), rubric="r")
    plain = Task("p", "q", check=contains("x"))
    a = RunResult("j", 1, "x", [], True, None, 0, 1, 0.0, None)
    b = RunResult("p", 1, "x", [], True, None, 0, 1, 0.0, None)
    judge_result(reply('{"pass": false, "reason": "missing"}'), a, judged)
    judge_result(reply('{"pass": false, "reason": "missing"}'), b, plain)
    assert (a.passed, a.judge_reason) == (False, "missing") and b.passed


def test_check_judge_counts_disagreements():
    always_pass = FakeModel([{"role": "assistant", "content": '{"pass": true, "reason": "ok"}'}] * len(JUDGE_CHECKS))
    assert check_judge(always_pass, log=lambda s: None) == sum(1 for _, expected, _ in JUDGE_CHECKS if not expected)


def test_judge_does_not_trust_a_quoted_boolean():
    assert judge_answer(reply('{"pass": "false", "reason": "penalty missing"}'), "q", "a", "r").passed is False
    assert judge_answer(reply('{"pass": "true", "reason": "ok"}'), "q", "a", "r").passed is True


def test_judge_finds_the_verdict_after_other_braces():
    v = judge_answer(reply('The rubric {net 30} is met. {"pass": true, "reason": "x"}'), "q", "a", "r")
    assert v == Verdict(True, "x")


def test_a_judge_call_that_raises_fails_that_run_only():
    judged = Task("j", "q", check=contains("x"), rubric="r")
    a = RunResult("j", 1, "x", [], True, None, 0, 1, 0.0, None)
    model = FakeModel([RuntimeError("boom")])
    judge_result(model, a, judged)
    assert (a.passed, a.error) == (False, "judge: RuntimeError: boom")
