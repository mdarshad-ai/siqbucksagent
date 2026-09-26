"""Chat pieces shared by the public chat endpoint and the admin preview."""

import logging
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints

import limits
from llm_service import _get_api_key, chat_with_agent

logger = logging.getLogger(__name__)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatMessage(BaseModel):
    # Only plain conversation turns - a client must not be able to inject its
    # own "system" (or "tool") messages alongside the agent's system prompt.
    role: Literal["user", "assistant"]
    content: str
    # Stone cards shown with an assistant reply. Display-only: echoed back to
    # the client with the history, never sent to the model.
    cards: list[dict] | None = None


class ChatResponse(BaseModel):
    reply: str
    cards: list[dict] = []
    history: list[ChatMessage]


def run_chat(agent_id: str, message: str, history: list[ChatMessage], agent_override=None):
    """Shared by the public chat and the admin persona preview."""
    if not _get_api_key():
        raise HTTPException(
            status_code=500,
            detail=(
                "No OpenRouter API key found. Set OPENROUTER_API_KEY, or put "
                "it in a file and set OPENROUTER_API_KEY_FILE to that path."
            ),
        )

    # Long chats resend everything on each turn, so only the most recent
    # messages go to the model (the client still keeps the full history).
    keep = limits.get_settings()["history_messages"]
    history_dicts = [h.model_dump(exclude={"cards"}) for h in history[-keep:]]
    try:
        reply, _, cards = chat_with_agent(
            agent_id, message, history_dicts, agent_override=agent_override
        )
    except Exception:
        # Log the full upstream error server-side; the raw OpenRouter/provider
        # message can contain request ids and account details, so the client
        # only gets a generic error.
        logger.exception("Chat request to the model failed")
        raise HTTPException(
            status_code=502,
            detail="The agent couldn't reply right now. Please try again.",
        )
    updated_history = [
        *history,
        ChatMessage(role="user", content=message),
        ChatMessage(role="assistant", content=reply, cards=cards or None),
    ]
    return ChatResponse(reply=reply, cards=cards, history=updated_history)
