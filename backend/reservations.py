"""
"Reserve this stone" requests.

A customer's request never changes stock by itself: it waits as "pending"
until someone in the shop confirms it. Confirming puts the stone on hold for
a number of days:
  - a one-off stone (quantity 1) is marked "reserved", so the dealers tell
    other customers it's on hold;
  - for stones with several in stock, one unit is set aside (quantity - 1).
When a hold expires or is released, exactly that change is undone. Marking a
confirmed request "completed" means it sold.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update

import database
from database import items, reservations

REQUESTS_PER_VISITOR_PER_DAY = 3
REQUESTS_PER_IP_PER_DAY = 6
RETENTION_DAYS = 90
DEFAULT_HOLD_DAYS = 3


def reference(reservation_id: int) -> str:
    return f"LX-{reservation_id:05d}"


def _now():
    return datetime.now(timezone.utc)


def _item_for_update(conn, agent_id, item_id):
    row = conn.execute(
        select(items).where(items.c.agent_id == agent_id, items.c.id == item_id)
    ).first()
    return dict(row._mapping) if row else None


def _undo_hold(conn, r):
    """Reverse the stock change made when the request was confirmed."""
    item = _item_for_update(conn, r["agent_id"], r["item_id"])
    if not item:
        return
    if r["hold_kind"] == "status" and item["status"] == "reserved":
        conn.execute(update(items).where(items.c.id == item["id"]).values(status="available"))
    elif r["hold_kind"] == "quantity":
        conn.execute(
            update(items).where(items.c.id == item["id"]).values(quantity=item["quantity"] + 1)
        )


# ---------- housekeeping ----------

_last_sweep = {"at": 0.0}
_sweep_lock = threading.Lock()


def sweep(force: bool = False):
    """Expire holds past their date and purge old closed requests. Cheap, and
    throttled to once a minute, so it's called wherever stock is read."""
    with _sweep_lock:
        if not force and time.monotonic() - _last_sweep["at"] < 60:
            return
        _last_sweep["at"] = time.monotonic()
    now = _now()
    for r in database.due_holds(now):
        with database.get_engine().begin() as conn:
            _undo_hold(conn, r)
            database.update_reservation(
                r["id"], {"status": "expired", "handled_by": "automatic"}, conn=conn
            )
    database.purge_closed_reservations(now - timedelta(days=RETENTION_DAYS))


# ---------- customer side ----------

def check_request_allowed(visitor_id, ip):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if visitor_id and database.get_counter(day, f"r:v:{visitor_id}") >= REQUESTS_PER_VISITOR_PER_DAY:
        raise HTTPException(status_code=429, detail="You've sent several requests today. The shop will be in touch.")
    if database.get_counter(day, f"r:ip:{ip}") >= REQUESTS_PER_IP_PER_DAY:
        raise HTTPException(status_code=429, detail="Too many requests from this connection today.")
    database.increment_counter(day, f"r:ip:{ip}")
    if visitor_id:
        database.increment_counter(day, f"r:v:{visitor_id}")


def create_request(agent_id, item_id, customer: dict, transcript, visitor_id):
    sweep()
    item = database.get_item(agent_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="That stone isn't available any more.")
    if item["status"] == "sold" or item["quantity"] <= 0:
        raise HTTPException(status_code=409, detail="Sorry, that stone has just sold.")
    return database.create_reservation(
        {
            "item_id": item["id"],
            "agent_id": agent_id,
            "item_name": item["name"],
            "item_price": item["price"],
            "transcript": transcript,
            "visitor_id": visitor_id,
            **customer,
        }
    )


# ---------- shop side ----------

def _load(reservation_id, allowed_statuses):
    r = database.get_reservation(reservation_id)
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r["status"] not in allowed_statuses:
        raise HTTPException(
            status_code=409, detail=f"This request is already {r['status']}."
        )
    return r


def confirm(reservation_id, hold_days, user_email):
    sweep(force=True)
    r = _load(reservation_id, ("pending",))
    with database.get_engine().begin() as conn:
        item = _item_for_update(conn, r["agent_id"], r["item_id"])
        if not item:
            raise HTTPException(status_code=409, detail="This stone has been deleted from the inventory.")
        if item["status"] == "sold" or item["quantity"] <= 0:
            raise HTTPException(status_code=409, detail="This stone is sold out, so it can't be held.")
        if item["quantity"] > 1:
            conn.execute(
                update(items).where(items.c.id == item["id"]).values(quantity=item["quantity"] - 1)
            )
            hold_kind = "quantity"
        else:
            if item["status"] == "reserved":
                raise HTTPException(
                    status_code=409,
                    detail="This stone is already on hold (for another request, or marked reserved in the inventory).",
                )
            conn.execute(update(items).where(items.c.id == item["id"]).values(status="reserved"))
            hold_kind = "status"
        database.update_reservation(
            reservation_id,
            {
                "status": "confirmed",
                "hold_kind": hold_kind,
                "hold_until": _now() + timedelta(days=hold_days),
                "handled_by": user_email,
            },
            conn=conn,
        )
    return database.get_reservation(reservation_id)


def decline(reservation_id, user_email):
    _load(reservation_id, ("pending",))
    return database.update_reservation(
        reservation_id, {"status": "declined", "handled_by": user_email}
    )


def release(reservation_id, user_email):
    """Cancel a confirmed hold and put the stone back on sale."""
    r = _load(reservation_id, ("confirmed",))
    with database.get_engine().begin() as conn:
        _undo_hold(conn, r)
        database.update_reservation(
            reservation_id, {"status": "cancelled", "handled_by": user_email}, conn=conn
        )
    return database.get_reservation(reservation_id)


def complete(reservation_id, user_email):
    """The customer bought it."""
    r = _load(reservation_id, ("confirmed",))
    with database.get_engine().begin() as conn:
        item = _item_for_update(conn, r["agent_id"], r["item_id"])
        if item and r["hold_kind"] == "status":
            conn.execute(
                update(items).where(items.c.id == item["id"])
                .values(status="sold", quantity=max(0, item["quantity"] - 1))
            )
        # "quantity" holds already took the unit out of stock.
        database.update_reservation(
            reservation_id, {"status": "completed", "handled_by": user_email}, conn=conn
        )
    return database.get_reservation(reservation_id)


def extend(reservation_id, extra_days, user_email):
    r = _load(reservation_id, ("confirmed",))
    return database.update_reservation(
        reservation_id,
        {"hold_until": max(r["hold_until"], _now()) + timedelta(days=extra_days), "handled_by": user_email},
    )


def admin_view(r: dict) -> dict:
    item = database.get_item(r["agent_id"], r["item_id"])
    return {
        **{k: v for k, v in r.items() if k not in ("visitor_id",)},
        "reference": reference(r["id"]),
        "item": (
            {k: item[k] for k in ("id", "name", "price", "quantity", "status")} if item else None
        ),
    }
