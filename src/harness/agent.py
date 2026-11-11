"""The agent: owns the conversation history and runs the tool loop."""

from collections.abc import Callable, Sequence

from harness.model import ChatModel, Message
from harness.tools import Tool, run_tool_call

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer briefly. "
    "Use the tools when they help. If a tool returns an error, fix the arguments and try again. "
    "Practice data lives in a data folder: files and an ERP database. Look before you guess. "
    "For questions about many files, search first instead of reading every file."
)


class Agent:
    def __init__(
        self,
        model: ChatModel,
        system_prompt: str = SYSTEM_PROMPT,
        tools: Sequence[Tool] = (),
        max_steps: int = 10,
        on_tool_call: Callable[[str, str, str], None] | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = {tool.name: tool for tool in tools}
        self.max_steps = max_steps
        # Called as on_tool_call(name, arguments, result), so the CLI can show what happens.
        self.on_tool_call = on_tool_call
        self.messages: list[Message] = []
        self.reset()

    def reset(self) -> None:
        """Forget the conversation. Only the system prompt stays."""
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def ask(self, user_text: str) -> str:
        """Answer one question, calling tools as often as the model asks (up to max_steps).

        The model remembers nothing between calls. Memory is the message list, sent again every time.
        """
        # Work on a copy. Save it only when the turn ends, so a failed call leaves no half-finished turn.
        turn = self.messages + [{"role": "user", "content": user_text}]
        schemas = [tool.schema() for tool in self.tools.values()] or None

        for _ in range(self.max_steps):
            reply = self.model.complete(turn, schemas)
            turn.append(reply)

            calls = reply.get("tool_calls") or []
            if not calls:  # no tool requests: this is the final answer
                self.messages = turn
                return reply.get("content") or ""

            for call in calls:
                result = run_tool_call(self.tools, call)
                if self.on_tool_call:
                    self.on_tool_call(call["function"]["name"], str(call["function"].get("arguments")), result)
                # The tool_call_id tells the model which request this result answers.
                turn.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

        # Out of steps. End the turn with an answer anyway, so the history doesn't end on a
        # tool result nobody replied to (the model would get confused on the next question).
        stop = f"Stopped after {self.max_steps} tool steps without a final answer."
        self.messages = turn + [{"role": "assistant", "content": stop}]
        return stop
