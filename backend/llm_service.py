import json
import os
from pathlib import Path

from openai import OpenAI

import database
from agent_config import get_agent

DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# OpenAI-style function-calling tool schema (this is the shape OpenRouter
# expects, regardless of which underlying model you route to).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": (
                "Search this agent's own inventory by keyword (matches item "
                "name, description, or category). Returns matching items with "
                "id, name, description, price, quantity, and category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword to search for, e.g. 'sapphire' or 'quartz'.",
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
            "description": "Get full details for one item in this agent's inventory by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item's id."}
                },
                "required": ["item_id"],
            },
        },
    },
]

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


def _run_tool(agent_id: str, tool_name: str, tool_args: dict):
    if tool_name == "search_inventory":
        results = database.search_inventory(agent_id, tool_args.get("query", ""))
        return json.dumps({"results": results})
    if tool_name == "get_item_details":
        item = database.get_item(agent_id, tool_args.get("item_id"))
        return json.dumps({"item": item} if item else {"error": "not found"})
    return json.dumps({"error": f"unknown tool {tool_name}"})


def chat_with_agent(agent_id: str, message: str, history: list[dict]):
    """
    history: list of {"role": "user"|"assistant", "content": str} from prior
    turns (plain text only - this is what the frontend stores and replays).

    Returns: (reply_text, updated_history) where updated_history is the same
    plain-text shape with this turn appended. Any tool-call exchange happens
    only within this single call and is not persisted.
    """
    agent = get_agent(agent_id)
    if not agent:
        raise ValueError(f"Unknown agent_id: {agent_id}")

    if not _get_api_key():
        raise RuntimeError(
            "No OpenRouter API key found. Set OPENROUTER_API_KEY, or put the "
            "key in a file and point OPENROUTER_API_KEY_FILE at it."
        )

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    plain_history = [{"role": h["role"], "content": h["content"]} for h in history]

    messages = [{"role": "system", "content": agent["system_prompt"]}]
    messages.extend(plain_history)
    messages.append({"role": "user", "content": message})

    reply_text = "Sorry, I'm having trouble looking that up right now."

    client = _get_client()

    for _ in range(5):
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
            result = _run_tool(agent_id, tc.function.name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    plain_history.append({"role": "user", "content": message})
    plain_history.append({"role": "assistant", "content": reply_text})
    return reply_text, plain_history
