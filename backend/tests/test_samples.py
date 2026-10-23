import json
from pathlib import Path

import database
import samples

SAMPLE_DIR = Path(samples.__file__).parent / "sample_data"


def stone(name):
    return next(i for i in database.list_items("gem-expert") if i["name"] == name)


def test_every_starter_stone_has_sample_content():
    import agent_config

    data = json.loads((SAMPLE_DIR / "stones.json").read_text())["stones"]
    assert {s["name"] for s in data} == {i["name"] for i in agent_config.SEED_ITEMS["gem-expert"]}
    for s in data:
        assert (SAMPLE_DIR / "images" / s["image"]).is_file()
        assert s["story"].strip() and s["sales_guidance"].strip()


def test_only_owners_can_load_samples(client, staff):
    assert client.post("/api/admin/samples/load", headers=staff).status_code == 403
    assert client.get("/api/admin/samples", headers=staff).status_code == 403


def test_load_fills_gaps_and_remove_takes_it_back(client, owner, staff):
    # The shop already wrote a story for the ruby and added its own stone.
    ruby = stone("Burmese Ruby 1.02ct")
    database.update_item("gem-expert", ruby["id"], {"story": "Our own story."})
    client.post("/api/admin/agents/gem-expert/items", headers=staff, json={
        "name": "House Special", "price": 10, "quantity": 1, "status": "available",
    })

    res = client.post("/api/admin/samples/load", headers=owner).json()
    assert res["photos"] == 20 and res["stories"] == 19 and res["guidance"] == 20
    assert res["unmatched"] == ["House Special"]
    assert res["status"] == {"available": 20, "matched": 20, "with_sample_photo": 20, "with_sample_text": 20}

    ruby = stone("Burmese Ruby 1.02ct")
    assert ruby["story"] == "Our own story."  # never overwritten
    assert "unheated" in ruby["sales_guidance"].lower()

    # The photo shows on the stone page and catalogue, and is served.
    page = client.get(f"/api/stones/{ruby['id']}").json()
    [photo] = page["media"]
    assert "(sample image)" in photo["caption"] and page["can_preview"] is True
    assert client.get(photo["url"]).headers["content-type"] == "image/webp"
    tile = next(i for i in client.get("/api/catalog?limit=60").json()["items"] if i["id"] == ruby["id"])
    assert tile["image_url"] == photo["url"]

    # Loading again changes nothing.
    again = client.post("/api/admin/samples/load", headers=owner).json()
    assert (again["photos"], again["stories"], again["guidance"]) == (0, 0, 0)

    # Stones with their own photos keep them; sample photos only fill gaps.
    removed = client.post("/api/admin/samples/remove", headers=owner).json()
    assert (removed["photos"], removed["stories"], removed["guidance"]) == (20, 19, 20)
    assert client.get(photo["url"]).status_code == 404
    ruby = stone("Burmese Ruby 1.02ct")
    assert ruby["story"] == "Our own story." and ruby["sales_guidance"] == ""
    assert removed["status"]["with_sample_photo"] == 0


def test_stones_with_photos_keep_them(client, owner):
    from test_media import add_photo

    ruby = stone("Burmese Ruby 1.02ct")
    own = add_photo(client, owner, ruby["id"])
    client.post("/api/admin/samples/load", headers=owner)
    assert [m["id"] for m in database.list_media(ruby["id"])] == [own["id"]]
    client.post("/api/admin/samples/remove", headers=owner)
    assert [m["id"] for m in database.list_media(ruby["id"])] == [own["id"]]


def test_the_gem_expert_uses_the_sample_story(client, owner):
    import llm_service

    client.post("/api/admin/samples/load", headers=owner)
    ruby = stone("Burmese Ruby 1.02ct")

    details = json.loads(llm_service._run_tool("gem-expert", "get_item_details", {"item_id": ruby["id"]}))["item"]
    assert "pigeon's blood" in details["story"]
    assert details["sales_guidance"].startswith("This is a hero stone")
