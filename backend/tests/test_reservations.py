import json
from datetime import datetime, timedelta, timezone

import pytest

import database
import llm_service
import reservations
from conftest import response, tool_call


def item(name):
    return next(i for i in database.list_items("siq") + database.list_items("bucks") if i["name"] == name)


def request_hold(client, stone, visitor="visitor-aaaa", ip="203.0.113.9", **extra):
    body = {
        "agent_id": stone["agent_id"],
        "item_id": stone["id"],
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "+44 20 1234 5678",
        "note": "Can I see it on Saturday?",
        "consent": True,
        **extra,
    }
    return client.post(
        "/api/reservations", json=body, headers={"X-Visitor-Id": visitor, "X-Forwarded-For": ip}
    )


def requests_in(client, headers, group):
    return client.get(f"/api/admin/reservations?group={group}", headers=headers).json()


# ---------- customer side ----------

def test_request_is_pending_and_does_not_touch_stock(client, staff):
    ruby = item("Burmese Ruby 1.02ct")
    res = request_hold(client, ruby)
    assert res.status_code == 201 and res.json()["reference"].startswith("LG-")

    assert database.get_item("siq", ruby["id"])["status"] == "available"
    pending = requests_in(client, staff, "pending")
    assert len(pending) == 1
    r = pending[0]
    assert r["customer_name"] == "Ada Lovelace" and r["item_name"] == "Burmese Ruby 1.02ct"
    assert r["reference"] == res.json()["reference"]
    assert r["transcript"] is None  # not shared
    assert "visitor_id" not in r
    assert client.get("/api/admin/reservations/summary", headers=staff).json() == {"pending": 1}


def test_chat_is_only_attached_when_shared(client, staff):
    transcript = [
        {"role": "user", "content": "Any rubies?"},
        {"role": "assistant", "content": "The Burmese ruby."},
    ]
    request_hold(client, item("Burmese Ruby 1.02ct"), share_chat=True, transcript=transcript)
    request_hold(client, item("Tanzanite 3.20ct"), share_chat=False, transcript=transcript)
    by_stone = {r["item_name"]: r for r in requests_in(client, staff, "pending")}
    assert by_stone["Burmese Ruby 1.02ct"]["transcript"] == transcript
    assert by_stone["Tanzanite 3.20ct"]["transcript"] is None


@pytest.mark.parametrize(
    "bad", [{"consent": False}, {"email": "nope"}, {"name": "  "}, {"note": "x" * 1001}]
)
def test_request_validation(client, bad):
    assert request_hold(client, item("Burmese Ruby 1.02ct"), **bad).status_code == 422


def test_sold_or_unknown_stones_cannot_be_requested(client):
    alex = item("Alexandrite 0.62ct")
    database.update_item("siq", alex["id"], {"status": "sold", "quantity": 0})
    assert request_hold(client, alex).status_code == 409
    fake = {**alex, "id": 99999}
    assert request_hold(client, fake).status_code == 404
    # A stone can't be requested through the other dealer.
    assert request_hold(client, {**item("Burmese Ruby 1.02ct"), "agent_id": "bucks"}).status_code == 404


def test_honeypot_stores_nothing(client, staff):
    res = request_hold(client, item("Burmese Ruby 1.02ct"), website="http://spam.example")
    assert res.status_code == 201
    assert requests_in(client, staff, "pending") == []


def test_requests_are_rate_limited(client):
    ruby = item("Burmese Ruby 1.02ct")
    for _ in range(reservations.REQUESTS_PER_VISITOR_PER_DAY):
        assert request_hold(client, ruby).status_code == 201
    assert request_hold(client, ruby).status_code == 429
    # Other visitors on the same connection share a larger allowance.
    for i in range(reservations.REQUESTS_PER_IP_PER_DAY - reservations.REQUESTS_PER_VISITOR_PER_DAY):
        assert request_hold(client, ruby, visitor=f"visitor-{i:04d}").status_code == 201
    assert request_hold(client, ruby, visitor="visitor-zzzz").status_code == 429


# ---------- shop side ----------

def test_confirm_one_off_stone_marks_it_reserved(client, staff):
    ruby = item("Burmese Ruby 1.02ct")
    request_hold(client, ruby)
    request_hold(client, ruby, visitor="visitor-bbbb")
    first, second = sorted(requests_in(client, staff, "pending"), key=lambda r: r["id"])

    res = client.post(f"/api/admin/reservations/{first['id']}/confirm", json={"hold_days": 5}, headers=staff)
    assert res.status_code == 200
    held = res.json()
    assert held["status"] == "confirmed" and held["hold_kind"] == "status"
    assert held["item"]["status"] == "reserved"
    hold_until = datetime.fromisoformat(held["hold_until"])
    assert timedelta(days=4, hours=23) < hold_until - datetime.now(timezone.utc) <= timedelta(days=5)

    # The same one-off stone can't be held twice.
    clash = client.post(f"/api/admin/reservations/{second['id']}/confirm", json={}, headers=staff)
    assert clash.status_code == 409
    # Confirming twice isn't allowed either.
    assert client.post(f"/api/admin/reservations/{first['id']}/confirm", json={}, headers=staff).status_code == 409

    # Release puts it back on sale.
    released = client.post(f"/api/admin/reservations/{first['id']}/release", headers=staff).json()
    assert released["status"] == "cancelled" and released["item"]["status"] == "available"


