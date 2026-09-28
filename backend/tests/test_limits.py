import pytest

import database
import limits
from conftest import response


def chat(client, visitor="visitor-aaaa", ip="203.0.113.5", history=None):
    headers = {"X-Forwarded-For": ip}
    if visitor:
        headers["X-Visitor-Id"] = visitor
    return client.post(
        "/api/chat",
        json={"agent_id": "siq", "message": "hi", "history": history or []},
        headers=headers,
    )


@pytest.fixture
def set_limits(client, owner):
    def apply(**values):
        res = client.put("/api/admin/settings/limits", json=values, headers=owner)
        assert res.status_code == 200, res.text
        return res.json()

    return apply


def replies(fake_llm, n):
    return fake_llm(*[response(content="Hello") for _ in range(n)])


def test_burst_limit_per_visitor(client, fake_llm, set_limits):
    set_limits(burst_limit=3, burst_window_minutes=10)
    llm = replies(fake_llm, 3)
    for _ in range(3):
        assert chat(client).status_code == 200
    res = chat(client)
    assert res.status_code == 429
    assert res.json()["detail"]["code"] == "slow_down"
    assert 0 < int(res.headers["Retry-After"]) <= 600
    assert len(llm.requests) == 3  # the blocked message never reached the model

    # Another visitor on the same IP still gets through.
    replies(fake_llm, 1)
    assert chat(client, visitor="visitor-bbbb").status_code == 200


def test_daily_limit_per_visitor_and_ip(client, fake_llm, set_limits):
    set_limits(visitor_daily_limit=2)
    replies(fake_llm, 6)  # 2 for the first visitor + 4 more on the same IP
    assert chat(client).status_code == 200
    assert chat(client).status_code == 200
    blocked = chat(client)
    assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "daily"

    # New visitor IDs from the same IP share the IP's allowance (3x = 6;
    # the blocked message above wasn't counted).
    for visitor in ("visitor-cccc", "visitor-dddd", "visitor-eeee", "visitor-ffff"):
        assert chat(client, visitor=visitor).status_code == 200
    assert chat(client, visitor="visitor-hhhh").status_code == 429
    # A different IP is unaffected.
    replies(fake_llm, 1)
    assert chat(client, visitor="visitor-gggg", ip="198.51.100.7").status_code == 200


def test_global_daily_cap(client, fake_llm, set_limits):
    set_limits(global_daily_limit=2)
    replies(fake_llm, 2)
    assert chat(client, visitor="visitor-1111", ip="198.51.100.1").status_code == 200
    assert chat(client, visitor="visitor-2222", ip="198.51.100.2").status_code == 200
    res = chat(client, visitor="visitor-3333", ip="198.51.100.3")
    assert res.status_code == 429 and res.json()["detail"]["code"] == "closed"


def test_counts_survive_restart(client, fake_llm, set_limits):
    set_limits(visitor_daily_limit=1)
    replies(fake_llm, 1)
    assert chat(client).status_code == 200
    limits.reset_memory()  # a restart clears memory, not the stored daily counts
    assert chat(client).status_code == 429


def test_invalid_visitor_id_is_ignored(client, fake_llm):
    replies(fake_llm, 1)
    assert chat(client, visitor="bad id!").status_code == 200
    assert database.count_counters(limits.today(), "v:") == 0


def test_only_recent_history_goes_to_the_model(client, fake_llm, set_limits):
    set_limits(history_messages=4)
    llm = replies(fake_llm, 1)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(10)
    ]
    res = chat(client, history=history)
    sent = [m["content"] for m in llm.requests[0]["messages"][1:]]
    assert sent == ["m6", "m7", "m8", "m9", "hi"]
    # The client still gets the whole conversation back.
    assert len(res.json()["history"]) == 12


def test_usage_and_settings_permissions(client, owner, staff, fake_llm, set_limits):
    replies(fake_llm, 2)
    chat(client, visitor="visitor-1111")
    chat(client, visitor="visitor-2222")
    usage = client.get("/api/admin/usage", headers=owner).json()
    assert usage["today"] == {"messages": 2, "visitors": 2, "images": 0}
    assert usage["last_7_days"][-1]["count"] == 2 and len(usage["last_7_days"]) == 7
    assert usage["settings"]["global_daily_limit"] == 1500

    assert client.get("/api/admin/usage", headers=staff).status_code == 403
    assert client.put(
        "/api/admin/settings/limits", json={"burst_limit": 5}, headers=staff
    ).status_code == 403
    bad = client.put("/api/admin/settings/limits", json={"burst_limit": 0}, headers=owner)
    assert bad.status_code == 400


def test_admin_preview_is_not_rate_limited(client, owner, fake_llm, set_limits):
    set_limits(global_daily_limit=1)
    replies(fake_llm, 1)
    chat(client)
    replies(fake_llm, 1)
    draft = {"display_name": "Siq", "stall_name": "Pacific Gems", "persona": "You are Siq."}
    res = client.post(
        "/api/admin/agents/siq/preview", json={"draft": draft, "message": "hi"}, headers=owner
    )
    assert res.status_code == 200


def test_prune_old_counters(client):
    database.increment_counter("2000-01-01", "global")
    database.increment_counter(limits.today(), "global")
    limits.prune_old_counters()
    assert database.get_counter("2000-01-01", "global") == 0
    assert database.get_counter(limits.today(), "global") == 1
