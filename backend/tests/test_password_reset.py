"""The owner's "forgot password" switch (ADMIN_RESET_PASSWORD)."""

import auth
import database
from conftest import OWNER_EMAIL, OWNER_PASSWORD

TEMP = "temporary-pass-1"


def login(client, email, password):
    return client.post("/api/admin/login", json={"email": email, "password": password})


def switch_on(monkeypatch, email=OWNER_EMAIL, password=TEMP):
    monkeypatch.setenv("ADMIN_RESET_PASSWORD", "true")
    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", password)


def test_off_by_default(client, owner, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", OWNER_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", TEMP)
    monkeypatch.delenv("ADMIN_RESET_PASSWORD", raising=False)
    auth.reset_owner_password()
    assert login(client, OWNER_EMAIL, OWNER_PASSWORD).status_code == 200
    assert login(client, OWNER_EMAIL, TEMP).status_code == 401


def test_forgotten_owner_password_is_reset(client, owner, monkeypatch):
    # Locked out after guessing.
    for _ in range(auth.MAX_FAILED_LOGINS):
        login(client, OWNER_EMAIL, "wrong-guess-123")
    switch_on(monkeypatch, email=OWNER_EMAIL.upper())
    auth.reset_owner_password()

    assert login(client, OWNER_EMAIL, OWNER_PASSWORD).status_code == 401
    # Old logins stop working.
    assert client.get("/api/admin/me", headers=owner).status_code == 401
    res = login(client, OWNER_EMAIL, TEMP)
    assert res.status_code == 200 and res.json()["user"]["must_change_password"] is True
    token = {"Authorization": f"Bearer {res.json()['token']}"}
    # A new password must be chosen before anything else.
    assert client.get("/api/admin/agents/gem-expert/items", headers=token).status_code == 403
    changed = client.post(
        "/api/admin/me/password",
        json={"current_password": TEMP, "new_password": "brand-new-pass-1"},
        headers=token,
    )
    assert changed.status_code == 200

    # Restarting with the switch still on doesn't undo the new password.
    auth.reset_owner_password()
    assert login(client, OWNER_EMAIL, "brand-new-pass-1").status_code == 200

    # A different temporary password resets again.
    switch_on(monkeypatch, password="another-temp-2")
    auth.reset_owner_password()
    assert login(client, OWNER_EMAIL, "another-temp-2").status_code == 200


def test_reset_makes_the_account_an_owner(client, owner, staff, monkeypatch):
    switch_on(monkeypatch, email="staff@example.com")
    auth.reset_owner_password()
    user = database.get_user_by_email("staff@example.com")
    assert user["role"] == "owner" and user["must_change_password"] is True


def test_reset_creates_a_missing_owner(client, owner, monkeypatch):
    switch_on(monkeypatch, email="new-boss@example.com")
    auth.reset_owner_password()
    user = database.get_user_by_email("new-boss@example.com")
    assert user["role"] == "owner" and user["must_change_password"] is True
    assert login(client, "new-boss@example.com", TEMP).status_code == 200


def test_short_password_is_ignored(client, owner, monkeypatch):
    switch_on(monkeypatch, password="short")
    auth.reset_owner_password()
    assert login(client, OWNER_EMAIL, OWNER_PASSWORD).status_code == 200
