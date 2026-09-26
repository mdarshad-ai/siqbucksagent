import json
import os
from pathlib import Path

from openai import OpenAI

import database
from media import stone_card
from agent_config import compose_system_prompt

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# OpenAI-style function-calling tool schema (this is the shape OpenRouter
# expects, regardless of which underlying model you route to).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": (
                "Search this agent's own inventory by keywords (matches name, "
                "category, description, origin, color, cut, and story). An "
                "empty query lists everything. Returns a summary of each "
                "matching stone: id, name, category, carat, cut, color, "
                "origin, price, quantity, and status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords, e.g. 'sapphire', 'blue oval', or '' for everything.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_item_details",
            "description": (
                "Get full details for one stone by its id, including its "
                "story (shareable) and private sales guidance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item's id."}
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_item",
            "description": (
                "Show the customer a card for a stone you are recommending, "
                "with its photos, videos, price and key details. Call it for "
                "each stone you actually recommend (at most 3 per reply), not "
                "for every stone you mention. It fails for sold-out stones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The stone's id."}
                },
                "required": ["item_id"],
            },
        },
    },
]

MAX_CARDS_PER_REPLY = 3

_client = None


def _get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key

    # Fall back to a plain-text token file (path set via OPENROUTER_API_KEY_FILE,
    # default token.txt next to this file) - useful if you keep secrets outside
    # of .env.
    file_path = os.environ.get("OPENROUTER_API_KEY_FILE", "token.txt")
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    if path.exists():
        return path.read_text().strip()

    return None


def _get_client():
    global _client
    if _client is None:
        api_key = _get_api_key()
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or "missing-key",  # placeholder so init doesn't crash
        )
    return _client


def _extra_headers():
    # Optional, recommended by OpenRouter for attribution/rate-limit purposes.
    headers = {}
    site_url = os.environ.get("OPENROUTER_SITE_URL", "").strip()
    site_name = os.environ.get("OPENROUTER_SITE_NAME", "").strip()
    if site_url:
        headers["HTTP-Referer"] = site_url
    if site_name:
        headers["X-Title"] = site_name
    return headers


SEARCH_SUMMARY_FIELDS = (
    "id", "name", "category", "carat", "cut", "color", "origin", "price",
    "quantity", "status",
)
DETAIL_FIELDS = database.ITEM_PUBLIC_FIELDS + ("story", "sales_guidance")


def _run_tool(agent_id: str, tool_name: str, tool_args: dict, shown: list | None = None):
    """Run one tool call. shown collects stone cards from show_item."""
    if tool_name == "search_inventory":
        results = database.search_items(agent_id, tool_args.get("query", ""))
        summaries = [{k: r[k] for k in SEARCH_SUMMARY_FIELDS} for r in results]
        return json.dumps({"results": summaries})
    if tool_name == "get_item_details":
        item = database.get_item(agent_id, tool_args.get("item_id"))
        if not item:
            return json.dumps({"error": "not found"})
        return json.dumps({"item": {k: item[k] for k in DETAIL_FIELDS}})
    if tool_name == "show_item":
        item = database.get_item(agent_id, tool_args.get("item_id"))
        if not item:
            return json.dumps({"error": "not found"})
        if item["status"] == "sold" or item["quantity"] <= 0:
            return json.dumps({"error": "sold out - don't show or recommend it"})
        shown = shown if shown is not None else []
        if any(card["id"] == item["id"] for card in shown):
            return json.dumps({"ok": True, "note": "already shown"})
        if len(shown) >= MAX_CARDS_PER_REPLY:
            return json.dumps({"error": f"at most {MAX_CARDS_PER_REPLY} cards per reply"})
        shown.append(stone_card(item))
        return json.dumps({"ok": True, "media_count": len(shown[-1]["media"])})
    return json.dumps({"error": f"unknown tool {tool_name}"})


def chat_with_agent(agent_id: str, message: str, history: list[dict], agent_override=None):
    """
    history: list of {"role": "user"|"assistant", "content": str} from prior
    turns (plain text only - this is what the frontend stores and replays).

    Returns: (reply_text, updated_history, cards). updated_history is the same
    plain-text shape with this turn appended; cards are the stones the agent
    chose to show (show_item) during this reply. Any tool-call exchange
    happens only within this single call and is not persisted.

    agent_override: optional dict with persona/selling_rules to use instead of
    the published ones (the admin "preview" chat). Tools still run against
    agent_id's real inventory.
    """
    agent = database.get_agent(agent_id)
    if agent and agent_override:
        agent = {**agent, **agent_override}
    if not agent:
        raise ValueError(f"Unknown agent_id: {agent_id}")

    if not _get_api_key():
        raise RuntimeError(
            "No OpenRouter API key found. Set OPENROUTER_API_KEY, or put the "
            "key in a file and point OPENROUTER_API_KEY_FILE at it."
        )

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    plain_history = [{"role": h["role"], "content": h["content"]} for h in history]

    messages = [{"role": "system", "content": compose_system_prompt(agent)}]
    messages.extend(plain_history)
    messages.append({"role": "user", "content": message})

    reply_text = "Sorry, I'm having trouble looking that up right now."

    client = _get_client()
    cards = []

    for _ in range(8):  # search + details for a few stones
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            extra_headers=_extra_headers(),
        )
        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            reply_text = (msg.content or "").strip()
            break

        # Record the assistant's tool-call turn, then run each tool and feed
        # results back in as "tool" role messages.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(agent_id, tc.function.name, args, shown=cards)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    plain_history.append({"role": "user", "content": message})
    plain_history.append({"role": "assistant", "content": reply_text})
    return reply_text, plain_history, cards
