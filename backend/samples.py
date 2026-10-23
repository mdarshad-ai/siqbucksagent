"""
Sample content for the starter stones: an illustrated photo, a story and
private sales guidance for each (backend/sample_data/). Owners load it from
admin Settings to see the shop fully dressed, and remove it again before
going live with real details.

Loading only fills gaps: a stone that already has a photo keeps its photos,
and a story or guidance someone wrote is never replaced. Stones are matched
by name, so stones the shop added itself are left alone.
"""

import json
from functools import lru_cache
from pathlib import Path

import database
from storage import get_storage

DATA_DIR = Path(__file__).parent / "sample_data"
PATH_PREFIX = "samples/"  # storage folder for sample photos


@lru_cache(maxsize=1)
def _content():
    data = json.loads((DATA_DIR / "stones.json").read_text())
    return {s["name"].strip().lower(): s for s in data["stones"]}


def _all_items():
    for agent in database.list_agents():
        for item in database.list_items(agent["id"]):
            yield item


def _sample_for(item):
    return _content().get(item["name"].strip().lower())


def _is_sample_media(row):
    return bool(row["path"]) and row["path"].startswith(PATH_PREFIX)


def status():
    matched = photos = written = 0
    for item in _all_items():
        sample = _sample_for(item)
        if not sample:
            continue
        matched += 1
        photos += any(_is_sample_media(m) for m in database.list_media(item["id"]))
        written += item["story"] == sample["story"] or item["sales_guidance"] == sample["sales_guidance"]
    return {"available": len(_content()), "matched": matched, "with_sample_photo": photos, "with_sample_text": written}


def apply():
    """Fill in missing photos, stories and guidance. Returns what changed."""
    result = {"photos": 0, "stories": 0, "guidance": 0, "unmatched": []}
    storage = get_storage()
    for item in _all_items():
        sample = _sample_for(item)
        if not sample:
            result["unmatched"].append(item["name"])
            continue
        changes = {}
        if not (item["story"] or "").strip():
            changes["story"] = sample["story"]
            result["stories"] += 1
        if not (item["sales_guidance"] or "").strip():
            changes["sales_guidance"] = sample["sales_guidance"]
            result["guidance"] += 1
        if changes:
            database.update_item(item["agent_id"], item["id"], changes)

        if not any(m["kind"] == "image" for m in database.list_media(item["id"])):
            data = (DATA_DIR / "images" / sample["image"]).read_bytes()
            path = f"{PATH_PREFIX}{item['id']}/{sample['image']}"
            storage.put(path, data, "image/webp")
            database.create_media(item["id"], {
                "kind": "image", "path": path, "content_type": "image/webp",
                "size_bytes": len(data), "caption": f"{sample['caption']} (sample image)",
            })
            result["photos"] += 1
    return result


def remove():
    """Take out sample photos, and stories/guidance still exactly as loaded."""
    result = {"photos": 0, "stories": 0, "guidance": 0}
    paths = []
    for item in _all_items():
        for row in database.list_media(item["id"]):
            if _is_sample_media(row):
                database.delete_media(item["id"], row["id"])
                paths.append(row["path"])
                result["photos"] += 1
        sample = _sample_for(item)
        if not sample:
            continue
        changes = {}
        if item["story"] == sample["story"]:
            changes["story"] = ""
            result["stories"] += 1
        if item["sales_guidance"] == sample["sales_guidance"]:
            changes["sales_guidance"] = ""
            result["guidance"] += 1
        if changes:
            database.update_item(item["agent_id"], item["id"], changes)
    if paths:
        get_storage().delete(paths)
    return result
