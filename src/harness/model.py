"""Talking to the model.

The rest of the harness only knows the ChatModel protocol: send messages, get one
assistant message back. Tests swap in a fake; the real one calls Ollama over HTTP.
"""

import re
from collections.abc import Callable
from typing import Any, Protocol

from openai import OpenAI

from harness.config import Settings

# One chat message in OpenAI format, e.g. {"role": "user", "content": "hi"}.
Message = dict[str, Any]


class ChatModel(Protocol):
    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        """Return {"role": "assistant", "content": ...}, plus "tool_calls" when the model asks for tools."""
        ...


_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def split_thinking(text: str | None) -> tuple[str, str | None]:
    """Separate an inline <think>...</think> block from the answer: (thinking, answer).

    Ollama now returns thinking in its own `reasoning` field, but older servers (and some
    other models) put it inline, so both ways are handled.
    """
    if text is None:
        return "", None
    thinking = " ".join(m.strip() for m in _THINK_BLOCK.findall(text))
    text = _THINK_BLOCK.sub("", text)
    # A reply cut off mid-thought has an opening tag and no closing one.
    if "<think>" in text:
        text, _, rest = text.partition("<think>")
        thinking = (thinking + " " + rest.strip()).strip()
    return thinking, text.strip()


class OpenAIChatModel:
    """A ChatModel backed by any OpenAI-style server. Here: Ollama."""

    def __init__(
        self,
        settings: Settings,
        client: OpenAI | None = None,
        on_thinking: Callable[[str], None] | None = None,
    ):
        self.model = settings.model
        self.client = client or OpenAI(base_url=settings.base_url, api_key=settings.api_key)
        # Called with the model's reasoning text, when there is any, so the CLI can show it.
        self.on_thinking = on_thinking

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:  # some servers reject an empty tools list
            kwargs["tools"] = tools
        reply = self.client.chat.completions.create(**kwargs).choices[0].message

        inline, content = split_thinking(reply.content)
        # Ollama's own field first, inline tags as a fallback. Stripped here, so no hook has to check for blank text.
        thinking = (getattr(reply, "reasoning", None) or inline).strip()
        if thinking and self.on_thinking:
            self.on_thinking(thinking)

        message: Message = {"role": "assistant", "content": content}
        if reply.tool_calls:
            message["tool_calls"] = [call.model_dump() for call in reply.tool_calls]
        return message
