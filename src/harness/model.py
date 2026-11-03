"""Talking to the model.

The rest of the harness only knows the ChatModel protocol: send messages, get one
assistant message back. Tests swap in a fake; the real one calls Ollama over HTTP.
"""

import re
from typing import Any, Protocol

from openai import OpenAI

from harness.config import Settings

# One chat message in OpenAI format, e.g. {"role": "user", "content": "hi"}.
Message = dict[str, Any]


class ChatModel(Protocol):
    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        """Return {"role": "assistant", "content": ...}, plus "tool_calls" when the model asks for tools."""
        ...


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str | None) -> str | None:
    """Remove Qwen3's <think>...</think> reasoning, so only the answer is left."""
    if text is None:
        return None
    text = _THINK_BLOCK.sub("", text)
    # A reply cut off mid-thought has an opening tag and no closing one.
    if "<think>" in text:
        text = text[: text.index("<think>")]
    return text.strip()


class OpenAIChatModel:
    """A ChatModel backed by any OpenAI-style server. Here: Ollama."""

    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.model = settings.model
        self.client = client or OpenAI(base_url=settings.base_url, api_key=settings.api_key)

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:  # some servers reject an empty tools list
            kwargs["tools"] = tools
        reply = self.client.chat.completions.create(**kwargs).choices[0].message

        message: Message = {"role": "assistant", "content": strip_thinking(reply.content)}
        if reply.tool_calls:
            message["tool_calls"] = [call.model_dump() for call in reply.tool_calls]
        return message
