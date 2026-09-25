from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_ACCEPTED = 50  # reject oversized payloads outright
HISTORY_SENT_TO_AI = 10  # the server keeps only the most recent turns

MessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: MessageText


class ChatRequest(BaseModel):
    """Body of POST /patients/{id}/chat. The chat is stateless: the browser sends the earlier
    turns in `history`. That history is client-controlled, so it is validated here."""

    model_config = ConfigDict(extra="forbid")

    message: MessageText
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_ACCEPTED)

    @model_validator(mode="after")
    def check_turn_order(self) -> "ChatRequest":
        # Earlier turns must go user, assistant, user, assistant... and end with an assistant
        # reply, because `message` is the next user turn.
        for index, turn in enumerate(self.history):
            expected = "user" if index % 2 == 0 else "assistant"
            if turn.role != expected:
                raise ValueError("history must alternate user/assistant turns, starting with user")
        if self.history and self.history[-1].role != "assistant":
            raise ValueError("history must end with an assistant reply")
        return self

    def recent_history(self) -> list[ChatMessage]:
        """The last few turns (at most HISTORY_SENT_TO_AI), still starting with a user turn."""
        recent = self.history[-HISTORY_SENT_TO_AI:]
        return recent[1:] if recent and recent[0].role == "assistant" else recent


class ChatResponse(BaseModel):
    reply: str
