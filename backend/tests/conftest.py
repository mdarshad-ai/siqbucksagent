import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the app at a throwaway DB and a dummy key before importing main,
    # which seeds the DB at import time.
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "inventory.db")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    database.init_db()

    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


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
