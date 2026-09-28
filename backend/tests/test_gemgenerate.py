import base64
import json
from types import SimpleNamespace

import pytest

import database
import gemgenerate
import limits
import storage
from conftest import response, tool_call
from test_agent_flow import sse_events, stream

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg" * 10
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png" * 10
VISITOR = {"X-Visitor-Id": "visitor-aaaa-1111"}


def ruby():
    return next(i for i in database.list_items("siq") if i["name"] == "Burmese Ruby 1.02ct")


def add_photo(item):
    path = f"items/{item['id']}/photo.jpg"
    storage.get_storage().put(path, JPEG, "image/jpeg")
    return database.create_media(item["id"], {
        "kind": "image", "path": path, "content_type": "image/jpeg", "size_bytes": len(JPEG), "caption": "",
    })


@pytest.fixture
def image_model(monkeypatch):
    """Stands in for the image model; records each call."""
    calls = []

    def fake(prompt, reference_url, model):
        calls.append({"prompt": prompt, "reference": reference_url, "model": model})
        return PNG, "image/png"

    monkeypatch.setattr(gemgenerate, "call_image_model", fake)
    return calls


def ask_for_ring(item, **extra):
    args = {"item_id": item["id"], "setting": "ring", "metal": "yellow_gold", **extra}
    return [
        response(content="Let me sketch that.", tool_calls=[tool_call("g1", "gemgenerate", json.dumps(args))]),
        response(content="Here it is in yellow gold - an AI preview, of course."),
    ]


