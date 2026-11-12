import copy
import json

from harness.context import estimate_tokens, fit_to_budget

SYSTEM = {"role": "system", "content": "You are a helpful assistant."}


def tool_turn(i, size):
    """One question that needed one tool call whose result is `size` characters long."""
    call = {"id": f"c{i}", "type": "function", "function": {"name": "read_pdf", "arguments": json.dumps({"path": f"f{i}.pdf"})}}
    return [
        {"role": "user", "content": f"read file {i}"},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        {"role": "tool", "tool_call_id": f"c{i}", "content": "x" * size},
        {"role": "assistant", "content": f"done {i}"},
    ]


def plain_turn(i, size):
    """One question and answer, no tools."""
    return [{"role": "user", "content": f"q{i} " + "y" * size}, {"role": "assistant", "content": f"a{i}"}]


def test_estimate_is_chars_over_four():
    assert estimate_tokens([{"role": "user", "content": "x" * 400}]) in range(100, 115)


def test_under_budget_unchanged():
    msgs = [SYSTEM] + tool_turn(1, 100)
    assert fit_to_budget(msgs, 10_000) == (msgs, 0)


def test_shortens_oldest_tool_results_first_and_keeps_newest_two():
    msgs = [SYSTEM] + tool_turn(1, 4000) + tool_turn(2, 4000) + tool_turn(3, 4000) + tool_turn(4, 400)
    out, changes = fit_to_budget(msgs, 2500)
    contents = {m["tool_call_id"]: m["content"] for m in out if m["role"] == "tool"}
    assert contents["c1"] == '[old result removed to save space: read_pdf({"path": "f1.pdf"})]'
    assert contents["c3"] == "x" * 4000 and contents["c4"] == "x" * 400  # the newest two are never touched
    assert changes >= 1 and estimate_tokens(out) <= 2500


def test_drops_old_turns_when_shortening_is_not_enough():
    msgs = [SYSTEM] + [m for i in range(1, 30) for m in plain_turn(i, 400)]  # chat only, nothing to shorten
    out, _ = fit_to_budget(msgs, 1000)
    assert out[0] == SYSTEM and out[-2:] == msgs[-2:] and estimate_tokens(out) <= 1000


def test_never_leaves_a_tool_call_without_its_result():
    msgs = [SYSTEM] + [m for i in range(1, 8) for m in tool_turn(i, 3000)]
    out, _ = fit_to_budget(msgs, 1500)
    call_ids = {c["id"] for m in out if m["role"] == "assistant" for c in m.get("tool_calls", [])}
    result_ids = {m["tool_call_id"] for m in out if m["role"] == "tool"}
    assert call_ids == result_ids


def test_one_huge_newest_result_is_kept_and_does_not_crash():
    msgs = [SYSTEM] + tool_turn(1, 50_000)
    out, _ = fit_to_budget(msgs, 1000)
    assert out[0] == SYSTEM and any(m["role"] == "tool" and len(m["content"]) == 50_000 for m in out)


def test_input_list_is_not_changed():
    msgs = [SYSTEM] + tool_turn(1, 4000) + tool_turn(2, 4000) + tool_turn(3, 4000)
    before = copy.deepcopy(msgs)
    fit_to_budget(msgs, 1500)
    assert msgs == before
