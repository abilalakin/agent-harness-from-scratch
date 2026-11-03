"""A stand-in for the real model, so tests are free, fast and offline."""

import copy

from harness.model import Message


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
