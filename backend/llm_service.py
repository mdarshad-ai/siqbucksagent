import json
import os
from pathlib import Path

from openai import OpenAI

import database
import gemgenerate
import limits
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
                    "item_id": {"type": "integer", "description": "The stone's id."},
                    "suggest_reserve": {
                        "type": "boolean",
                        "description": (
                            "True when the customer seems keen to buy, to "
                            "highlight the card's 'Reserve this stone' button."
                        ),
                    },
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
        details = {k: item[k] for k in DETAIL_FIELDS}
        details["certificates"] = [
            " ".join(filter(None, (c["lab"], c["title"], c["number"])))
            for c in database.list_certificates(item["id"])
        ]
        return json.dumps({"item": details})
    if tool_name == "show_item":
        item = database.get_item(agent_id, tool_args.get("item_id"))
        if not item:
            return json.dumps({"error": "not found"})
        if item["status"] == "sold" or item["quantity"] <= 0:
            return json.dumps({"error": "sold out - don't show or recommend it"})
        shown = shown if shown is not None else []
        if any(c["id"] == item["id"] for c in shown):
            return json.dumps({"ok": True, "note": "already shown"})
        if len(shown) >= MAX_CARDS_PER_REPLY:
            return json.dumps({"error": f"at most {MAX_CARDS_PER_REPLY} cards per reply"})
        card = stone_card(item)
        card["suggest_reserve"] = bool(tool_args.get("suggest_reserve")) and item["status"] == "available"
        shown.append(card)
        return json.dumps({"ok": True, "media_count": len(shown[-1]["media"])})
    return json.dumps({"error": f"unknown tool {tool_name}"})


TERMINAL_TOOLS = {"suggest_replies", "refer_to_partner"}
MAX_SUGGESTIONS = 3
MAX_IMAGES_PER_REPLY = 2


def _gemgenerate(agent_id, args, context, images):
    """Run the gemgenerate tool, yielding image_pending then image (or
    image_failed) events. Returns the tool result for the model."""
    pending_id = f"img-{len(images) + 1}"
    if len(images) >= MAX_IMAGES_PER_REPLY:
        return json.dumps({"error": f"at most {MAX_IMAGES_PER_REPLY} previews per reply"})
    item = database.get_item(agent_id, args.get("item_id"))
    setting, metal, style = args.get("setting"), args.get("metal"), args.get("style") or ""
    try:
        gemgenerate.check_request(item, setting, metal, style)
    except gemgenerate.GemGenerateError as exc:
        return json.dumps({"error": str(exc)})
    yield {
        "type": "image_pending",
        "id": pending_id,
        "label": gemgenerate.describe(setting, metal, style),
        "item_name": item["name"],
    }
    try:
        card, _ = gemgenerate.generate(item, setting, metal, style, context=context)
    except gemgenerate.GemGenerateError as exc:
        yield {"type": "image_failed", "id": pending_id}
        return json.dumps({"error": f"{exc}. Tell the customer kindly; don't retry."})
    images.append(card)
    yield {"type": "image", "id": pending_id, "image": card}
    return json.dumps({
        "ok": True,
        "shown": card["label"],
        "note": "The customer can see it now. Remind them it's an AI preview, not the finished piece.",
    })


def build_tools(partners: list[dict], images: bool = False):
    """The fixed tools plus the two whose options depend on the partners (and
    gemgenerate when AI previews are on)."""
    tools = list(TOOLS) + ([gemgenerate.TOOL] if images else []) + [
        {
            "type": "function",
            "function": {
                "name": "suggest_replies",
                "description": (
                    "Offer the customer 2-3 short follow-up questions they can "
                    "tap, written in their voice (e.g. 'Show me it in "
                    "daylight', 'Anything cheaper?'). Call this together with "
                    "your final message of each reply."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2-3 options, each under 8 words.",
                        }
                    },
                    "required": ["options"],
                },
            },
        }
    ]
    if partners:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "refer_to_partner",
                    "description": (
                        "Offer to hand the customer over to your partner when "
                        "what they want fits the partner's line better than "
                        "yours. The customer sees a button to continue with "
                        "the partner, who receives customer_request."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "partner_id": {"type": "string", "enum": [p["id"] for p in partners]},
                            "customer_request": {
                                "type": "string",
                                "description": (
                                    "What the customer wants, in their voice, "
                                    "e.g. 'I'm after amethyst under $30.'"
                                ),
                            },
                        },
                        "required": ["partner_id", "customer_request"],
                    },
                },
            }
        )
    return tools


