from types import SimpleNamespace

from openai.types.chat import ChatCompletion

from harness.config import Settings
from harness.model import OpenAIChatModel, split_thinking


class StubClient:
    """Looks like OpenAI() just enough for OpenAIChatModel: client.chat.completions.create(...)."""

    def __init__(self, message: dict):
        self.message = message
        self.last_kwargs: dict = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs) -> ChatCompletion:
        self.last_kwargs = kwargs
        return ChatCompletion.model_validate(
            {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": kwargs["model"],
                "choices": [{"index": 0, "finish_reason": "stop", "message": self.message}],
            }
        )


def test_split_thinking_separates_block_from_answer():
    assert split_thinking("<think>hmm</think>\n\nHello") == ("hmm", "Hello")


def test_split_thinking_keeps_plain_text_and_none():
    assert split_thinking("Hello") == ("", "Hello")
    assert split_thinking(None) == ("", None)


def test_split_thinking_unclosed_block_is_all_thinking():
    assert split_thinking("<think>never closed") == ("never closed", "")


def test_complete_converts_text_reply_and_omits_empty_tools():
    stub = StubClient({"role": "assistant", "content": "<think>x</think>Hi"})
    msg = OpenAIChatModel(Settings(), client=stub).complete([{"role": "user", "content": "hey"}])
    assert msg == {"role": "assistant", "content": "Hi"}
    assert "tools" not in stub.last_kwargs
    assert stub.last_kwargs["model"] == "qwen3:8b"


def test_complete_converts_tool_calls():
    stub = StubClient(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "calculate", "arguments": '{"a": 1}'}}
            ],
        }
    )
    tools = [{"type": "function", "function": {"name": "calculate", "parameters": {}}}]
    msg = OpenAIChatModel(Settings(), client=stub).complete([{"role": "user", "content": "1?"}], tools=tools)
    assert msg["tool_calls"][0]["id"] == "c1"
    assert msg["tool_calls"][0]["function"] == {"name": "calculate", "arguments": '{"a": 1}'}
    assert stub.last_kwargs["tools"] == tools


def test_thinking_from_the_reasoning_field_goes_to_on_thinking():
    stub = StubClient({"role": "assistant", "content": "51.", "reasoning": "17*3: 10*3 + 7*3 = 51"})
    seen = []
    msg = OpenAIChatModel(Settings(), client=stub, on_thinking=seen.append).complete([{"role": "user", "content": "?"}])
    assert seen == ["17*3: 10*3 + 7*3 = 51"] and msg == {"role": "assistant", "content": "51."}


def test_inline_think_block_also_goes_to_on_thinking():
    stub = StubClient({"role": "assistant", "content": "<think>hmm</think>Hi"})
    seen = []
    OpenAIChatModel(Settings(), client=stub, on_thinking=seen.append).complete([{"role": "user", "content": "?"}])
    assert seen == ["hmm"]


def test_no_thinking_means_no_call():
    stub = StubClient({"role": "assistant", "content": "Hi"})
    seen = []
    OpenAIChatModel(Settings(), client=stub, on_thinking=seen.append).complete([{"role": "user", "content": "?"}])
    assert seen == []
