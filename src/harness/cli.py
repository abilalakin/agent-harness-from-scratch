"""The terminal program: read a line, ask the agent, print the answer."""

import sys
from collections.abc import Callable
from pathlib import Path

import openai
from mcp import StdioServerParameters

from harness.agent import SYSTEM_PROMPT, Agent
from harness.config import Settings, load_settings
from harness.file_tools import MISSING_DATA_HINT, make_file_tools
from harness.mcp_client import McpConnection, make_mcp_tools
from harness.mcp_server import SERVER_NAME
from harness.model import OpenAIChatModel
from harness.sql_tools import make_sql_tools
from harness.tools import BUILTIN_TOOLS, Tool


def run_repl(
    agent: Agent,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    agent.on_trim = lambda n: write(f"  [context] trimmed {n} old message(s) to fit")

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
        if agent.context_window:
            line = f"  [context ~{agent.context_tokens} of {agent.context_window} tokens]"
            if agent.over_budget:
                # Nothing more could be cut. Ollama will drop the oldest text itself, silently.
                line += " (over budget: the model may have lost the start of the conversation)"
            write(line)


def show_tool_call(name: str, arguments: str, result: str) -> None:
    """Print each tool call, so you can watch what the agent does between your question and its answer."""
    short = result if len(result) <= 200 else result[:200] + "..."
    print(f"  [tool] {name}({arguments}) -> {short}")


def show_thinking(text: str) -> None:
    """Print the model's reasoning before its tool calls and answer, so the wait is not a black box."""
    lines = text.splitlines()
    if not lines:
        return
    first, *rest = lines
    print(f"  [thinking] {first}")
    for line in rest:
        print(f"             {line}")


def build_agent(
    settings: Settings,
    system_prompt: str = SYSTEM_PROMPT,
    sql_tools: list[Tool] | None = None,
    on_thinking: Callable[[str], None] | None = None,
) -> Agent:
    """The agent with every tool. The REPL and the evals both build it here, so the evals measure the same agent you run."""
    if sql_tools is None:
        sql_tools = make_sql_tools(settings.data_dir / "erp.db")
    return Agent(
        OpenAIChatModel(settings, on_thinking=on_thinking),
        system_prompt,
        tools=[*BUILTIN_TOOLS, *make_file_tools(settings.data_dir), *sql_tools],
        max_steps=settings.max_steps,
        context_window=settings.context_window,  # run_repl adds the on_trim notice
    )


def start_erp_mcp_server(db_path: Path) -> McpConnection:
    """Start erp-mcp as a subprocess. Its log lines go to logs/mcp-erp.log, not your terminal."""
    Path("logs").mkdir(exist_ok=True)
    errlog = open(Path("logs") / f"mcp-{SERVER_NAME}.log", "a")
    command = [sys.executable, "-m", "harness.mcp_server", "--db", str(db_path.resolve())]
    return McpConnection(StdioServerParameters(command=command[0], args=command[1:]), errlog=errlog)


def main() -> None:
    settings = load_settings()
    print(f"harness: {settings.model} at {settings.base_url}. /reset clears history, /exit quits.")
    if not settings.data_dir.is_dir():
        print(MISSING_DATA_HINT)

    db_path = settings.data_dir / "erp.db"
    connection = None
    if settings.sql_via == "mcp":
        try:
            connection = start_erp_mcp_server(db_path)
        except RuntimeError as e:
            print(f"Error: {e}. See logs/mcp-{SERVER_NAME}.log")
            sys.exit(1)
        sql_tools = make_mcp_tools(connection, SERVER_NAME)
        print(f"SQL tools: from the MCP server '{SERVER_NAME}' ({', '.join(t.name for t in sql_tools)})")
    else:
        sql_tools = make_sql_tools(db_path)
        print("SQL tools: built in (set HARNESS_SQL_VIA=mcp to use the MCP server)")

    agent = build_agent(settings, sql_tools=sql_tools, on_thinking=show_thinking)
    agent.on_tool_call = show_tool_call
    try:
        run_repl(agent)
    finally:
        if connection:
            connection.close()  # ends the server process too
