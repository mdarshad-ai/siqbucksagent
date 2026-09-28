"""
Chat rate limiting.

Three checks run before every public chat message reaches the model:
  - burst: per visitor and per IP, over a short rolling window (in memory)
  - daily: per visitor and per IP (stored, so it survives restarts)
  - global daily cap for the whole shop (the budget ceiling)

Limits are owner-editable from the admin Settings tab.
"""

import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

import database

DEFAULT_SETTINGS = {
    "burst_limit": 15,  # messages per visitor...
    "burst_window_minutes": 10,  # ...within this many minutes
    "visitor_daily_limit": 100,
    "global_daily_limit": 1500,
    "history_messages": 20,  # only this many past messages go to the model
    # GemGenerate ("see it in a ring") previews, counted separately.
    "image_enabled": 1,
    "image_visitor_daily_limit": 3,
    "image_global_daily_limit": 50,
}
SETTING_BOUNDS = {
    "burst_limit": (1, 1000),
    "burst_window_minutes": (1, 240),
    "visitor_daily_limit": (1, 100000),
    "global_daily_limit": (1, 1000000),
    "history_messages": (2, 100),
    "image_enabled": (0, 1),
    "image_visitor_daily_limit": (1, 1000),
    "image_global_daily_limit": (1, 100000),
}
# Shared IPs (offices, mobile carriers) get more room than one visitor.
IP_MULTIPLIER = 3

_VISITOR_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_settings_cache = {"value": None, "at": 0.0}
_SETTINGS_TTL = 30  # seconds


def get_settings(fresh: bool = False):
    now = time.monotonic()
    if fresh or _settings_cache["value"] is None or now - _settings_cache["at"] > _SETTINGS_TTL:
        stored = database.get_settings_rows()
        _settings_cache["value"] = {
            k: int(stored.get(k, default)) for k, default in DEFAULT_SETTINGS.items()
        }
        _settings_cache["at"] = now
    return dict(_settings_cache["value"])


def update_settings(values: dict, user_email: str):
    clean = {}
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        low, high = SETTING_BOUNDS[key]
        if not isinstance(value, int) or not low <= value <= high:
            raise HTTPException(status_code=400, detail=f"{key} must be between {low} and {high}")
        clean[key] = value
    database.set_settings(clean, user_email)
    return get_settings(fresh=True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def client_ip(request: Request) -> str:
    # Render sits behind Cloudflare; prefer the headers it sets. The first
    # X-Forwarded-For entry can be spoofed, but the per-visitor and global
    # limits still apply, so this is good enough for cost control.
    for header in ("cf-connecting-ip", "true-client-ip"):
        if request.headers.get(header):
            return request.headers[header].strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def visitor_id(request: Request):
    value = (request.headers.get("x-visitor-id") or "").strip()
    return value if _VISITOR_ID.match(value) else None


# ---------- burst window (in memory) ----------

_recent: dict[str, deque] = defaultdict(deque)
_recent_lock = threading.Lock()


def _burst_check(keys, window_seconds):
    """keys: [(key, limit)]. Record one message for each key unless any key
    is over its limit.
    Returns seconds to wait, or 0 if allowed."""
    now = time.monotonic()
    with _recent_lock:
        wait = 0
        for key, key_limit in keys:
            q = _recent[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= key_limit:
                wait = max(wait, int(q[0] + window_seconds - now) + 1)
        if wait:
            return wait
        for key, _ in keys:
            _recent[key].append(now)
        # Keep memory bounded: drop idle keys now and then.
        if len(_recent) > 5000:
            for key in [k for k, q in _recent.items() if not q or q[-1] <= now - window_seconds]:
                del _recent[key]
    return 0


def _limited(code: str, message: str, retry_after: int | None = None):
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    detail = {"code": code, "message": message}
    if retry_after:
        detail["retry_after"] = retry_after
    return HTTPException(status_code=429, detail=detail, headers=headers)


def check_chat_allowed(request: Request):
    """Raise 429 if this visitor, their IP, or the whole shop is over a limit;
    otherwise count the message."""
    settings = get_settings()
    ip = client_ip(request)
    visitor = visitor_id(request)
    day = today()

    if database.get_counter(day, "global") >= settings["global_daily_limit"]:
        raise _limited("closed", "The shop has reached today's chat limit. Please come back tomorrow.")

    ip_daily = settings["visitor_daily_limit"] * IP_MULTIPLIER
    if visitor and database.get_counter(day, f"v:{visitor}") >= settings["visitor_daily_limit"]:
        raise _limited("daily", "You've reached today's message limit. Please come back tomorrow.")
    if database.get_counter(day, f"ip:{ip}") >= ip_daily:
        raise _limited("daily", "You've reached today's message limit. Please come back tomorrow.")

    burst_keys = [(f"ip:{ip}", settings["burst_limit"] * IP_MULTIPLIER)]
    if visitor:
        burst_keys.append((f"v:{visitor}", settings["burst_limit"]))
    wait = _burst_check(burst_keys, settings["burst_window_minutes"] * 60)
    if wait:
        raise _limited("slow_down", "You're sending messages quickly. Please wait a moment.", wait)

    database.increment_counter(day, "global")
    database.increment_counter(day, f"ip:{ip}")
    if visitor:
        database.increment_counter(day, f"v:{visitor}")


def request_context(request: Request):
    """Who is asking, for limits applied deeper in a reply (GemGenerate)."""
    return {"visitor": visitor_id(request), "ip": client_ip(request)}


IMAGE_LIMIT_MESSAGES = {
    "closed": "The shop has made all its AI previews for today.",
    "daily": "This customer has had all their AI previews for today.",
}


def check_image_allowed(context: dict | None):
    """Count one new AI preview for this visitor, or return a reason code
    ("off", "closed", "daily") if it isn't allowed."""
    settings = get_settings()
    if not settings["image_enabled"]:
        return "off"
    if context is None:
        return "off"
    day = today()
    if database.get_counter(day, "img") >= settings["image_global_daily_limit"]:
        return "closed"
    visitor, ip = context.get("visitor"), context.get("ip") or "unknown"
    per_visitor = settings["image_visitor_daily_limit"]
    if visitor and database.get_counter(day, f"img-v:{visitor}") >= per_visitor:
        return "daily"
    if database.get_counter(day, f"img-ip:{ip}") >= per_visitor * IP_MULTIPLIER:
        return "daily"
    database.increment_counter(day, "img")
    database.increment_counter(day, f"img-ip:{ip}")
    if visitor:
        database.increment_counter(day, f"img-v:{visitor}")
    return None


def refund_image(context: dict | None):
    """Undo check_image_allowed's count when a preview then fails."""
    if context is None:
        return
    day = today()
    database.increment_counter(day, "img", -1)
    database.increment_counter(day, f"img-ip:{context.get('ip') or 'unknown'}", -1)
    if context.get("visitor"):
        database.increment_counter(day, f"img-v:{context['visitor']}", -1)


def usage_summary():
    settings = get_settings()
    day = today()
    start = datetime.now(timezone.utc).date()
    days = [(start - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    return {
        "today": {
            "messages": database.get_counter(day, "global"),
            "visitors": database.count_counters(day, "v:"),
            "images": database.get_counter(day, "img"),
        },
        "last_7_days": database.counter_history("global", days),
        "settings": settings,
    }


def prune_old_counters(keep_days: int = 30):
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    database.prune_counters(cutoff)


def reset_memory():
    """Tests: clear burst windows and the settings cache."""
    with _recent_lock:
        _recent.clear()
    _settings_cache["value"] = None
