"""The terminal program: read a line, ask the agent, print the answer."""

from collections.abc import Callable

import openai

from harness.agent import Agent
from harness.config import load_settings
from harness.model import OpenAIChatModel
from harness.tools import BUILTIN_TOOLS


def run_repl(
    agent: Agent,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    while True:
        try:
            text = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            write("bye")
            return

        if not text:
            continue
        if text == "/exit":
            return
        if text == "/reset":
            agent.reset()
            write("(history cleared)")
            continue

        try:
            answer = agent.ask(text)
        except KeyboardInterrupt:
            # Ctrl+C while the model works: drop this question, keep the conversation.
            write("(stopped)")
            continue
        except openai.APIConnectionError:
            write("Error: can't reach the model. Is Ollama running?")
            continue
        except openai.APIError as e:
            write(f"Error from model: {e}")
            continue

        write(f"agent> {answer or '(no reply)'}")


def show_tool_call(name: str, arguments: str, result: str) -> None:
    """Print each tool call, so you can watch what the agent does between your question and its answer."""
    short = result if len(result) <= 200 else result[:200] + "..."
    print(f"  [tool] {name}({arguments}) -> {short}")


def main() -> None:
    settings = load_settings()
    print(f"harness: {settings.model} at {settings.base_url}. /reset clears history, /exit quits.")
    agent = Agent(
        OpenAIChatModel(settings),
        tools=BUILTIN_TOOLS,
        max_steps=settings.max_steps,
        on_tool_call=show_tool_call,
    )
    run_repl(agent)
