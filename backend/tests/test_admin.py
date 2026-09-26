import json

import pytest

import auth
import database
import llm_service
from agent_config import CORE_RULES
from conftest import OWNER_EMAIL, OWNER_PASSWORD, response, tool_call

STONE = {
    "name": "Test Sapphire 1.00ct",
    "category": "Sapphire",
    "carat": 1.0,
    "cut": "Oval",
    "color": "Cornflower blue",
    "origin": "Madagascar",
    "treatment": "Unheated",
    "certification": "GIA 123456",
    "price": 1500,
    "quantity": 1,
    "status": "available",
    "description": "Bright oval.",
    "story": "Found by a family-run mine in 2019.",
    "sales_guidance": "Lead with the certificate; pairs well with the tanzanite.",
}


def login(client, email, password):
    return client.post("/api/admin/login", json={"email": email, "password": password})


# ---------- seeding ----------

def test_seed_creates_agents_and_inventory_once(client):
    assert [a["id"] for a in client.get("/api/agents").json()] == ["siq", "bucks"]
    assert len(database.list_items("siq")) == 10
    database.init_db()  # a restart must not duplicate or reset anything
    assert len(database.list_items("siq")) == 10
    assert len(database.list_agent_versions("siq")) == 1


def test_public_agents_do_not_expose_personas(client):
    agent = client.get("/api/agents").json()[0]
    assert "persona" not in agent and "selling_rules" not in agent


def test_bootstrap_owner_only_when_no_users(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "boss-password-1")
    auth.bootstrap_owner()
    assert login(client, "boss@example.com", "boss-password-1").json()["user"]["role"] == "owner"

    monkeypatch.setenv("ADMIN_EMAIL", "second@example.com")
    auth.bootstrap_owner()
    assert database.get_user_by_email("second@example.com") is None


# ---------- login ----------

def test_login_and_me(client, owner):
    me = client.get("/api/admin/me", headers=owner).json()
    assert me["email"] == OWNER_EMAIL and me["role"] == "owner"
    assert "password_hash" not in me


def test_admin_api_requires_login(client):
    assert client.get("/api/admin/agents").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/api/admin/agents", headers=bad).status_code == 401


def test_wrong_password_and_lockout(client, owner):
    for _ in range(auth.MAX_FAILED_LOGINS):
        assert login(client, OWNER_EMAIL, "wrong-password").status_code == 401
    # Locked out now, even with the right password.
    assert login(client, OWNER_EMAIL, OWNER_PASSWORD).status_code == 429


def test_new_user_must_change_temp_password(client, owner):
    created = client.post(
        "/api/admin/users", json={"email": "new@example.com"}, headers=owner
    ).json()
    assert created["user"]["role"] == "staff" and created["user"]["must_change_password"]
    token = login(client, "new@example.com", created["temp_password"]).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/admin/agents", headers=headers).status_code == 403
    assert client.get("/api/admin/me", headers=headers).status_code == 200

    short = client.post(
        "/api/admin/me/password",
        json={"current_password": created["temp_password"], "new_password": "short"},
        headers=headers,
    )
    assert short.status_code == 400

    res = client.post(
        "/api/admin/me/password",
        json={"current_password": created["temp_password"], "new_password": "a-long-password"},
        headers=headers,
    )
    assert res.status_code == 200
    new_headers = {"Authorization": f"Bearer {res.json()['token']}"}
    assert client.get("/api/admin/agents", headers=new_headers).status_code == 200
    # The token from before the change no longer works.
    assert client.get("/api/admin/me", headers=headers).status_code == 401


# ---------- roles ----------

def test_staff_cannot_manage_agents_or_users(client, staff):
    assert client.get("/api/admin/agents", headers=staff).status_code == 200
    assert client.get("/api/admin/agents/siq", headers=staff).status_code == 403
    assert client.get("/api/admin/users", headers=staff).status_code == 403
    assert client.post(
        "/api/admin/users", json={"email": "x@example.com"}, headers=staff
    ).status_code == 403


def test_owner_user_management(client, owner, staff):
    users = client.get("/api/admin/users", headers=owner).json()
    staff_id = next(u["id"] for u in users if u["email"] == "staff@example.com")
    owner_id = next(u["id"] for u in users if u["email"] == OWNER_EMAIL)

    dup = client.post("/api/admin/users", json={"email": "STAFF@example.com"}, headers=owner)
    assert dup.status_code == 409
    assert client.post(
        "/api/admin/users", json={"email": "not-an-email"}, headers=owner
    ).status_code == 422

    # Owners can't lock themselves out.
    assert client.delete(f"/api/admin/users/{owner_id}", headers=owner).status_code == 400
    assert client.patch(
        f"/api/admin/users/{owner_id}", json={"role": "staff"}, headers=owner
    ).status_code == 400

    promoted = client.patch(f"/api/admin/users/{staff_id}", json={"role": "owner"}, headers=owner)
    assert promoted.json()["role"] == "owner"

    reset = client.post(f"/api/admin/users/{staff_id}/reset-password", headers=owner).json()
    assert reset["user"]["must_change_password"]
    # Reset logs the user out everywhere.
    assert client.get("/api/admin/me", headers=staff).status_code == 401
    assert login(client, "staff@example.com", reset["temp_password"]).status_code == 200

    assert client.delete(f"/api/admin/users/{staff_id}", headers=owner).status_code == 204
    assert database.get_user(staff_id) is None


# ---------- inventory ----------

