import json

import pytest

import database
import llm_service
import storage
from conftest import response, tool_call
from media import parse_video_link

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg" * 10
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"fake-video" * 10


def siq_item_id(name="Burmese Ruby 1.02ct"):
    return next(i["id"] for i in database.list_items("siq") if i["name"] == name)


def upload(client, headers, item_id, data, content_type, purpose="media"):
    """Do the browser's two steps: get an upload URL, then PUT the bytes."""
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media/upload-url",
        json={"content_type": content_type, "size_bytes": len(data), "purpose": purpose},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    target = res.json()
    put = client.put(target["url"], content=data, headers=target["headers"])
    assert put.status_code == 200, put.text
    return target["path"]


def add_photo(client, headers, item_id, caption=""):
    path = upload(client, headers, item_id, JPEG, "image/jpeg")
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media",
        json={"path": path, "content_type": "image/jpeg", "size_bytes": len(JPEG), "caption": caption},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def add_video(client, headers, item_id):
    path = upload(client, headers, item_id, MP4, "video/mp4")
    poster = upload(client, headers, item_id, JPEG, "image/jpeg", purpose="poster")
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media",
        json={"path": path, "poster_path": poster, "content_type": "video/mp4", "size_bytes": len(MP4)},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------- uploads ----------

def test_photo_upload_is_stored_and_served(client, staff):
    item_id = siq_item_id()
    photo = add_photo(client, staff, item_id, caption="Daylight")
    assert photo["kind"] == "image" and photo["caption"] == "Daylight"
    assert client.get(photo["url"]).content == JPEG

    listed = client.get(f"/api/admin/agents/siq/items/{item_id}/media", headers=staff).json()
    assert [m["id"] for m in listed] == [photo["id"]]
    counts = {i["id"]: i["media_count"] for i in client.get("/api/admin/agents/siq/items", headers=staff).json()}
    assert counts[item_id] == 1


def test_video_upload_with_still_frame(client, staff):
    video = add_video(client, staff, siq_item_id())
    assert video["kind"] == "video"
    assert client.get(video["url"]).content == MP4
    assert client.get(video["poster_url"]).content == JPEG


@pytest.mark.parametrize(
    "body, message",
    [
        ({"content_type": "application/pdf", "size_bytes": 10}, "Unsupported"),
        ({"content_type": "image/jpeg", "size_bytes": storage.MAX_UPLOAD_BYTES + 1}, "50 MB"),
        ({"content_type": "video/mp4", "size_bytes": 10, "purpose": "poster"}, "Unsupported"),
    ],
)
def test_upload_url_rejects_bad_files(client, staff, body, message):
    res = client.post(
        f"/api/admin/agents/siq/items/{siq_item_id()}/media/upload-url", json=body, headers=staff
    )
    assert res.status_code == 400 and message in res.json()["detail"]


def test_upload_needs_login_and_valid_token(client):
    res = client.post(
        f"/api/admin/agents/siq/items/{siq_item_id()}/media/upload-url",
        json={"content_type": "image/jpeg", "size_bytes": 10},
    )
    assert res.status_code == 401
    assert client.put("/api/admin/local-upload?token=forged", content=JPEG).status_code == 400


def test_media_must_be_uploaded_for_that_stone(client, staff):
    ruby, emerald = siq_item_id(), siq_item_id("Colombian Emerald 1.45ct")
    ruby_path = upload(client, staff, ruby, JPEG, "image/jpeg")
    body = {"content_type": "image/jpeg", "size_bytes": len(JPEG)}

    # Another stone's file
    res = client.post(
        f"/api/admin/agents/siq/items/{emerald}/media", json={**body, "path": ruby_path}, headers=staff
    )
    assert res.status_code == 400
    # A path that was never uploaded
    res = client.post(
        f"/api/admin/agents/siq/items/{ruby}/media",
        json={**body, "path": f"items/{ruby}/missing.jpg"}, headers=staff,
    )
    assert res.status_code == 400
    # Stones are per agent: Bucks' URL can't reach Siq's stone.
    res = client.get(f"/api/admin/agents/bucks/items/{ruby}/media", headers=staff)
    assert res.status_code == 404


# ---------- video links ----------

@pytest.mark.parametrize(
    "url, embed",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        ("https://vimeo.com/76979871", "https://player.vimeo.com/video/76979871"),
        ("https://vimeo.com/76979871/abc123def0", "https://player.vimeo.com/video/76979871?h=abc123def0"),
    ],
)
def test_parse_video_links(url, embed):
    assert parse_video_link(url)[0] == embed


@pytest.mark.parametrize(
    "url",
    ["https://example.com/video.mp4", "javascript:alert(1)", "https://youtube.com/watch?v=bad", "not a url"],
)
def test_rejects_other_links(url):
    assert parse_video_link(url) is None


def test_add_video_link(client, staff):
    item_id = siq_item_id()
    res = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media/link",
        json={"url": "https://youtu.be/dQw4w9WgXcQ", "caption": "Under a loupe"},
        headers=staff,
    )
    assert res.status_code == 201
    assert res.json()["kind"] == "embed"
    assert res.json()["poster_url"].startswith("https://i.ytimg.com/")
    bad = client.post(
        f"/api/admin/agents/siq/items/{item_id}/media/link",
        json={"url": "https://example.com/x"}, headers=staff,
    )
    assert bad.status_code == 400


