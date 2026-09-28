import json

import pytest
from sqlalchemy import inspect, text

import database
import llm_service
from conftest import response, tool_call
from test_agent_flow import sse_events
from test_media import JPEG, MP4, add_photo, add_video, siq_item_id, upload

PDF = b"%PDF-1.4 fake certificate"


def by_name(name):
    return next(i for i in database.list_items("siq") + database.list_items("bucks") if i["name"] == name)


def catalog(client, **params):
    return client.get("/api/catalog", params=params).json()


# ---------- catalogue ----------

def test_catalog_lists_browsable_stones(client):
    data = catalog(client, limit=60)
    assert data["total"] == 20 and len(data["items"]) == 20
    assert "Sapphire" in data["categories"]
    entry = next(i for i in data["items"] if i["name"] == "Burmese Ruby 1.02ct")
    assert entry["code"] == f"LGS-{entry['id']:04d}"
    assert entry["agent"]["display_name"] == "Siq" and entry["image_url"] is None
    assert "sales_guidance" not in entry and "story" not in entry

    alex = by_name("Alexandrite 0.62ct")
    database.update_item("siq", alex["id"], {"status": "sold"})
    ruby = by_name("Burmese Ruby 1.02ct")
    database.update_item("siq", ruby["id"], {"status": "reserved"})
    names = [i["name"] for i in catalog(client, limit=60)["items"]]
    assert "Alexandrite 0.62ct" not in names and "Burmese Ruby 1.02ct" in names
    names = [i["name"] for i in catalog(client, limit=60, include_reserved="false")["items"]]
    assert "Burmese Ruby 1.02ct" not in names


def test_catalog_filters_sort_and_pages(client):
    assert {i["agent"]["id"] for i in catalog(client, agent="bucks", limit=60)["items"]} == {"bucks"}
    assert {i["name"] for i in catalog(client, category="sapphire")["items"]} == {
        "Padparadscha Sapphire 1.30ct", "Ceylon Blue Sapphire 2.10ct",
    }
    assert [i["name"] for i in catalog(client, q="blue sapphire")["items"]] == ["Ceylon Blue Sapphire 2.10ct"]

    prices = [i["price"] for i in catalog(client, sort="price_asc", limit=60)["items"]]
    assert prices == sorted(prices)
    prices = [i["price"] for i in catalog(client, sort="price_desc", min_price=1000, max_price=4000, limit=60)["items"]]
    assert prices == sorted(prices, reverse=True) and all(1000 <= p <= 4000 for p in prices)

    first = catalog(client, sort="price_asc", limit=5)
    second = catalog(client, sort="price_asc", limit=5, offset=5)
    assert first["total"] == 20 and len(first["items"]) == 5
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    assert client.get("/api/catalog", params={"sort": "bogus"}).status_code == 422


def test_catalog_image_is_chosen_or_first_photo(client, staff):
    item_id = siq_item_id()
    first = add_photo(client, staff, item_id)
    second = add_photo(client, staff, item_id)
    image = lambda: next(i for i in catalog(client, limit=60)["items"] if i["id"] == item_id)["image_url"]
    assert image() == first["url"]

    base = f"/api/admin/agents/siq/items/{item_id}"
    listed = client.put(f"{base}/catalog-image", json={"media_id": second["id"]}, headers=staff).json()
    assert [m["is_catalog"] for m in listed] == [False, True]
    assert image() == second["url"]

    video = add_video(client, staff, item_id)
    assert client.put(f"{base}/catalog-image", json={"media_id": video["id"]}, headers=staff).status_code == 400
    other = add_photo(client, staff, siq_item_id("Colombian Emerald 1.45ct"))
    assert client.put(f"{base}/catalog-image", json={"media_id": other["id"]}, headers=staff).status_code == 400

    # Deleting the chosen photo falls back to the first one.
    client.delete(f"{base}/media/{second['id']}", headers=staff)
    assert image() == first["url"]


def test_stock_code_can_be_set(client, staff):
    ruby = by_name("Burmese Ruby 1.02ct")
    body = {k: ruby[k] for k in database.ITEM_EDITABLE_FIELDS}
    client.put(f"/api/admin/agents/siq/items/{ruby['id']}", json={**body, "sku": "RL1803"}, headers=staff)
    assert next(i for i in catalog(client, q="RL1803")["items"])["code"] == "RL1803"


# ---------- certificates ----------

def add_certificate(client, headers, item_id, data=PDF, content_type="application/pdf", **fields):
    path = upload(client, headers, item_id, data, content_type, purpose="certificate")
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/certificates",
        json={"path": path, "content_type": content_type, "size_bytes": len(data), **fields},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_certificates(client, staff):
    item_id = siq_item_id()
    pdf = add_certificate(client, staff, item_id, title="Report", lab="GIA", number="2141438")
    scan = add_certificate(client, staff, item_id, data=JPEG, content_type="image/jpeg", lab="GRS")
    assert pdf["kind"] == "pdf" and scan["kind"] == "image"
    assert client.get(pdf["url"]).content == PDF

    base = f"/api/admin/agents/siq/items/{item_id}/certificates"
    edited = client.patch(f"{base}/{scan['id']}", json={"title": "Scan", "number": "X1"}, headers=staff).json()
    assert edited["number"] == "X1" and edited["lab"] == "GRS"  # only the fields sent change
    assert [c["lab"] for c in client.get(base, headers=staff).json()] == ["GIA", "GRS"]

    # Partners know about them.
    details = json.loads(llm_service._run_tool("siq", "get_item_details", {"item_id": item_id}))["item"]
    assert details["certificates"] == ["GIA Report 2141438", "GRS Scan X1"]

    assert client.delete(f"{base}/{pdf['id']}", headers=staff).status_code == 204
    assert client.get(pdf["url"]).status_code == 404

    # Videos aren't certificates.
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media/upload-url",
        json={"content_type": "video/mp4", "size_bytes": 10, "purpose": "certificate"}, headers=staff,
    )
    assert res.status_code == 400

    # Deleting the stone removes certificate files too.
    client.delete(f"/api/admin/agents/siq/items/{item_id}", headers=staff)
    assert client.get(scan["url"]).status_code == 404