def test_staff_can_manage_inventory(client, staff):
    created = client.post("/api/admin/agents/siq/items", json=STONE, headers=staff)
    assert created.status_code == 201
    item = created.json()
    assert item["story"] == STONE["story"] and item["sales_guidance"] == STONE["sales_guidance"]

    updated = client.put(
        f"/api/admin/agents/siq/items/{item['id']}",
        json={**STONE, "quantity": 0, "status": "sold"},
        headers=staff,
    ).json()
    assert updated["quantity"] == 0 and updated["status"] == "sold"

    # An item belongs to one agent: Bucks' URL can't touch Siq's stone.
    assert client.delete(
        f"/api/admin/agents/bucks/items/{item['id']}", headers=staff
    ).status_code == 404
    assert client.delete(
        f"/api/admin/agents/siq/items/{item['id']}", headers=staff
    ).status_code == 204
    assert database.get_item("siq", item["id"]) is None


@pytest.mark.parametrize(
    "bad", [{"price": -1}, {"quantity": -2}, {"status": "lost"}, {"name": "  "}, {"carat": -0.5}]
)
def test_item_validation(client, staff, bad):
    res = client.post("/api/admin/agents/siq/items", json={**STONE, **bad}, headers=staff)
    assert res.status_code == 422


def test_public_inventory_hides_private_notes(client, staff):
    client.post("/api/admin/agents/siq/items", json=STONE, headers=staff)
    public = client.get("/api/agents/siq/inventory").json()
    stone = next(i for i in public if i["name"] == STONE["name"])
    assert "sales_guidance" not in stone and "story" not in stone


def test_agent_tools_read_stone_memory(client, staff, fake_llm):
    item = client.post("/api/admin/agents/siq/items", json=STONE, headers=staff).json()

    search = json.loads(llm_service._run_tool("siq", "search_inventory", {"query": "sapphires"}))
    names = [r["name"] for r in search["results"]]
    assert STONE["name"] in names and "Ceylon Blue Sapphire 2.10ct" in names
    assert all("sales_guidance" not in r for r in search["results"])

    details = json.loads(
        llm_service._run_tool("siq", "get_item_details", {"item_id": item["id"]})
    )["item"]
    assert details["story"] == STONE["story"]
    assert details["sales_guidance"] == STONE["sales_guidance"]

    # Bucks can't read Siq's stone.
    other = json.loads(llm_service._run_tool("bucks", "get_item_details", {"item_id": item["id"]}))
    assert other == {"error": "not found"}


# ---------- personas ----------

def agent_fields(**overrides):
    fields = {
        "display_name": "Siq",
        "stall_name": "Pacific Gems",
        "tagline": "Certified fine gemstones.",
        "persona": "You are Siq, cheerful and chatty.",
        "selling_rules": "- Always mention the certificate.",
    }
    return {**fields, **overrides}


def test_publish_persona_creates_version_and_changes_prompt(client, owner, fake_llm):
    res = client.put(
        "/api/admin/agents/siq", json={**agent_fields(), "note": "More cheerful"}, headers=owner
    )
    assert res.status_code == 200
    assert res.json()["core_rules"] == CORE_RULES

    versions = client.get("/api/admin/agents/siq/versions", headers=owner).json()
    assert [v["note"] for v in versions] == ["More cheerful", "Initial version"]
    assert versions[0]["created_by"] == OWNER_EMAIL

    llm = fake_llm(response(content="Hello!"))
    client.post("/api/chat", json={"agent_id": "siq", "message": "hi"})
    system = llm.requests[0]["messages"][0]["content"]
    assert system.startswith("You are Siq, cheerful and chatty.")
    assert "Always mention the certificate." in system
    assert system.endswith(CORE_RULES)  # locked rules always come last


def test_persona_validation(client, owner):
    res = client.put("/api/admin/agents/siq", json=agent_fields(persona="   "), headers=owner)
    assert res.status_code == 422
    assert client.put(
        "/api/admin/agents/nobody", json=agent_fields(), headers=owner
    ).status_code == 404


def test_preview_uses_draft_without_publishing(client, owner, fake_llm):
    llm = fake_llm(
        response(tool_calls=[tool_call("c1", "search_inventory", '{"query": "ruby"}')]),
        response(content="Draft reply"),
    )
    res = client.post(
        "/api/admin/agents/siq/preview",
        json={"draft": agent_fields(persona="You are DRAFT Siq."), "message": "Rubies?"},
        headers=owner,
    )
    assert res.json()["reply"] == "Draft reply"
    assert llm.requests[0]["messages"][0]["content"].startswith("You are DRAFT Siq.")
    # Tools still use Siq's real inventory.
    assert "Burmese Ruby" in llm.requests[1]["messages"][-1]["content"]
    # Nothing was published.
    assert database.get_agent("siq")["persona"].startswith("You are Siq, the specialist")
    assert len(database.list_agent_versions("siq")) == 1


def test_old_default_theme_is_moved_to_the_new_default(client):
    import json

    from sqlalchemy import update

    from agent_config import DEFAULT_AGENTS, PREVIOUS_THEMES

    old = PREVIOUS_THEMES["bucks"][0]
    with database.get_engine().begin() as conn:
        conn.execute(update(database.agents).where(database.agents.c.id == "bucks").values(theme=json.dumps(old)))
    database.init_db()
    assert database.get_agent("bucks")["theme"] == DEFAULT_AGENTS["bucks"]["theme"]

    # A theme someone customised is left alone.
    custom = {"accent": "#123456", "accent_dim": "#000000", "glow": "#abcdef"}
    with database.get_engine().begin() as conn:
        conn.execute(update(database.agents).where(database.agents.c.id == "bucks").values(theme=json.dumps(custom)))
    database.init_db()
    assert database.get_agent("bucks")["theme"] == custom
