"""Moving an existing two-partner shop (Siq and Bucks) to the one Gem Expert."""

import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select

import agent_config
import database

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
SIQ = {
    "display_name": "Siq", "stall_name": "Pacific Gems", "tagline": "Certified fine gemstones.",
    "persona": "You are Siq, the specialist.", "selling_rules": "- Be precise.",
}
RED = {"accent": "#C4472B", "accent_dim": "#6E2418", "glow": "#FFB199"}


@pytest.fixture
def old_shop(tmp_path, monkeypatch):
    """A database as it was before the merge: two partners and their stock."""
    pg_url = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg_url or f"sqlite:///{tmp_path / 'old.db'}")
    database.reset_engine()
    engine = database.get_engine()
    if pg_url:
        database.metadata.drop_all(engine)
    database.metadata.create_all(engine)

    def build(bucks_fields=None):
        bucks = {**{k: v for k, v in agent_config.LEGACY_BUCKS.items()}, **(bucks_fields or {})}
        with engine.begin() as conn:
            for agent_id, fields in (("siq", SIQ), ("bucks", bucks)):
                conn.execute(insert(database.agents).values(
                    id=agent_id, theme=json.dumps(RED), updated_at=NOW, updated_by="seed", **fields))
                conn.execute(insert(database.agent_versions).values(
                    agent_id=agent_id, note="Initial version", created_at=NOW, created_by="seed", **fields))
            ids = {}
            for agent_id, name, sku in (
                ("siq", "Burmese Ruby", ""), ("siq", "Blue Sapphire", "RB-9"), ("bucks", "Amethyst Point", ""),
            ):
                ids[name] = conn.execute(insert(database.items).values(
                    agent_id=agent_id, name=name, sku=sku, price=100, quantity=1, status="available",
                    story="", sales_guidance="", created_at=NOW, updated_at=NOW,
                )).inserted_primary_key[0]
            conn.execute(insert(database.reservations).values(
                item_id=ids["Burmese Ruby"], agent_id="siq", item_name="Burmese Ruby", item_price=100,
                customer_name="Ada", email="ada@example.com", status="pending", created_at=NOW, updated_at=NOW,
            ))
        return ids

    yield build
    database.reset_engine()


def test_partners_merge_into_the_gem_expert(old_shop):
    ids = old_shop()
    database.init_db()

    [expert] = database.list_agents()
    defaults = agent_config.DEFAULT_AGENTS["gem-expert"]
    assert expert["id"] == "gem-expert"
    # Bucks's untouched defaults become the Gem Expert's, in Bucks's green.
    for key in database.AGENT_EDITABLE_FIELDS:
        assert expert[key] == defaults[key]
    assert expert["theme"] == defaults["theme"]

    # Every stone moved, and kept the stock code customers have seen.
    stones = {i["name"]: i for i in database.list_items("gem-expert")}
    assert set(stones) == {"Burmese Ruby", "Blue Sapphire", "Amethyst Point"}
    assert stones["Burmese Ruby"]["sku"] == f"LXS-{ids['Burmese Ruby']:04d}"
    assert stones["Amethyst Point"]["sku"] == f"LXB-{ids['Amethyst Point']:04d}"
    assert stones["Blue Sapphire"]["sku"] == "RB-9"  # a code set by hand stays

    # Reservations follow their stones.
    [request] = database.list_reservations()
    assert request["agent_id"] == "gem-expert"

    # Persona history is kept, Siq's labelled, with a note for the merge.
    notes = [v["note"] for v in database.list_agent_versions("gem-expert")]
    assert notes[0] == "Siq and Bucks merged into Gem Expert"
    assert set(notes[1:]) == {"Initial version", "Siq: Initial version"}

    # Restarting changes nothing.
    database.init_db()
    assert [a["id"] for a in database.list_agents()] == ["gem-expert"]
    assert len(database.list_items("gem-expert")) == 3
    assert len(database.list_agent_versions("gem-expert")) == 3
    with database.get_engine().connect() as conn:
        assert conn.execute(select(database.items.c.agent_id).distinct()).scalars().all() == ["gem-expert"]


def test_owner_edits_to_bucks_are_kept(old_shop):
    old_shop({
        "tagline": "Bargains, honestly.",
        "persona": "You are Bucks, friendly and fair. Bucks' customers come back.",
        "selling_rules": "- Bucks always mentions free cleaning.",
    })
    database.init_db()
    expert = database.get_agent("gem-expert")
    assert expert["display_name"] == "Gem Expert" and expert["stall_name"] == "Luxuria Gems"
    assert expert["tagline"] == "Bargains, honestly."
    assert expert["persona"] == "You are the Gem Expert, friendly and fair. The Gem Expert's customers come back."
    assert expert["selling_rules"] == "- The Gem Expert always mentions free cleaning."
