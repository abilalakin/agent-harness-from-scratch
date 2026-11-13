"""A stand-in for the real model, so tests are free, fast and offline."""

import copy

from harness.model import Message
from harness.tools import Tool


class FakeModel:
    """Returns (or raises) the given replies in order, and records every call."""

    def __init__(self, replies: list[Message | BaseException]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        # Deep copy: the agent keeps changing its list after the call.
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):  # BaseException also covers Ctrl+C
            raise reply
        return reply


def tool_reply(name: str, args: str, id: str = "c1") -> Message:
    """An assistant message that asks for one tool call."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": id, "type": "function", "function": {"name": name, "arguments": args}}],
    }


# A tool whose result is big enough to need trimming after a few calls.
BIG = Tool("big", "", {"type": "object", "properties": {}}, lambda: "z" * 4000)
