"""
The partner's opening pitch on a stone's page.

When a customer opens a stone page, its partner introduces the stone. The
pitch is the same for everyone, so it's written once and saved; later
visitors get the saved one instantly (no AI call, no cost). It's rewritten
when the stone, its certificates, the partner's persona or the model change.
"""

import hashlib
import json
import logging
import os

import database
from chat_core import GENERIC_ERROR, _sse
from llm_service import DEFAULT_MODEL, stream_agent

logger = logging.getLogger(__name__)


def opening_message(item: dict) -> str:
    """What the customer implicitly asks on arrival. It starts the chat
    history but isn't shown on the page."""
    return (
        f"I'm looking at the {item['name']} (stone #{item['id']}) on your catalogue "
        "page and can already see its photos and details. Tell me about it."
    )


def fingerprint(item: dict, agent: dict) -> str:
    certs = ",".join(str(c["id"]) for c in database.list_certificates(item["id"]))
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    raw = f"{item['updated_at']}|{agent['updated_at']}|{certs}|{model}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cached(item: dict, agent: dict):
    saved = database.get_pitch(item["id"])
    if saved and saved["fingerprint"] == fingerprint(item, agent):
        return saved
    return None


def _history(message, reply, suggestions):
    assistant = {"role": "assistant", "content": reply}
    if suggestions:
        assistant["suggestions"] = suggestions
    return [{"role": "user", "content": message, "hidden": True}, assistant]


def stream_pitch(item: dict, agent: dict):
    """Server-sent events, same shape as the chat stream: delta /
    suggestions, then done (with a two-message history) or error."""
    message = opening_message(item)
    saved = cached(item, agent)

    def replay():
        yield _sse("delta", {"text": saved["reply"]})
        if saved["suggestions"]:
            yield _sse("suggestions", {"options": saved["suggestions"]})
        yield _sse("done", {
            "reply": saved["reply"], "cards": [], "suggestions": saved["suggestions"],
            "handoff": None, "history": _history(message, saved["reply"], saved["suggestions"]),
        })

    def generate():
        try:
            for event in stream_agent(item["agent_id"], message, []):
                kind = event.pop("type")
                # The page already shows this stone, so cards and handoffs
                # from the opening pitch are dropped.
                if kind in ("card", "handoff"):
                    continue
                if kind == "done":
                    database.save_pitch(item["id"], fingerprint(item, agent), event["reply"], event["suggestions"])
                    yield _sse("done", {
                        "reply": event["reply"], "cards": [], "suggestions": event["suggestions"],
                        "handoff": None, "history": _history(message, event["reply"], event["suggestions"]),
                    })
                else:
                    yield _sse(kind, event)
        except Exception:
            logger.exception("Stone pitch failed")
            yield _sse("error", {"message": GENERIC_ERROR})

    return replay() if saved else generate()
