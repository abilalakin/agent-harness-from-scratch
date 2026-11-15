import httpx2
import openai

from fakes import BIG, FakeModel, tool_reply
from harness.agent import Agent
from harness.cli import run_repl, show_thinking
from harness.context import REPLY_RESERVE


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


def test_repl_ctrl_c_while_model_answers_stops_that_question_only():
    agent = Agent(FakeModel([KeyboardInterrupt(), reply("still here")]))
    out = run(agent, ["slow question", "next", "/exit"])
    assert any("(stopped)" in line for line in out)
    assert any("still here" in line for line in out)
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant"]


def test_repl_shows_context_size_when_the_agent_has_a_window():
    out = run(Agent(FakeModel([reply("x")]), context_window=8192), ["hi", "/exit"])
    assert any("[context ~" in line and "of 8192 tokens]" in line for line in out)


def test_repl_hides_context_size_without_a_window():
    out = run(Agent(FakeModel([reply("x")])), ["hi", "/exit"])
    assert not any("[context" in line for line in out)


def test_repl_reports_trimming_through_write():
    model = FakeModel([tool_reply("big", "{}", f"c{i}") for i in range(3)] + [reply("done")])
    agent = Agent(model, tools=[BIG], context_window=REPLY_RESERVE + 1800)
    out = run(agent, ["go", "/exit"])
    assert any("[context] trimmed" in line for line in out)


def test_repl_warns_when_the_newest_turn_alone_is_over_budget():
    out = run(Agent(FakeModel([reply("x")]), context_window=3000), ["q" * 20000, "/exit"])
    assert any("over budget" in line for line in out)


def test_show_thinking_prints_it_indented(capsys):
    show_thinking("first line\nsecond line")
    assert capsys.readouterr().out == "  [thinking] first line\n             second line\n"


def test_show_thinking_prints_nothing_for_empty_text(capsys):
    show_thinking("")
    assert capsys.readouterr().out == ""
