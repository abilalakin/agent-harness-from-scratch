import pytest

from fakes import FakeModel
from harness.agent import SYSTEM_PROMPT, Agent


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
