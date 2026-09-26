"""Chat pieces shared by the public chat endpoint and the admin preview."""

import logging
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, StringConstraints

from llm_service import _get_api_key, chat_with_agent

logger = logging.getLogger(__name__)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatMessage(BaseModel):
    # Only plain conversation turns - a client must not be able to inject its
    # own "system" (or "tool") messages alongside the agent's system prompt.
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    reply: str
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

    history_dicts = [h.model_dump() for h in history]
    try:
        reply, updated_history = chat_with_agent(
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
    return ChatResponse(reply=reply, history=updated_history)