# ---------- stone page ----------

def test_stone_page(client, staff):
    item_id = siq_item_id()
    ruby = database.get_item("siq", item_id)
    database.update_item("siq", item_id, {"story": "Cut in Mogok.", "sales_guidance": "SECRET"})
    first = add_photo(client, staff, item_id)
    chosen = add_photo(client, staff, item_id)
    client.put(f"/api/admin/agents/siq/items/{item_id}/catalog-image", json={"media_id": chosen["id"]}, headers=staff)
    add_certificate(client, staff, item_id, lab="GIA")

    page = client.get(f"/api/stones/{item_id}").json()
    assert page["name"] == ruby["name"] and page["story"] == "Cut in Mogok."
    assert "sales_guidance" not in page and "SECRET" not in json.dumps(page)
    assert [m["id"] for m in page["media"]] == [chosen["id"], first["id"]]  # catalogue photo leads
    assert page["certificates"][0]["lab"] == "GIA"
    assert page["agent"]["id"] == "siq" and page["code"].startswith("LGS-")

    database.update_item("siq", item_id, {"status": "sold"})
    assert client.get(f"/api/stones/{item_id}").status_code == 404
    assert client.get("/api/stones/99999").status_code == 404


# ---------- the partner's pitch ----------

def test_pitch_is_written_once_then_replayed(client, fake_llm):
    item_id = siq_item_id()
    llm = fake_llm(
        response(content="Let me look.", tool_calls=[tool_call("c1", "show_item", json.dumps({"item_id": item_id}))]),
        response(content="A vivid, unheated Burmese ruby.", tool_calls=[
            tool_call("c2", "suggest_replies", json.dumps({"options": ["Is it certified?"]}))]),
    )
    events = sse_events(client.post(f"/api/stones/{item_id}/pitch").text)
    kinds = [k for k, _ in events]
    assert "card" not in kinds and kinds[-1] == "done"
    done = events[-1][1]
    assert done["reply"] == "Let me look.\n\nA vivid, unheated Burmese ruby."
    assert done["history"][0]["hidden"] is True and "stone #" in done["history"][0]["content"]
    assert done["history"][1]["suggestions"] == ["Is it certified?"]
    assert "can already see its photos" in llm.requests[0]["messages"][1]["content"]

    # Second visitor: replayed from the save, no AI call at all.
    fake_llm()
    replay = sse_events(client.post(f"/api/stones/{item_id}/pitch").text)
    assert "".join(d["text"] for k, d in replay if k == "delta") == done["reply"]
    assert replay[-1][1]["suggestions"] == ["Is it certified?"]

    # Editing the stone makes the partner write a fresh pitch.
    database.update_item("siq", item_id, {"story": "New story"})
    llm = fake_llm(response(content="Fresh pitch."))
    assert sse_events(client.post(f"/api/stones/{item_id}/pitch").text)[-1][1]["reply"] == "Fresh pitch."
    assert len(llm.requests) == 1


def test_pitch_history_continues_in_chat(client, fake_llm):
    item_id = siq_item_id()
    fake_llm(response(content="A fine ruby."))
    history = sse_events(client.post(f"/api/stones/{item_id}/pitch").text)[-1][1]["history"]
    llm = fake_llm(response(content="Yes, GIA."))
    res = client.post("/api/chat", json={"agent_id": "siq", "message": "Certified?", "history": history}).json()
    sent = llm.requests[0]["messages"]
    assert sent[1]["role"] == "user" and "stone #" in sent[1]["content"]
    assert res["history"][0]["hidden"] is True


def test_new_pitches_count_toward_limits_but_saved_ones_are_free(client, owner, fake_llm):
    client.put("/api/admin/settings/limits", json={"global_daily_limit": 1}, headers=owner)
    ruby, emerald = siq_item_id(), siq_item_id("Colombian Emerald 1.45ct")
    fake_llm(response(content="Ruby pitch."))
    assert client.post(f"/api/stones/{ruby}/pitch").status_code == 200
    fake_llm()
    assert client.post(f"/api/stones/{ruby}/pitch").status_code == 200  # saved: free
    res = client.post(f"/api/stones/{emerald}/pitch")
    assert res.status_code == 429 and res.json()["detail"]["code"] == "closed"


def test_pitch_errors_are_not_saved(client, fake_llm):
    item_id = siq_item_id()
    fake_llm(RuntimeError("boom"))
    assert sse_events(client.post(f"/api/stones/{item_id}/pitch").text)[-1][0] == "error"
    assert database.get_pitch(item_id) is None


def test_new_item_columns_are_added_to_existing_databases(client):
    engine = database.get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE items DROP COLUMN sku"))
        conn.execute(text("ALTER TABLE items DROP COLUMN catalog_media_id"))
    database.init_db()
    columns = {c["name"] for c in inspect(engine).get_columns("items")}
    assert {"sku", "catalog_media_id"} <= columns