def test_confirm_multi_quantity_stone_sets_one_aside(client, staff):
    peridot = item("Peridot 1.8ct")  # 25 in stock
    request_hold(client, peridot)
    r = requests_in(client, staff, "pending")[0]
    held = client.post(f"/api/admin/reservations/{r['id']}/confirm", json={}, headers=staff).json()
    assert held["hold_kind"] == "quantity"
    assert held["item"]["quantity"] == 24 and held["item"]["status"] == "available"

    done = client.post(f"/api/admin/reservations/{r['id']}/complete", headers=staff).json()
    assert done["status"] == "completed"
    assert done["item"]["quantity"] == 24  # the unit was already taken out


def test_complete_one_off_stone_marks_it_sold(client, staff):
    ruby = item("Burmese Ruby 1.02ct")
    request_hold(client, ruby)
    r = requests_in(client, staff, "pending")[0]
    client.post(f"/api/admin/reservations/{r['id']}/confirm", json={}, headers=staff)
    done = client.post(f"/api/admin/reservations/{r['id']}/complete", headers=staff).json()
    assert done["item"]["status"] == "sold" and done["item"]["quantity"] == 0
    assert [x["id"] for x in requests_in(client, staff, "closed")] == [r["id"]]


def test_decline_extend_and_notes(client, staff):
    ruby, tanzanite = item("Burmese Ruby 1.02ct"), item("Tanzanite 3.20ct")
    request_hold(client, ruby)
    request_hold(client, tanzanite)
    by_stone = {r["item_name"]: r for r in requests_in(client, staff, "pending")}

    declined = client.post(f"/api/admin/reservations/{by_stone['Burmese Ruby 1.02ct']['id']}/decline", headers=staff).json()
    assert declined["status"] == "declined" and declined["item"]["status"] == "available"

    tid = by_stone["Tanzanite 3.20ct"]["id"]
    held = client.post(f"/api/admin/reservations/{tid}/confirm", json={"hold_days": 2}, headers=staff).json()
    extended = client.post(f"/api/admin/reservations/{tid}/extend", json={"extra_days": 3}, headers=staff).json()
    delta = datetime.fromisoformat(extended["hold_until"]) - datetime.fromisoformat(held["hold_until"])
    assert abs(delta - timedelta(days=3)) < timedelta(seconds=5)

    noted = client.patch(f"/api/admin/reservations/{tid}", json={"admin_note": "Called, visiting Sat"}, headers=staff)
    assert noted.json()["admin_note"] == "Called, visiting Sat"
    assert noted.json()["handled_by"] == "staff@example.com"


def test_expired_holds_are_released_automatically(client, staff):
    ruby = item("Burmese Ruby 1.02ct")
    request_hold(client, ruby)
    r = requests_in(client, staff, "pending")[0]
    client.post(f"/api/admin/reservations/{r['id']}/confirm", json={"hold_days": 1}, headers=staff)
    assert database.get_item("siq", ruby["id"])["status"] == "reserved"

    database.update_reservation(r["id"], {"hold_until": datetime.now(timezone.utc) - timedelta(minutes=1)})
    reservations.sweep(force=True)

    assert database.get_item("siq", ruby["id"])["status"] == "available"
    assert database.get_reservation(r["id"])["status"] == "expired"


def test_old_closed_requests_are_purged(client, staff):
    request_hold(client, item("Burmese Ruby 1.02ct"))
    r = requests_in(client, staff, "pending")[0]
    client.post(f"/api/admin/reservations/{r['id']}/decline", headers=staff)
    database.update_reservation(r["id"], {})  # touch
    with database.get_engine().begin() as conn:
        conn.execute(
            database.reservations.update()
            .where(database.reservations.c.id == r["id"])
            .values(updated_at=datetime.now(timezone.utc) - timedelta(days=reservations.RETENTION_DAYS + 1))
        )
    reservations.sweep(force=True)
    assert database.get_reservation(r["id"]) is None


def test_admin_endpoints_need_login(client):
    assert client.get("/api/admin/reservations").status_code == 401
    assert client.post("/api/admin/reservations/1/confirm", json={}).status_code == 401


# ---------- dealers ----------

def test_show_item_can_highlight_reserve(client, fake_llm):
    ruby = item("Burmese Ruby 1.02ct")
    fake_llm(
        response(tool_calls=[tool_call("c1", "show_item", json.dumps({"item_id": ruby["id"], "suggest_reserve": True}))]),
        response(content="Use the Reserve button below."),
    )
    card = client.post("/api/chat", json={"agent_id": "siq", "message": "I want it"}).json()["cards"][0]
    assert card["suggest_reserve"] is True

    # Not for a stone that's already on hold.
    database.update_item("siq", ruby["id"], {"status": "reserved"})
    shown = []
    llm_service._run_tool("siq", "show_item", {"item_id": ruby["id"], "suggest_reserve": True}, shown)
    assert shown[0]["suggest_reserve"] is False and shown[0]["status"] == "reserved"
