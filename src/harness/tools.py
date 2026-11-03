"""Tools: functions the model can ask the harness to run.

The model never runs anything itself. It replies with a tool call (a name and
JSON arguments). The harness looks up the tool, runs it, and sends the result
back as text. Every mistake also comes back as text, so the model can read it
and try again.
"""

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from harness.model import Message

# Tool results go into the model's context, which only holds 8192 tokens (about 4 characters
# each). One big PDF or table could fill it, so every result is cut to this size.
# Step 5 replaces this blunt cut with paging and search.
MAX_TOOL_OUTPUT = 3000


def cap_output(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + (
        f"\n...[cut: {len(text) - limit} more characters. Ask for less, for example one page or fewer rows.]"
    )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str  # written for the model: when and why to use this tool
    parameters: dict  # JSON Schema for the arguments
    fn: Callable[..., str]

    def schema(self) -> dict:
        """The tool as the model sees it, in OpenAI's "function" format."""
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def run_tool_call(tools: Mapping[str, Tool], call: Message) -> str:
    """Run one tool call from the model. Always returns a string, never raises."""
    name = call["function"]["name"]
    raw_args = call["function"].get("arguments") or "{}"

    tool = tools.get(name)
    if tool is None:
        return f"Error: unknown tool '{name}'. Available tools: {', '.join(tools)}"

    # Most servers send arguments as a JSON string; some send a dict already.
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return f"Error: arguments are not valid JSON: {e}"
    else:
        args = raw_args
    if not isinstance(args, dict):
        return f"Error: bad arguments for '{name}': expected a JSON object, got {raw_args!r}"

    # Check the arguments match the function before calling it, so a missing or
    # extra argument is reported as the model's mistake, not as a tool crash.
    try:
        inspect.signature(tool.fn).bind(**args)
    except TypeError as e:
        return f"Error: bad arguments for '{name}': {e}"

    try:
        return cap_output(tool.fn(**args))
    except Exception as e:
        return f"Error: tool '{name}' failed: {e}"


# --- Built-in tools -------------------------------------------------------


def get_current_time(timezone: str = "UTC") -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat(timespec="seconds")


def calculate(a: float, op: str, b: float) -> str:
    # float() also accepts "6", because small models often send numbers as strings.
    a, b = float(a), float(b)
    if op == "+":
        return str(a + b)
    if op == "-":
        return str(a - b)
    if op == "*":
        return str(a * b)
    if op == "/":
        return str(a / b)
    raise ValueError(f"unknown op {op!r}, use one of + - * /")


BUILTIN_TOOLS: list[Tool] = [
    Tool(
        name="get_current_time",
        description="Get the current date and time in a time zone.",
        parameters={
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "description": "IANA time zone, like Europe/Istanbul. Default UTC."}
            },
        },
        fn=get_current_time,
    ),
    Tool(
        name="calculate",
        description="Do one arithmetic step on two numbers. Use it instead of doing math in your head.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "op": {"type": "string", "enum": ["+", "-", "*", "/"]},
                "b": {"type": "number"},
            },
            "required": ["a", "op", "b"],
        },
        fn=calculate,
    ),
]