def test_preview_streams_into_the_chat(client, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    llm = fake_llm(*ask_for_ring(stone, style="halo"))
    events = sse_events(stream(client, "How would it look in a ring?", headers=VISITOR).text)
    kinds = [k for k, _ in events]
    assert kinds.index("image_pending") < kinds.index("image") < kinds.index("done")

    pending = next(d for k, d in events if k == "image_pending")
    image = next(d for k, d in events if k == "image")
    assert pending["id"] == image["id"] and pending["label"] == "Halo ring in yellow gold"
    card = image["image"]
    assert card["item_id"] == stone["id"] and card["label"] == "Halo ring in yellow gold"
    assert client.get(card["url"]).content == PNG

    done = events[-1][1]
    assert done["images"] == [card] and done["history"][-1]["images"] == [card]

    # The model got the real photo and a prompt built from the stone.
    [call] = image_model
    assert call["reference"] == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    assert "1.02 ct" in call["prompt"] and "yellow gold" in call["prompt"] and "halo" in call["prompt"]
    tool_names = [t["function"]["name"] for t in llm.requests[0]["tools"]]
    assert "gemgenerate" in tool_names
    result = json.loads(llm.requests[1]["messages"][-1]["content"])
    assert result["ok"] and "AI preview" in result["note"]
    assert database.get_counter(limits.today(), "img") == 1


def test_same_preview_is_reused_for_free(client, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    fake_llm(*ask_for_ring(stone), *ask_for_ring(stone))
    first = sse_events(stream(client, "Ring?", headers=VISITOR).text)[-1][1]["images"][0]
    second = sse_events(stream(client, "Ring?", headers={"X-Visitor-Id": "someone-else-22"}).text)[-1][1]["images"][0]
    assert first == second
    assert len(image_model) == 1
    assert database.get_counter(limits.today(), "img") == 1


def test_visitor_limit_stops_new_previews(client, owner, fake_llm, image_model):
    client.put("/api/admin/settings/limits", json={"image_visitor_daily_limit": 1}, headers=owner)
    stone = ruby()
    add_photo(stone)
    llm = fake_llm(*ask_for_ring(stone), *ask_for_ring(stone, metal="platinum"))
    stream(client, "Ring?", headers=VISITOR)
    events = sse_events(stream(client, "Platinum?", headers=VISITOR).text)
    kinds = [k for k, _ in events]
    assert "image_failed" in kinds and "image" not in kinds
    assert events[-1][1]["images"] == []
    result = json.loads(llm.requests[-1]["messages"][-1]["content"])
    assert "previews for today" in result["error"]
    assert len(image_model) == 1


def test_global_limit(client, owner, fake_llm, image_model):
    client.put("/api/admin/settings/limits", json={"image_global_daily_limit": 1}, headers=owner)
    stone = ruby()
    add_photo(stone)
    fake_llm(*ask_for_ring(stone), *ask_for_ring(stone, metal="platinum"))
    stream(client, "Ring?", headers=VISITOR)
    events = sse_events(stream(client, "Platinum?", headers={"X-Visitor-Id": "someone-else-22"}).text)
    assert "image_failed" in [k for k, _ in events]
    assert len(image_model) == 1


def test_switched_off(client, owner, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    assert client.get(f"/api/stones/{stone['id']}").json()["can_preview"] is True
    client.put("/api/admin/settings/limits", json={"image_enabled": 0}, headers=owner)
    llm = fake_llm(response(content="Rubies are lovely."))
    stream(client, "Ring?", headers=VISITOR)
    assert "gemgenerate" not in [t["function"]["name"] for t in llm.requests[0]["tools"]]
    assert client.get(f"/api/stones/{stone['id']}").json()["can_preview"] is False


def test_stone_without_photo(client, fake_llm, image_model):
    stone = ruby()
    assert client.get(f"/api/stones/{stone['id']}").json()["can_preview"] is False
    llm = fake_llm(*ask_for_ring(stone))
    events = sse_events(stream(client, "Ring?", headers=VISITOR).text)
    assert not {"image_pending", "image", "image_failed"} & {k for k, _ in events}
    assert "no photo" in json.loads(llm.requests[1]["messages"][-1]["content"])["error"]
    assert image_model == []


def test_bad_arguments_and_other_partners_stones(client, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    llm = fake_llm(*ask_for_ring(stone, metal="copper"))
    stream(client, "Ring?", headers=VISITOR)
    assert "unknown setting" in json.loads(llm.requests[1]["messages"][-1]["content"])["error"]
    # Bucks can't make previews of Siq's stones.
    llm = fake_llm(*ask_for_ring(stone))
    stream(client, "Ring?", agent="bucks", headers=VISITOR)
    assert "not found" in json.loads(llm.requests[1]["messages"][-1]["content"])["error"]
    assert image_model == []


def test_image_model_failure_is_reported_kindly(client, fake_llm, monkeypatch):
    stone = ruby()
    add_photo(stone)

    def broken(*args):
        raise RuntimeError("provider said secret-123")

    monkeypatch.setattr(gemgenerate, "call_image_model", broken)
    llm = fake_llm(*ask_for_ring(stone))
    res = stream(client, "Ring?", headers=VISITOR)
    assert "secret-123" not in res.text
    assert "image_failed" in [k for k, _ in sse_events(res.text)]
    assert "couldn't be made" in json.loads(llm.requests[1]["messages"][-1]["content"])["error"]
    # The failed attempt doesn't use up the customer's previews.
    assert database.get_counter(limits.today(), "img") == 0
    assert database.get_counter(limits.today(), "img-v:visitor-aaaa-1111") == 0


def test_not_offered_in_stone_pitch_or_admin_preview(client, owner, fake_llm):
    stone = ruby()
    llm = fake_llm(response(content="A fine ruby."), response(content="Hello."))
    client.post(f"/api/stones/{stone['id']}/pitch")
    client.post("/api/admin/agents/siq/preview", json={"message": "Hi", "persona": "x", "selling_rules": "y"}, headers=owner)
    for request in llm.requests:
        assert "gemgenerate" not in [t["function"]["name"] for t in request["tools"]]


def test_deleting_a_stone_removes_its_previews(client, staff, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    fake_llm(*ask_for_ring(stone))
    card = sse_events(stream(client, "Ring?", headers=VISITOR).text)[-1][1]["images"][0]
    assert client.get(card["url"]).status_code == 200
    client.delete(f"/api/admin/agents/siq/items/{stone['id']}", headers=staff)
    assert client.get(card["url"]).status_code == 404
    assert database.count_generated() == 0


# ---------- admin ----------

def test_admin_model_choice_and_tester(client, owner, staff, image_model):
    status = client.get("/api/admin/gemgenerate", headers=owner).json()
    assert status["model"] == gemgenerate.DEFAULT_IMAGE_MODEL and status["saved_previews"] == 0
    assert client.get("/api/admin/gemgenerate", headers=staff).status_code == 403

    bad = client.put("/api/admin/gemgenerate/model", json={"model": "not a model"}, headers=owner)
    assert bad.status_code == 400
    res = client.put("/api/admin/gemgenerate/model", json={"model": "qwen/qwen-image-3"}, headers=owner)
    assert res.json()["model"] == "qwen/qwen-image-3" == gemgenerate.current_model()

    stone = ruby()
    body = {"agent_id": "siq", "item_id": stone["id"], "setting": "pendant", "metal": "platinum",
            "model": "google/gemini-3.1-flash-image"}
    no_photo = client.post("/api/admin/gemgenerate/test", json=body, headers=owner)
    assert no_photo.status_code == 400 and "no photo" in no_photo.json()["detail"]

    add_photo(stone)
    res = client.post("/api/admin/gemgenerate/test", json=body, headers=owner)
    assert res.status_code == 200
    assert res.json()["image"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert res.json()["label"] == "Pendant in platinum"
    assert image_model[-1]["model"] == "google/gemini-3.1-flash-image"
    assert database.count_generated() == 0  # tests aren't saved or shown
    assert client.post("/api/admin/gemgenerate/test", json=body, headers=staff).status_code == 403


def test_usage_counts_previews(client, owner, fake_llm, image_model):
    stone = ruby()
    add_photo(stone)
    fake_llm(*ask_for_ring(stone))
    stream(client, "Ring?", headers=VISITOR)
    assert client.get("/api/admin/usage", headers=owner).json()["today"]["images"] == 1


# ---------- the image model call ----------

class FakeImageClient:
    def __init__(self, message):
        self.message = message
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def with_options(self, **kwargs):
        self.options = kwargs
        return self

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        msg = SimpleNamespace(model_dump=lambda: self.message)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.mark.parametrize("model, modalities", [
    ("google/gemini-3.1-flash-lite-image", ["image", "text"]),
    ("qwen/qwen-image-3", ["image"]),
])
def test_call_image_model_reads_the_image(monkeypatch, model, modalities):
    import llm_service

    data_url = "data:image/png;base64," + base64.b64encode(PNG).decode()
    fake = FakeImageClient({"content": "Here you go", "images": [{"type": "image_url", "image_url": {"url": data_url}}]})
    monkeypatch.setattr(llm_service, "_get_client", lambda: fake)
    assert gemgenerate.call_image_model("prompt", "data:image/jpeg;base64,xx", model) == (PNG, "image/png")
    sent = fake.requests[0]
    assert fake.options == {"timeout": gemgenerate.IMAGE_TIMEOUT_SECONDS, "max_retries": 0}
    assert sent["model"] == model and sent["extra_body"]["modalities"] == modalities
    assert sent["messages"][0]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,xx"


def test_call_image_model_without_image(monkeypatch):
    import llm_service

    monkeypatch.setattr(llm_service, "_get_client", lambda: FakeImageClient({"content": "Sorry, I can't."}))
    with pytest.raises(gemgenerate.GemGenerateError):
        gemgenerate.call_image_model("prompt", "data:image/jpeg;base64,xx", "qwen/qwen-image-3")
