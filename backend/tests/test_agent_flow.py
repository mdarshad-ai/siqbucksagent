import json

import pytest
from sqlalchemy import inspect, text

import database
from conftest import response, tool_call


def sse_events(body: str):
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def ruby():
    return next(i for i in database.list_items("siq") if i["name"] == "Burmese Ruby 1.02ct")


def stream(client, message="Ruby?", agent="siq", history=None, headers=None):
    return client.post(
        "/api/chat/stream",
        json={"agent_id": agent, "message": message, "history": history or []},
        headers=headers or {},
    )


# ---------- streaming ----------

def test_stream_sends_text_cards_suggestions_then_done(client, fake_llm):
    stone = ruby()
    llm = fake_llm(
        response(content="Let me show you.", tool_calls=[tool_call("c1", "show_item", json.dumps({"item_id": stone["id"]}))]),
        response(
            content="It's unheated and vivid.",
            tool_calls=[tool_call("c2", "suggest_replies", json.dumps({"options": ["Show me in daylight", "Anything cheaper?"]}))],
        ),
    )
    res = stream(client)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    events = sse_events(res.text)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done"
    assert kinds.index("card") < kinds.index("suggestions") < kinds.index("done")

    streamed = "".join(d["text"] for k, d in events if k == "delta")
    done = events[-1][1]
    assert streamed == done["reply"] == "Let me show you.\n\nIt's unheated and vivid."
    assert done["suggestions"] == ["Show me in daylight", "Anything cheaper?"]
    last = done["history"][-1]
    assert last["cards"][0]["id"] == stone["id"] and last["suggestions"] == done["suggestions"]
    assert "handoff" not in last  # empty extras are left out of the history
    # suggest_replies arrives with the final message: no extra model call.
    assert len(llm.requests) == 2


def test_stream_errors_are_generic(client, fake_llm):
    fake_llm(RuntimeError("provider said user_secret123"))
    events = sse_events(stream(client).text)
    assert events == [("error", {"message": "The agent couldn't reply right now. Please try again."})]


def test_stream_is_rate_limited_before_starting(client, owner, fake_llm):
    client.put("/api/admin/settings/limits", json={"global_daily_limit": 1}, headers=owner)
    fake_llm(response(content="Hi"))
    assert stream(client).status_code == 200
    res = stream(client)
    assert res.status_code == 429 and res.json()["detail"]["code"] == "closed"


def test_suggestions_are_trimmed(client, fake_llm):
    options = ["  One  ", "", "Two", "Three", "Four", "x" * 200]
    fake_llm(response(content="Hi", tool_calls=[tool_call("c1", "suggest_replies", json.dumps({"options": options}))]))
    done = sse_events(stream(client).text)[-1][1]
    assert done["suggestions"] == ["One", "Two", "Three"]


# ---------- partners ----------

def test_partner_referral(client, fake_llm):
    llm = fake_llm(
        response(
            content="Amethyst is more Bucks's line.",
            tool_calls=[tool_call("c1", "refer_to_partner", json.dumps(
                {"partner_id": "bucks", "customer_request": "I'm after amethyst under $30."}))],
        )
    )
    res = client.post("/api/chat", json={"agent_id": "siq", "message": "Cheap amethyst?"}).json()
    assert res["handoff"] == {
        "to": "bucks", "display_name": "Bucks", "stall_name": "Bucks' Exchange",
        "message": "I'm after amethyst under $30.",
    }
    assert res["history"][-1]["handoff"]["to"] == "bucks"

    request = llm.requests[0]
    refer = next(t for t in request["tools"] if t["function"]["name"] == "refer_to_partner")
    assert refer["function"]["parameters"]["properties"]["partner_id"]["enum"] == ["bucks"]
    system = request["messages"][0]["content"]
    assert "Bucks (Bucks' Exchange)" in system and "Loupe Gem" in system


def test_referral_to_unknown_partner_is_ignored(client, fake_llm):
    fake_llm(response(content="Hmm.", tool_calls=[tool_call("c1", "refer_to_partner", json.dumps(
        {"partner_id": "siq", "customer_request": "x"}))]))
    res = client.post("/api/chat", json={"agent_id": "siq", "message": "?"}).json()
    assert res["handoff"] is None


# ---------- routing ----------

@pytest.mark.parametrize(
    "message, agent",
    [
        ("A cheap amethyst gift under $30", "bucks"),
        ("smoky quartz and rose quartz crystals", "bucks"),
        ("GIA certified sapphire for an engagement ring", "siq"),
        ("Something rare under $5,000", "siq"),
        ("hello", "siq"),
    ],
)
def test_route_picks_partner(client, message, agent):
    assert client.post("/api/route", json={"message": message}).json() == {"agent_id": agent}


# ---------- featured ----------

def test_featured_stones(client, staff):
    stone = ruby()
    assert client.get("/api/featured").json() == []
    body = {k: stone[k] for k in database.ITEM_EDITABLE_FIELDS if k != "featured"}
    res = client.put(f"/api/admin/agents/siq/items/{stone['id']}", json={**body, "featured": True}, headers=staff)
    assert res.json()["featured"] is True

    featured = client.get("/api/featured").json()
    assert [f["name"] for f in featured] == ["Burmese Ruby 1.02ct"]
    assert featured[0]["agent"]["display_name"] == "Siq" and featured[0]["media"] == []
    assert "sales_guidance" not in featured[0]

    database.update_item("siq", stone["id"], {"status": "sold"})
    assert client.get("/api/featured").json() == []


def test_featured_column_is_added_to_existing_databases(client):
    engine = database.get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE items DROP COLUMN featured"))
    assert "featured" not in {c["name"] for c in inspect(engine).get_columns("items")}
    database.init_db()
    assert "featured" in {c["name"] for c in inspect(engine).get_columns("items")}
    assert all(i["featured"] is False for i in database.list_items("siq"))
