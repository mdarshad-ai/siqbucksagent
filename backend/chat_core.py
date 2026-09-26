"""Chat pieces shared by the public chat endpoints and the admin preview."""

import json
import logging
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints

import limits
from llm_service import _get_api_key, chat_with_agent, stream_agent

logger = logging.getLogger(__name__)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

GENERIC_ERROR = "The agent couldn't reply right now. Please try again."


class ChatMessage(BaseModel):
    # Only plain conversation turns - a client must not be able to inject its
    # own "system" (or "tool") messages alongside the agent's system prompt.
    role: Literal["user", "assistant"]
    content: str
    # Display-only extras on an assistant reply: stone cards, tappable
    # follow-ups, and a handoff offer. Echoed back to the client with the
    # history, never sent to the model.
    cards: list[dict] | None = None
    suggestions: list[str] | None = None
    handoff: dict | None = None


class ChatResponse(BaseModel):
    reply: str
    cards: list[dict] = []
    suggestions: list[str] = []
    handoff: dict | None = None
    history: list[ChatMessage]


def _require_key():
    if not _get_api_key():
        raise HTTPException(
            status_code=500,
            detail=(
                "No OpenRouter API key found. Set OPENROUTER_API_KEY, or put "
                "it in a file and set OPENROUTER_API_KEY_FILE to that path."
            ),
        )


def _model_history(history: list[ChatMessage]):
    # Long chats resend everything on each turn, so only the most recent
    # messages go to the model (the client still keeps the full history).
    keep = limits.get_settings()["history_messages"]
    return [{"role": h.role, "content": h.content} for h in history[-keep:]]


def _updated_history(history, message, result):
    return [
        *history,
        ChatMessage(role="user", content=message),
        ChatMessage(
            role="assistant",
            content=result["reply"],
            cards=result["cards"] or None,
            suggestions=result["suggestions"] or None,
            handoff=result["handoff"],
        ),
    ]


def run_chat(agent_id: str, message: str, history: list[ChatMessage], agent_override=None):
    """One whole reply at once (admin preview, and clients without streaming)."""
    _require_key()
    try:
        result = chat_with_agent(
            agent_id, message, _model_history(history), agent_override=agent_override
        )
    except Exception:
        # Log the full upstream error server-side; the raw OpenRouter/provider
        # message can contain request ids and account details, so the client
        # only gets a generic error.
        logger.exception("Chat request to the model failed")
        raise HTTPException(status_code=502, detail=GENERIC_ERROR)
    return ChatResponse(
        reply=result["reply"],
        cards=result["cards"],
        suggestions=result["suggestions"],
        handoff=result["handoff"],
        history=_updated_history(history, message, result),
    )


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_chat(agent_id: str, message: str, history: list[ChatMessage]):
    """Server-sent events for one reply: delta / card / suggestions / handoff
    as they happen, then "done" with the full updated history (or "error")."""
    _require_key()
    model_history = _model_history(history)

    def events():
        try:
            for event in stream_agent(agent_id, message, model_history):
                kind = event.pop("type")
                if kind == "done":
                    event["history"] = [
                        m.model_dump(exclude_none=True)
                        for m in _updated_history(history, message, event)
                    ]
                yield _sse(kind, event)
        except Exception:
            logger.exception("Streaming chat request to the model failed")
            yield _sse("error", {"message": GENERIC_ERROR})

    return events()