# ---------- editing ----------

def test_reorder_caption_and_replace_still_frame(client, staff):
    item_id = siq_item_id()
    photo = add_photo(client, staff, item_id)
    video = add_video(client, staff, item_id)
    base = f"/api/admin/agents/siq/items/{item_id}/media"

    ordered = client.put(f"{base}/order", json={"ids": [video["id"], photo["id"]]}, headers=staff)
    assert [m["id"] for m in ordered.json()] == [video["id"], photo["id"]]
    assert client.put(f"{base}/order", json={"ids": [photo["id"]]}, headers=staff).status_code == 400

    captioned = client.patch(f"{base}/{photo['id']}", json={"caption": "Side view"}, headers=staff)
    assert captioned.json()["caption"] == "Side view"

    old_poster = client.get(video["poster_url"])
    assert old_poster.status_code == 200
    new_poster = upload(client, staff, item_id, JPEG + b"v2", "image/jpeg", purpose="poster")
    updated = client.patch(f"{base}/{video['id']}", json={"poster_path": new_poster}, headers=staff).json()
    assert client.get(updated["poster_url"]).content == JPEG + b"v2"
    # The old still frame file is removed.
    assert client.get(video["poster_url"]).status_code == 404


def test_deleting_media_and_stones_removes_files(client, staff):
    item_id = siq_item_id()
    photo = add_photo(client, staff, item_id)
    video = add_video(client, staff, item_id)
    base = f"/api/admin/agents/siq/items/{item_id}"

    assert client.delete(f"{base}/media/{photo['id']}", headers=staff).status_code == 204
    assert client.get(photo["url"]).status_code == 404

    assert client.delete(base, headers=staff).status_code == 204
    assert client.get(video["url"]).status_code == 404
    assert client.get(video["poster_url"]).status_code == 404
    assert database.list_media(item_id) == []


# ---------- stone cards in chat ----------

def test_show_item_adds_cards_to_the_reply(client, staff, fake_llm):
    item_id = siq_item_id()
    photo = add_photo(client, staff, item_id, caption="Daylight")
    llm = fake_llm(
        response(tool_calls=[tool_call("c1", "show_item", json.dumps({"item_id": item_id}))]),
        response(content="Have a look at this ruby."),
    )

    res = client.post("/api/chat", json={"agent_id": "siq", "message": "Show me a ruby"}).json()

    card = res["cards"][0]
    assert card["name"] == "Burmese Ruby 1.02ct" and card["price"] == 4100
    assert card["media"] == [
        {"id": photo["id"], "kind": "image", "url": photo["url"], "poster_url": None, "caption": "Daylight"}
    ]
    assert "sales_guidance" not in card and "story" not in card
    assert res["history"][-1]["cards"] == res["cards"]

    # Cards are display-only: the next turn doesn't send them to the model.
    llm = fake_llm(response(content="It's unheated."))
    client.post(
        "/api/chat", json={"agent_id": "siq", "message": "Heated?", "history": res["history"]}
    )
    assert all("cards" not in m for m in llm.requests[0]["messages"])


def test_show_item_rules(client, staff):
    shown = []
    sold = siq_item_id("Alexandrite 0.62ct")
    database.update_item("siq", sold, {"status": "sold"})

    result = json.loads(llm_service._run_tool("siq", "show_item", {"item_id": sold}, shown))
    assert "sold out" in result["error"] and shown == []

    bucks_item = database.list_items("bucks")[0]["id"]
    assert json.loads(llm_service._run_tool("siq", "show_item", {"item_id": bucks_item}, shown)) == {
        "error": "not found"
    }

    ids = [i["id"] for i in database.list_items("siq") if i["id"] != sold][:4]
    for item_id in ids[:3]:
        assert json.loads(llm_service._run_tool("siq", "show_item", {"item_id": item_id}, shown))["ok"]
    # Showing the same stone twice doesn't duplicate it; a 4th is refused.
    assert json.loads(llm_service._run_tool("siq", "show_item", {"item_id": ids[0]}, shown))["ok"]
    assert "at most" in json.loads(
        llm_service._run_tool("siq", "show_item", {"item_id": ids[3]}, shown)
    )["error"]
    assert [c["id"] for c in shown] == ids[:3]


@pytest.mark.parametrize(
    "url",
    [
        "https://abcdefgh.supabase.co",
        "https://abcdefgh.supabase.co/",
        "https://abcdefgh.supabase.co/rest/v1",
        "https://abcdefgh.supabase.co/rest/v1/",
        " https://abcdefgh.supabase.co/storage/v1 ",
    ],
)
def test_supabase_url_is_reduced_to_project_origin(url):
    store = storage.SupabaseStorage(url, "sb_secret_x", "stone-media")
    assert store.api == "https://abcdefgh.supabase.co/storage/v1"
    assert store.public_url("items/1/a.jpg") == (
        "https://abcdefgh.supabase.co/storage/v1/object/public/stone-media/items/1/a.jpg"
    )
