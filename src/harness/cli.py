"""The terminal program: read a line, ask the agent, print the answer."""

from collections.abc import Callable

import openai

from harness.agent import Agent
from harness.config import load_settings
from harness.model import OpenAIChatModel


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
        except openai.APIConnectionError:
            write("Error: can't reach the model. Is Ollama running?")
            continue
        except openai.APIError as e:
            write(f"Error from model: {e}")
            continue

        write(f"agent> {answer or '(no reply)'}")


def main() -> None:
    settings = load_settings()
    print(f"harness: {settings.model} at {settings.base_url}. /reset clears history, /exit quits.")
    run_repl(Agent(OpenAIChatModel(settings)))
