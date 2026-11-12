"""Keeping the conversation inside the context window.

The model sees a fixed number of tokens (8192 here). The message list only grows,
so sooner or later it won't fit. Ollama then drops the oldest text silently, system
prompt included. The harness has to do the cutting itself, and do it on purpose.

Two stages, cheapest first:
1. Shorten old tool results. They are the biggest messages, and the model has already
   used them. Each becomes a one-line stub that still says what was asked.
2. Drop whole old turns (a user message and everything up to the next one). Whole turns,
   because half a turn leaves a tool call without its result, which breaks the next call.

The newest user message and the system prompt are never dropped.
"""

import json

from harness.model import Message

CHARS_PER_TOKEN = 4  # a rough but useful rule of thumb for English and code
REPLY_RESERVE = 2000  # tokens kept free for the model's answer (Qwen3 thinks out loud first)
KEEP_RECENT_TOOL_RESULTS = 2  # the newest tool results are what the model is working on right now


def estimate_tokens(messages: list[Message], tools: list[dict] | None = None) -> int:
    """About how many tokens a request will take. An estimate: real tokenizers vary by a few percent."""
    return len(json.dumps(messages) + json.dumps(tools or [])) // CHARS_PER_TOKEN


def _stub_for(messages: list[Message], tool_message: Message) -> str:
    """A one-line replacement for an old tool result, naming the call it answered."""
    for message in messages:
        for call in message.get("tool_calls") or []:
            if call.get("id") == tool_message.get("tool_call_id"):
                arguments = str(call["function"].get("arguments", ""))[:80]
                return f"[old result removed to save space: {call['function']['name']}({arguments})]"
    return "[old result removed to save space]"


def fit_to_budget(messages: list[Message], budget: int) -> tuple[list[Message], int]:
    """Return a copy of the messages that fits in `budget` tokens, and how many changes it took.

    If even the newest turn alone is too big, it comes back unchanged: nothing more can go.
    """
    messages = list(messages)  # a new list; changed messages are new dicts, so the input stays as it was
    changes = 0

    # Stage 1: shorten old tool results, oldest first, until it fits.
    tool_positions = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    for i in tool_positions[: len(tool_positions) - KEEP_RECENT_TOOL_RESULTS]:
        if estimate_tokens(messages) <= budget:
            break
        if messages[i]["content"].startswith("[old result removed"):
            continue  # already a stub
        messages[i] = {**messages[i], "content": _stub_for(messages, messages[i])}
        changes += 1

    # Stage 2: drop whole turns, oldest first, until it fits. The last turn always stays.
    while estimate_tokens(messages) > budget:
        user_positions = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(user_positions) < 2:
            break
        del messages[user_positions[0] : user_positions[1]]
        changes += 1

    return messages, changes