def _terminal_tool(tool_name, args, partners, state):
    """suggest_replies / refer_to_partner: they only shape the UI."""
    if tool_name == "suggest_replies":
        options = [str(o).strip()[:80] for o in (args.get("options") or []) if str(o).strip()]
        state["suggestions"] = options[:MAX_SUGGESTIONS]
        return {"type": "suggestions", "options": state["suggestions"]}
    partner = next((p for p in partners if p["id"] == args.get("partner_id")), None)
    request = str(args.get("customer_request") or "").strip()[:300]
    if not partner or not request:
        return None
    state["handoff"] = {
        "to": partner["id"],
        "display_name": partner["display_name"],
        "stall_name": partner["stall_name"],
        "message": request,
    }
    return {"type": "handoff", **state["handoff"]}


def _stream_completion(client, **kwargs):
    """Yield ("text", str) as it arrives, then ("tool_calls", [...])."""
    calls = {}
    for chunk in client.chat.completions.create(stream=True, **kwargs):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if getattr(delta, "content", None):
            yield "text", delta.content
        for tc in getattr(delta, "tool_calls", None) or []:
            call = calls.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
            if tc.id:
                call["id"] = tc.id
            if tc.function and tc.function.name:
                call["name"] += tc.function.name
            if tc.function and tc.function.arguments:
                call["arguments"] += tc.function.arguments
    yield "tool_calls", [calls[i] for i in sorted(calls)]


def stream_agent(agent_id: str, message: str, history: list[dict], agent_override=None, context=None):
    """
    Run one customer turn, yielding events as they happen:
      {"type": "delta", "text"}          reply text, streamed
      {"type": "card", "card"}           a stone card (show_item)
      {"type": "image_pending", "id", "label", "item_name"}  a preview is being made
      {"type": "image", "id", "image"}   the finished preview (gemgenerate)
      {"type": "image_failed", "id"}     the preview couldn't be made
      {"type": "suggestions", "options"} tappable follow-ups
      {"type": "handoff", "to", ...}     offer to continue with the partner
      {"type": "done", "reply", "cards", "images", "suggestions", "handoff"}

    history: plain {"role", "content"} turns from the client.
    agent_override: persona/selling_rules for the admin preview; tools still
    use agent_id's real inventory.
    context: {"visitor", "ip"} of a public chat. AI previews (gemgenerate)
    are only offered when it's given, since they're limited per visitor.
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
    partners = [a for a in database.list_agents() if a["id"] != agent_id]
    images_on = context is not None and bool(limits.get_settings()["image_enabled"])
    tools = build_tools(partners, images=images_on)

    messages = [{"role": "system", "content": compose_system_prompt(agent, partners)}]
    messages.extend({"role": h["role"], "content": h["content"]} for h in history)
    messages.append({"role": "user", "content": message})

    client = _get_client()
    cards = []
    images = []
    state = {"suggestions": [], "handoff": None}
    # Models may talk alongside a tool call and then finish with an empty
    # message, so every piece of text counts toward the reply.
    segments = []

    for _ in range(8):  # search + details for a few stones
        text = ""
        tool_calls = []
        for kind, value in _stream_completion(
            client, model=model, messages=messages, tools=tools, extra_headers=_extra_headers()
        ):
            if kind == "text":
                if not text and segments:
                    yield {"type": "delta", "text": "\n\n"}
                text += value
                yield {"type": "delta", "text": value}
            else:
                tool_calls = value
        if text.strip():
            segments.append(text.strip())
        if not tool_calls:
            break

        messages.append(
            {
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc["name"] in TERMINAL_TOOLS:
                event = _terminal_tool(tc["name"], args, partners, state)
                if event:
                    yield event
                result = json.dumps({"ok": bool(event)})
            elif tc["name"] == "gemgenerate" and images_on:
                result = yield from _gemgenerate(agent_id, args, context, images)
            else:
                before = len(cards)
                result = _run_tool(agent_id, tc["name"], args, shown=cards)
                for card in cards[before:]:
                    yield {"type": "card", "card": card}
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        # suggest_replies / refer_to_partner come with the final message, so
        # there's nothing left to ask the model.
        if all(tc["name"] in TERMINAL_TOOLS for tc in tool_calls):
            break

    reply = "\n\n".join(segments)
    if not reply:
        if images:
            reply = "Here's a preview - an AI sketch, not the finished piece."
        elif cards:
            reply = "Have a look at this one below."
        elif state["handoff"]:
            reply = f"{state['handoff']['display_name']} is the one to ask about that."
        else:
            reply = "Sorry, I'm having trouble looking that up right now."
        yield {"type": "delta", "text": reply}
    yield {"type": "done", "reply": reply, "cards": cards, "images": images, **state}


def chat_with_agent(agent_id: str, message: str, history: list[dict], agent_override=None, context=None):
    """Non-streaming version of stream_agent: returns its final "done" event."""
    for event in stream_agent(agent_id, message, history, agent_override=agent_override, context=context):
        if event["type"] == "done":
            return event
    raise RuntimeError("The chat ended without a reply")
