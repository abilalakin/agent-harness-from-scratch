"""The agent: owns the conversation history and talks to the model."""

from harness.model import ChatModel, Message

SYSTEM_PROMPT = "You are a helpful assistant. Answer briefly."


class Agent:
    def __init__(self, model: ChatModel, system_prompt: str = SYSTEM_PROMPT):
        self.model = model
        self.system_prompt = system_prompt
        self.messages: list[Message] = []
        self.reset()

    def reset(self) -> None:
        """Forget the conversation. Only the system prompt stays."""
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def ask(self, user_text: str) -> str:
        """Send the whole history plus the new question. Return the answer text ("" if none).

        The model remembers nothing between calls. Memory is this list, sent again every time.
        """
        turn = self.messages + [{"role": "user", "content": user_text}]
        reply = self.model.complete(turn)
        # Save only after the model answered, so a failed call leaves no half-finished turn.
        self.messages = turn + [reply]
        return reply.get("content") or ""
