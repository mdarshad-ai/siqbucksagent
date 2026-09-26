import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Uploads go to a throwaway folder (main mounts it once at import).
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="gem-media-"))
os.environ.pop("SUPABASE_URL", None)

import database  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # A fresh database per test, and a dummy key, before importing main
    # (which initialises the DB at import time). SQLite by default; set
    # TEST_DATABASE_URL to run against Postgres (its tables are wiped).
    pg_url = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg_url or f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    database.reset_engine()
    if pg_url:
        database.metadata.drop_all(database.get_engine())
    database.init_db()

    import auth

    auth._failed_logins.clear()

    from fastapi.testclient import TestClient

    import main

    yield TestClient(main.app)
    database.reset_engine()


OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "owner-password-1"


@pytest.fixture
def owner(client):
    """Headers for a logged-in owner."""
    import auth

    database.create_user(
        OWNER_EMAIL, auth.hash_password(OWNER_PASSWORD), "owner", must_change_password=False
    )
    res = client.post(
        "/api/admin/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture
def staff(client, owner):
    """Headers for a logged-in staff user who has set their own password."""
    created = client.post(
        "/api/admin/users", json={"email": "staff@example.com", "role": "staff"}, headers=owner
    ).json()
    token = client.post(
        "/api/admin/login",
        json={"email": "staff@example.com", "password": created["temp_password"]},
    ).json()["token"]
    token = client.post(
        "/api/admin/me/password",
        json={"current_password": created["temp_password"], "new_password": "staff-password-1"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLM:
    """Stands in for the OpenAI client: returns queued responses in order and
    records every request it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@pytest.fixture
def fake_llm(monkeypatch):
    import llm_service

    def install(*responses):
        llm = FakeLLM(responses)
        monkeypatch.setattr(llm_service, "_get_client", lambda: llm)
        return llm

    return install


tool_call = _tool_call
response = _response
