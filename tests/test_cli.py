import httpx2
import openai

from fakes import FakeModel
from harness.agent import Agent
from harness.cli import run_repl


def run(agent: Agent, inputs: list) -> list[str]:
    """Feed inputs to the REPL one by one; an Exception in the list is raised instead of returned."""
    pending = list(inputs)
    output: list[str] = []

    def read(prompt: str) -> str:
        item = pending.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    run_repl(agent, read=read, write=output.append)
    return output


def reply(text):
    return {"role": "assistant", "content": text}


def test_repl_prints_reply_and_exits_on_slash_exit():
    out = run(Agent(FakeModel([reply("Hello there")])), ["hi", "/exit"])
    assert any("Hello there" in line for line in out)


def test_repl_empty_reply_prints_no_reply():
    out = run(Agent(FakeModel([reply(None)])), ["hi", "/exit"])
    assert any("(no reply)" in line for line in out)


def test_repl_connection_error_prints_hint_and_continues():
    down = openai.APIConnectionError(request=httpx2.Request("POST", "http://x"))
    out = run(Agent(FakeModel([down, reply("back")])), ["hi", "hi again", "/exit"])
    assert any("Is Ollama running?" in line for line in out)
    assert any("back" in line for line in out)


def test_repl_eof_exits_cleanly():
    run(Agent(FakeModel([])), [EOFError()])


def test_repl_reset_clears_history():
    agent = Agent(FakeModel([reply("x")]))
    out = run(agent, ["hi", "/reset", "/exit"])
    assert any("(history cleared)" in line for line in out)
    assert len(agent.messages) == 1
