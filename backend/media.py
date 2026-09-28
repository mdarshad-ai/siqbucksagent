"""Stone media helpers: public URLs, YouTube/Vimeo links, and chat cards."""

import re
from urllib.parse import parse_qs, urlparse

import database
from storage import get_storage

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_link(url: str):
    """Turn a YouTube or Vimeo page URL into an embeddable player URL.
    Returns (embed_url, thumbnail_url) or None if it isn't a supported link."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [p for p in parsed.path.split("/") if p]

    video_id = None
    if host == "youtu.be" and parts:
        video_id = parts[0]
    elif host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        if parts[:1] == ["watch"]:
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            video_id = parts[1]
    if video_id:
        if not _YOUTUBE_ID.match(video_id):
            return None
        return (
            f"https://www.youtube-nocookie.com/embed/{video_id}",
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        )

    if host in ("vimeo.com", "player.vimeo.com"):
        numbers = [p for p in parts if p.isdigit()]
        if not numbers:
            return None
        vid = numbers[0]
        # Unlisted videos: vimeo.com/<id>/<hash> or ?h=<hash>
        after = parts[parts.index(vid) + 1:] if vid in parts else []
        privacy = parse_qs(parsed.query).get("h", [None])[0]
        if not privacy and after and re.fullmatch(r"[0-9a-f]{6,}", after[0]):
            privacy = after[0]
        embed = f"https://player.vimeo.com/video/{vid}"
        if privacy:
            embed += f"?h={privacy}"
        return embed, None
    return None


def public_media(row: dict) -> dict:
    """What the browser needs to show one media item."""
    storage = get_storage()
    if row["kind"] == "embed":
        url, poster = row["external_url"], row["thumbnail_url"]
    else:
        url = storage.public_url(row["path"])
        poster = storage.public_url(row["poster_path"]) if row["poster_path"] else None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "url": url,
        "poster_url": poster,
        "caption": row["caption"],
    }


def admin_media(row: dict) -> dict:
    return {
        **public_media(row),
        "position": row["position"],
        "content_type": row["content_type"],
        "size_bytes": row["size_bytes"],
    }


CARD_FIELDS = (
    "id", "agent_id", "name", "category", "carat", "cut", "color", "origin", "treatment",
    "certification", "price", "quantity", "status",
)


def stone_card(item: dict) -> dict:
    """A stone card for the customer chat: public details + its media."""
    return {
        **{k: item[k] for k in CARD_FIELDS},
        "media": [public_media(m) for m in database.list_media(item["id"])],
    }


# ---------- catalogue & stone pages ----------

AGENT_FIELDS = ("id", "display_name", "stall_name", "tagline", "theme")


def stone_code(item: dict) -> str:
    """The shop's stock code, or an automatic one like "LXS-0012"."""
    return item.get("sku") or f"LX{item['agent_id'][:1].upper()}-{item['id']:04d}"


def public_certificate(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "lab": row["lab"],
        "number": row["number"],
        "url": get_storage().public_url(row["path"]),
        "kind": "pdf" if row["content_type"] == "application/pdf" else "image",
    }


def admin_certificate(row: dict) -> dict:
    return {**public_certificate(row), "content_type": row["content_type"], "size_bytes": row["size_bytes"]}


def catalog_entry(item: dict, image, agent: dict) -> dict:
    return {
        "id": item["id"],
        "code": stone_code(item),
        "name": item["name"],
        "category": item["category"],
        "carat": item["carat"],
        "price": item["price"],
        "status": item["status"],
        "image_url": get_storage().public_url(image["path"]) if image else None,
        "agent": {k: agent[k] for k in AGENT_FIELDS},
    }


def stone_page(item: dict, agent: dict) -> dict:
    """Everything the public stone page shows (never the sales guidance)."""
    media_rows = database.list_media(item["id"])
    ordered = sorted(media_rows, key=lambda m: m["id"] != item.get("catalog_media_id"))
    return {
        **database.public_item(item),
        "agent_id": item["agent_id"],
        "code": stone_code(item),
        "story": item["story"],
        "media": [public_media(m) for m in ordered],
        "certificates": [public_certificate(c) for c in database.list_certificates(item["id"])],
        "agent": {k: agent[k] for k in AGENT_FIELDS},
    }
