import pytest

from fakes import FakeModel
from harness.agent import SYSTEM_PROMPT, Agent
from harness.tools import BUILTIN_TOOLS


def test_ask_returns_reply_and_keeps_history():
    model = FakeModel([{"role": "assistant", "content": "Hi!"}, {"role": "assistant", "content": "Bilal"}])
    agent = Agent(model)
    assert agent.ask("hello") == "Hi!"
    agent.ask("my name?")
    sent = model.calls[1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]


def test_failed_call_leaves_history_unchanged():
    agent = Agent(FakeModel([RuntimeError("down")]))
    with pytest.raises(RuntimeError):
        agent.ask("hello")
    assert len(agent.messages) == 1


def test_reset_keeps_only_system_message():
    agent = Agent(FakeModel([{"role": "assistant", "content": "x"}]))
    agent.ask("a")
    agent.reset()
    assert agent.messages == [{"role": "system", "content": SYSTEM_PROMPT}]


def tool_reply(name, args, id="c1"):
    """An assistant message that asks for one tool call."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": id, "type": "function", "function": {"name": name, "arguments": args}}],
    }


def test_tool_call_then_final_answer():
    model = FakeModel(
        [tool_reply("calculate", '{"a": 6, "op": "*", "b": 7}'), {"role": "assistant", "content": "It is 42."}]
    )
    seen = []
    agent = Agent(model, tools=BUILTIN_TOOLS, on_tool_call=lambda *a: seen.append(a))
    assert agent.ask("6 times 7?") == "It is 42."
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert agent.messages[3] == {"role": "tool", "tool_call_id": "c1", "content": "42.0"}
    assert seen == [("calculate", '{"a": 6, "op": "*", "b": 7}', "42.0")]
    assert model.calls[0]["tools"][0]["type"] == "function"


def test_tool_error_goes_back_to_model():
    model = FakeModel([tool_reply("weather", "{}"), {"role": "assistant", "content": "Sorry."}])
    Agent(model, tools=BUILTIN_TOOLS).ask("weather?")
    assert model.calls[1]["messages"][-1]["content"].startswith("Error: unknown tool 'weather'")


def test_stops_after_max_steps():
    model = FakeModel([tool_reply("calculate", '{"a": 1, "op": "+", "b": 1}', id=f"c{i}") for i in range(3)])
    agent = Agent(model, tools=BUILTIN_TOOLS, max_steps=3)
    out = agent.ask("loop")
    assert out == "Stopped after 3 tool steps without a final answer."
    assert len(model.calls) == 3
    # History must end with an answer, so the next question starts clean.
    assert agent.messages[-1] == {"role": "assistant", "content": out}


def test_no_tools_means_tools_not_sent():
    model = FakeModel([{"role": "assistant", "content": "hi"}])
    Agent(model).ask("hey")
    assert model.calls[0]["tools"] is None


def test_failure_mid_tool_loop_leaves_history_unchanged():
    model = FakeModel([tool_reply("calculate", '{"a": 1, "op": "+", "b": 1}'), RuntimeError("down")])
    agent = Agent(model, tools=BUILTIN_TOOLS)
    with pytest.raises(RuntimeError):
        agent.ask("1+1?")
    assert len(agent.messages) == 1
