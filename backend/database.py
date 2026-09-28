"""
Storage for agents, inventory and admin users.

Uses SQLAlchemy Core so the same code runs on:
  - SQLite (default, local dev and tests): a file next to this module
  - Postgres (production): set DATABASE_URL, e.g. a Supabase connection string
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError

import agent_config

DEFAULT_SQLITE_PATH = Path(__file__).parent / "inventory.db"

metadata = MetaData()

agents = Table(
    "agents",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("display_name", String(80), nullable=False),
    Column("stall_name", String(120), nullable=False),
    Column("tagline", String(200), nullable=False, default=""),
    Column("theme", Text, nullable=False),  # JSON; styling only, not editable in admin
    Column("persona", Text, nullable=False),
    Column("selling_rules", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True)),
    Column("updated_by", String(255)),
)

agent_versions = Table(
    "agent_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False),
    Column("display_name", String(80), nullable=False),
    Column("stall_name", String(120), nullable=False),
    Column("tagline", String(200), nullable=False),
    Column("persona", Text, nullable=False),
    Column("selling_rules", Text, nullable=False),
    Column("note", String(255), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", String(255)),
)

ITEM_STATUSES = ("available", "reserved", "sold")

items = Table(
    "items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String(32), ForeignKey("agents.id"), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("category", String(80), nullable=False, default=""),
    Column("carat", Float),
    Column("cut", String(80), nullable=False, default=""),
    Column("color", String(120), nullable=False, default=""),
    Column("clarity", String(120), nullable=False, default=""),
    Column("origin", String(120), nullable=False, default=""),
    Column("treatment", String(120), nullable=False, default=""),
    Column("certification", String(200), nullable=False, default=""),
    Column("price", Float, nullable=False),
    Column("quantity", Integer, nullable=False, default=0),
    Column("status", String(16), nullable=False, default="available"),
    Column("description", Text, nullable=False, default=""),
    # "Memory" the agents sell with. story: may be shared with customers.
    # sales_guidance: private coaching, never sent to the public API.
    Column("story", Text, nullable=False, default=""),
    Column("sales_guidance", Text, nullable=False, default=""),
    # Shown on the homepage under "On the counter tonight".
    Column("featured", Boolean, nullable=False, default=False),
    # Shop's own stock code (e.g. "RL1803"); blank means an automatic one.
    Column("sku", String(40), nullable=False, default=""),
    # The photo shown for this stone in the catalogue (media.id); if unset,
    # the first photo is used.
    Column("catalog_media_id", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

MEDIA_KINDS = ("image", "video", "embed")

media = Table(
    "media",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("item_id", Integer, ForeignKey("items.id"), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    # Uploaded files: storage paths (see storage.py). Embeds: a YouTube/Vimeo
    # embed URL and thumbnail instead.
    Column("path", String(500)),
    Column("poster_path", String(500)),
    Column("external_url", String(500)),
    Column("thumbnail_url", String(500)),
    Column("content_type", String(80)),
    Column("size_bytes", Integer),
    Column("caption", String(300), nullable=False, default=""),
    Column("position", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# Grading reports and certificates for a stone (PDFs or images).
certificates = Table(
    "certificates",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("item_id", Integer, ForeignKey("items.id"), nullable=False, index=True),
    Column("title", String(200), nullable=False, default=""),
    Column("lab", String(120), nullable=False, default=""),
    Column("number", String(120), nullable=False, default=""),
    Column("path", String(500), nullable=False),
    Column("content_type", String(80), nullable=False),
    Column("size_bytes", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# The partner's opening pitch for a stone page, written once and reused until
# the stone or the partner changes (fingerprint), so page views are free.
stone_pitches = Table(
    "stone_pitches",
    metadata,
    Column("item_id", Integer, primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("reply", Text, nullable=False),
    Column("suggestions", Text, nullable=False),  # JSON list
    Column("created_at", DateTime(timezone=True), nullable=False),
)

USER_ROLES = ("owner", "staff")

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(16), nullable=False),
    Column("must_change_password", Boolean, nullable=False, default=False),
    # Bumped on every password change/reset so older login tokens stop working.
    Column("token_version", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

RESERVATION_STATUSES = ("pending", "confirmed", "declined", "cancelled", "completed", "expired")

# "Reserve this stone" requests. The stone's name and price are copied in so
# the request still makes sense if the stone is later edited or deleted.
reservations = Table(
    "reservations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("item_id", Integer, nullable=False, index=True),
    Column("agent_id", String(32), nullable=False),
    Column("item_name", String(200), nullable=False),
    Column("item_price", Float, nullable=False),
    Column("customer_name", String(120), nullable=False),
    Column("email", String(255), nullable=False),
    Column("phone", String(40), nullable=False, default=""),
    Column("note", Text, nullable=False, default=""),
    Column("transcript", Text),  # JSON list of {role, content}, if shared
    Column("status", String(16), nullable=False, default="pending", index=True),
    # How a confirmed hold was applied, so it can be undone exactly:
    # "status" (item marked reserved) or "quantity" (one unit set aside).
    Column("hold_kind", String(16)),
    Column("hold_until", DateTime(timezone=True)),
    Column("admin_note", Text, nullable=False, default=""),
    Column("visitor_id", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("handled_by", String(255)),
)

# Small key/value store for owner-editable settings (values are JSON).
app_settings = Table(
    "app_settings",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", String(255)),
)

# Daily usage counters for rate limiting, e.g. ("2026-09-26", "global").
usage_counters = Table(
    "usage_counters",
    metadata,
    Column("day", String(10), primary_key=True),
    Column("key", String(120), primary_key=True),
    Column("count", Integer, nullable=False, default=0),
)

# Fields the admin UI can set on an item, and the subset customers may see.
ITEM_EDITABLE_FIELDS = (
    "name", "category", "carat", "cut", "color", "clarity", "origin",
    "treatment", "certification", "price", "quantity", "status",
    "description", "story", "sales_guidance", "featured", "sku",
)
ITEM_PUBLIC_FIELDS = (
    "id", "sku", "name", "category", "carat", "cut", "color", "clarity", "origin",
    "treatment", "certification", "price", "quantity", "status", "description",
)
AGENT_EDITABLE_FIELDS = ("display_name", "stall_name", "tagline", "persona", "selling_rules")

_engine = None


def _now():
    return datetime.now(timezone.utc)


def _database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{DEFAULT_SQLITE_PATH}"
    # Supabase/Heroku-style URLs -> the psycopg 3 driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = _database_url()
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # pre_ping: the free Supabase pooler drops idle connections.
            # prepare_threshold=None: server-side prepared statements break
            # behind Supabase's transaction pooler, so never use them.
            _engine = create_engine(
                url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                connect_args={"prepare_threshold": None},
            )
    return _engine


def reset_engine():
    """Drop the cached engine (tests switch DATABASE_URL between runs)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


# Columns added after a table first shipped. create_all() only creates
# missing tables, so these are added to existing databases on startup.
ADDED_COLUMNS = [
    ("items", "featured", {"sqlite": "BOOLEAN NOT NULL DEFAULT 0", "default": "BOOLEAN NOT NULL DEFAULT false"}),
    ("items", "sku", {"default": "VARCHAR(40) NOT NULL DEFAULT ''"}),
    ("items", "catalog_media_id", {"default": "INTEGER"}),
]


def _add_missing_columns(engine):
    inspector = inspect(engine)
    for table, column, ddl in ADDED_COLUMNS:
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing:
            spec = ddl.get(engine.dialect.name, ddl["default"])
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {spec}"))


def init_db():
    """Create tables and seed agents/items the first time only. Never
    overwrites data that's already there."""
    engine = get_engine()
    metadata.create_all(engine)
    _add_missing_columns(engine)
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(agents)).scalar() == 0:
            now = _now()
            for a in agent_config.DEFAULT_AGENTS.values():
                row = {k: a[k] for k in AGENT_EDITABLE_FIELDS}
                conn.execute(
                    insert(agents).values(
                        id=a["id"], theme=json.dumps(a["theme"]),
                        updated_at=now, updated_by="seed", **row,
                    )
                )
                conn.execute(
                    insert(agent_versions).values(
                        agent_id=a["id"], note="Initial version",
                        created_at=now, created_by="seed", **row,
                    )
                )
        _refresh_default_themes(conn)
        if conn.execute(select(func.count()).select_from(items)).scalar() == 0:
            now = _now()
            for agent_id, seed_items in agent_config.SEED_ITEMS.items():
                for item in seed_items:
                    conn.execute(
                        insert(items).values(
                            agent_id=agent_id, status="available",
                            story="", sales_guidance="",
                            created_at=now, updated_at=now, **item,
                        )
                    )


def _refresh_default_themes(conn):
    for agent_id, old_themes in agent_config.PREVIOUS_THEMES.items():
        current = agent_config.DEFAULT_AGENTS.get(agent_id, {}).get("theme")
        stored = conn.execute(select(agents.c.theme).where(agents.c.id == agent_id)).scalar()
        if current and stored and json.loads(stored) in old_themes:
            conn.execute(update(agents).where(agents.c.id == agent_id).values(theme=json.dumps(current)))


# ---------- agents ----------

def _agent_row(row):
    a = dict(row._mapping)
    a["theme"] = json.loads(a["theme"])
    return a


def list_agents():
    with get_engine().connect() as conn:
        rows = conn.execute(select(agents)).fetchall()
    order = agent_config.AGENT_ORDER
    rows = sorted(rows, key=lambda r: order.index(r.id) if r.id in order else len(order))
    return [_agent_row(r) for r in rows]


def get_agent(agent_id: str):
    with get_engine().connect() as conn:
        row = conn.execute(select(agents).where(agents.c.id == agent_id)).first()
    return _agent_row(row) if row else None


def update_agent(agent_id: str, fields: dict, user_email: str, note: str = ""):
    """Publish new persona settings and record them as a version."""
    now = _now()
    values = {k: fields[k] for k in AGENT_EDITABLE_FIELDS}
    with get_engine().begin() as conn:
        conn.execute(
            update(agents).where(agents.c.id == agent_id)
            .values(updated_at=now, updated_by=user_email, **values)
        )
        conn.execute(
            insert(agent_versions).values(
                agent_id=agent_id, note=note or "", created_at=now,
                created_by=user_email, **values,
            )
        )
    return get_agent(agent_id)


def list_agent_versions(agent_id: str, limit: int = 50):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(agent_versions)
            .where(agent_versions.c.agent_id == agent_id)
            .order_by(agent_versions.c.id.desc())
            .limit(limit)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------- items ----------

def _search_terms(query: str):
    """Split a query into words and add a naive singular form, so
    'sapphires' still matches 'Sapphire'."""
    terms = []
    for word in query.lower().split():
        word = word.strip(".,!?'\"")
        if len(word) < 2:
            continue
        terms.append(word)
        if len(word) > 3 and word.endswith("s"):
            terms.append(word[:-1])
    return terms


def search_items(agent_id: str, query: str, limit: int = 20):
    stmt = select(items).where(items.c.agent_id == agent_id)
    terms = _search_terms(query or "")
    if terms:
        searchable = (
            items.c.name, items.c.category, items.c.description, items.c.origin,
            items.c.color, items.c.cut, items.c.story,
        )
        stmt = stmt.where(or_(*[col.ilike(f"%{t}%") for t in terms for col in searchable]))
    stmt = stmt.order_by(items.c.name).limit(limit)
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]


def list_items(agent_id: str, with_media_counts: bool = False):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(items).where(items.c.agent_id == agent_id).order_by(items.c.name)
        ).fetchall()
        result = [dict(r._mapping) for r in rows]
        if with_media_counts:
            counts = dict(
                conn.execute(
                    select(media.c.item_id, func.count())
                    .join(items, items.c.id == media.c.item_id)
                    .where(items.c.agent_id == agent_id)
                    .group_by(media.c.item_id)
                ).fetchall()
            )
            for item in result:
                item["media_count"] = counts.get(item["id"], 0)
    return result


def list_featured_items(limit: int = 4):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(items)
            .where(items.c.featured.is_(True), items.c.status == "available", items.c.quantity > 0)
            .order_by(items.c.updated_at.desc())
            .limit(limit)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_item(agent_id: str, item_id):
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return None
    with get_engine().connect() as conn:
        row = conn.execute(
            select(items).where(items.c.agent_id == agent_id, items.c.id == item_id)
        ).first()
    return dict(row._mapping) if row else None


def create_item(agent_id: str, fields: dict):
    now = _now()
    values = {k: fields[k] for k in ITEM_EDITABLE_FIELDS if k in fields}
    with get_engine().begin() as conn:
        result = conn.execute(
            insert(items).values(agent_id=agent_id, created_at=now, updated_at=now, **values)
        )
        item_id = result.inserted_primary_key[0]
    return get_item(agent_id, item_id)


def update_item(agent_id: str, item_id: int, fields: dict):
    values = {k: fields[k] for k in ITEM_EDITABLE_FIELDS if k in fields}
    with get_engine().begin() as conn:
        result = conn.execute(
            update(items)
            .where(items.c.agent_id == agent_id, items.c.id == item_id)
            .values(updated_at=_now(), **values)
        )
        if result.rowcount == 0:
            return None
    return get_item(agent_id, item_id)


def delete_item(agent_id: str, item_id: int):
    """Delete a stone with its media, certificates and saved pitch. Returns
    the deleted media and certificate rows (so the caller can remove their
    files), or None if the stone wasn't found."""
    with get_engine().begin() as conn:
        exists = conn.execute(
            select(items.c.id).where(items.c.agent_id == agent_id, items.c.id == item_id)
        ).first()
        if not exists:
            return None
        rows = conn.execute(select(media).where(media.c.item_id == item_id)).fetchall()
        rows += conn.execute(select(certificates).where(certificates.c.item_id == item_id)).fetchall()
        conn.execute(delete(media).where(media.c.item_id == item_id))
        conn.execute(delete(certificates).where(certificates.c.item_id == item_id))
        conn.execute(delete(stone_pitches).where(stone_pitches.c.item_id == item_id))
        conn.execute(delete(items).where(items.c.id == item_id))
    return [dict(r._mapping) for r in rows]


def public_item(item: dict):
    return {k: item[k] for k in ITEM_PUBLIC_FIELDS}


# ---------- media ----------

def list_media(item_id: int):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(media).where(media.c.item_id == item_id)
            .order_by(media.c.position, media.c.id)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_media(item_id: int, media_id: int):
    with get_engine().connect() as conn:
        row = conn.execute(
            select(media).where(media.c.item_id == item_id, media.c.id == media_id)
        ).first()
    return dict(row._mapping) if row else None


def create_media(item_id: int, fields: dict):
    with get_engine().begin() as conn:
        last = conn.execute(
            select(func.max(media.c.position)).where(media.c.item_id == item_id)
        ).scalar()
        result = conn.execute(
            insert(media).values(
                item_id=item_id,
                position=(last + 1) if last is not None else 0,
                created_at=_now(),
                **fields,
            )
        )
        media_id = result.inserted_primary_key[0]
    return get_media(item_id, media_id)


def update_media(item_id: int, media_id: int, fields: dict):
    with get_engine().begin() as conn:
        conn.execute(
            update(media).where(media.c.item_id == item_id, media.c.id == media_id)
            .values(**fields)
        )
    return get_media(item_id, media_id)


def reorder_media(item_id: int, ordered_ids: list[int]):
    """Set positions from the given order. Ids must be exactly the stone's media."""
    current = {m["id"] for m in list_media(item_id)}
    if set(ordered_ids) != current or len(ordered_ids) != len(current):
        return None
    with get_engine().begin() as conn:
        for position, media_id in enumerate(ordered_ids):
            conn.execute(
                update(media).where(media.c.item_id == item_id, media.c.id == media_id)
                .values(position=position)
            )
    return list_media(item_id)


def delete_media(item_id: int, media_id: int):
    row = get_media(item_id, media_id)
    if not row:
        return None
    with get_engine().begin() as conn:
        conn.execute(delete(media).where(media.c.id == media_id))
        # If it was the catalogue photo, fall back to the first photo.
        conn.execute(
            update(items).where(items.c.id == item_id, items.c.catalog_media_id == media_id)
            .values(catalog_media_id=None)
        )
    return row


def set_catalog_media(item_id: int, media_id):
    with get_engine().begin() as conn:
        conn.execute(update(items).where(items.c.id == item_id).values(catalog_media_id=media_id))


# ---------- certificates ----------

def list_certificates(item_id: int):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(certificates).where(certificates.c.item_id == item_id).order_by(certificates.c.id)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def create_certificate(item_id: int, fields: dict):
    with get_engine().begin() as conn:
        result = conn.execute(insert(certificates).values(item_id=item_id, created_at=_now(), **fields))
        cid = result.inserted_primary_key[0]
    return get_certificate(item_id, cid)


def get_certificate(item_id: int, certificate_id: int):
    with get_engine().connect() as conn:
        row = conn.execute(
            select(certificates).where(
                certificates.c.item_id == item_id, certificates.c.id == certificate_id
            )
        ).first()
    return dict(row._mapping) if row else None


def update_certificate(item_id: int, certificate_id: int, fields: dict):
    with get_engine().begin() as conn:
        conn.execute(
            update(certificates)
            .where(certificates.c.item_id == item_id, certificates.c.id == certificate_id)
            .values(**fields)
        )
    return get_certificate(item_id, certificate_id)


def delete_certificate(item_id: int, certificate_id: int):
    row = get_certificate(item_id, certificate_id)
    if row:
        with get_engine().begin() as conn:
            conn.execute(delete(certificates).where(certificates.c.id == certificate_id))
    return row


# ---------- catalogue ----------

CATALOG_SORTS = {
    "newest": lambda: [items.c.created_at.desc(), items.c.id.desc()],
    "price_asc": lambda: [items.c.price.asc(), items.c.id],
    "price_desc": lambda: [items.c.price.desc(), items.c.id],
    "carat_desc": lambda: [items.c.carat.desc().nulls_last(), items.c.id],
}


def list_catalog(agent_id=None, category=None, query="", min_price=None, max_price=None,
                 include_reserved=True, sort="newest", limit=24, offset=0):
    """Stones customers may browse (never sold-out ones), plus the total."""
    statuses = ["available", "reserved"] if include_reserved else ["available"]
    conditions = [items.c.status.in_(statuses), items.c.quantity > 0]
    if agent_id:
        conditions.append(items.c.agent_id == agent_id)
    if category:
        conditions.append(func.lower(items.c.category) == category.lower())
    if min_price is not None:
        conditions.append(items.c.price >= min_price)
    if max_price is not None:
        conditions.append(items.c.price <= max_price)
    terms = _search_terms(query or "")
    if terms:
        searchable = (items.c.name, items.c.category, items.c.origin, items.c.color, items.c.sku)
        conditions.append(and_(*[or_(*[col.ilike(f"%{t}%") for col in searchable]) for t in terms]))
    with get_engine().connect() as conn:
        total = conn.execute(select(func.count()).select_from(items).where(*conditions)).scalar()
        rows = conn.execute(
            select(items).where(*conditions)
            .order_by(*CATALOG_SORTS.get(sort, CATALOG_SORTS["newest"])())
            .limit(limit).offset(offset)
        ).fetchall()
        categories = [
            c for (c,) in conn.execute(
                select(items.c.category).distinct()
                .where(items.c.status.in_(statuses), items.c.quantity > 0, items.c.category != "")
                .order_by(items.c.category)
            ).fetchall()
        ]
    return [dict(r._mapping) for r in rows], total, categories


def get_public_item(item_id: int):
    """A stone by id alone, if customers may see it (not sold out)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            select(items).where(
                items.c.id == item_id, items.c.status.in_(("available", "reserved")), items.c.quantity > 0
            )
        ).first()
    return dict(row._mapping) if row else None


def first_images(item_ids):
    """{item_id: media row} for each stone's catalogue photo: the chosen one,
    else its first photo."""
    if not item_ids:
        return {}
    with get_engine().connect() as conn:
        chosen = dict(
            conn.execute(select(items.c.id, items.c.catalog_media_id).where(items.c.id.in_(item_ids))).fetchall()
        )
        rows = conn.execute(
            select(media).where(media.c.item_id.in_(item_ids), media.c.kind == "image")
            .order_by(media.c.position, media.c.id)
        ).fetchall()
    result = {}
    for r in rows:
        m = dict(r._mapping)
        if chosen.get(m["item_id"]) == m["id"]:
            result[m["item_id"]] = m
        else:
            result.setdefault(m["item_id"], m)
    return result


# ---------- saved pitches ----------

def get_pitch(item_id: int):
    with get_engine().connect() as conn:
        row = conn.execute(select(stone_pitches).where(stone_pitches.c.item_id == item_id)).first()
    if not row:
        return None
    p = dict(row._mapping)
    p["suggestions"] = json.loads(p["suggestions"])
    return p


def save_pitch(item_id: int, fingerprint: str, reply: str, suggestions):
    with get_engine().begin() as conn:
        conn.execute(delete(stone_pitches).where(stone_pitches.c.item_id == item_id))
        conn.execute(
            insert(stone_pitches).values(
                item_id=item_id, fingerprint=fingerprint, reply=reply,
                suggestions=json.dumps(suggestions or []), created_at=_now(),
            )
        )


# ---------- reservations ----------

def _as_utc(value):
    # SQLite hands back naive datetimes; everything we store is UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _reservation_row(row):
    r = dict(row._mapping)
    for key in ("hold_until", "created_at", "updated_at"):
        r[key] = _as_utc(r[key])
    r["transcript"] = json.loads(r["transcript"]) if r["transcript"] else None
    return r


def create_reservation(fields: dict):
    now = _now()
    values = dict(fields)
    if values.get("transcript") is not None:
        values["transcript"] = json.dumps(values["transcript"])
    with get_engine().begin() as conn:
        result = conn.execute(
            insert(reservations).values(status="pending", created_at=now, updated_at=now, **values)
        )
        rid = result.inserted_primary_key[0]
    return get_reservation(rid)


def get_reservation(reservation_id: int):
    with get_engine().connect() as conn:
        row = conn.execute(select(reservations).where(reservations.c.id == reservation_id)).first()
    return _reservation_row(row) if row else None


def list_reservations(statuses=None, limit: int = 200):
    stmt = select(reservations).order_by(reservations.c.created_at.desc()).limit(limit)
    if statuses:
        stmt = stmt.where(reservations.c.status.in_(statuses))
    with get_engine().connect() as conn:
        return [_reservation_row(r) for r in conn.execute(stmt).fetchall()]


def count_reservations(status: str) -> int:
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count()).select_from(reservations).where(reservations.c.status == status)
        ).scalar()


def update_reservation(reservation_id: int, fields: dict, conn=None):
    stmt = (
        update(reservations).where(reservations.c.id == reservation_id)
        .values(updated_at=_now(), **fields)
    )
    if conn is not None:
        conn.execute(stmt)
        return None
    with get_engine().begin() as c:
        c.execute(stmt)
    return get_reservation(reservation_id)


def due_holds(now):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(reservations).where(
                reservations.c.status == "confirmed", reservations.c.hold_until < now
            )
        ).fetchall()
    return [_reservation_row(r) for r in rows]


def purge_closed_reservations(before):
    """Delete closed requests (and the customer details in them) older than
    the retention window."""
    with get_engine().begin() as conn:
        conn.execute(
            delete(reservations).where(
                reservations.c.status.in_(("declined", "cancelled", "completed", "expired")),
                reservations.c.updated_at < before,
            )
        )


# ---------- settings ----------

def get_settings_rows():
    with get_engine().connect() as conn:
        rows = conn.execute(select(app_settings)).fetchall()
    return {r.key: json.loads(r.value) for r in rows}


def set_settings(values: dict, user_email: str):
    now = _now()
    with get_engine().begin() as conn:
        for key, value in values.items():
            encoded = json.dumps(value)
            result = conn.execute(
                update(app_settings).where(app_settings.c.key == key)
                .values(value=encoded, updated_at=now, updated_by=user_email)
            )
            if result.rowcount == 0:
                conn.execute(
                    insert(app_settings).values(
                        key=key, value=encoded, updated_at=now, updated_by=user_email
                    )
                )


# ---------- usage counters ----------

def increment_counter(day: str, key: str, amount: int = 1) -> int:
    """Add to a daily counter and return its new value."""
    where = and_(usage_counters.c.day == day, usage_counters.c.key == key)
    for _ in range(3):  # retry if two requests create the same row at once
        try:
            with get_engine().begin() as conn:
                result = conn.execute(
                    update(usage_counters).where(where)
                    .values(count=usage_counters.c.count + amount)
                )
                if result.rowcount == 0:
                    conn.execute(insert(usage_counters).values(day=day, key=key, count=amount))
                return conn.execute(select(usage_counters.c.count).where(where)).scalar()
        except IntegrityError:
            continue
    raise RuntimeError("Couldn't update usage counter")


def get_counter(day: str, key: str) -> int:
    with get_engine().connect() as conn:
        value = conn.execute(
            select(usage_counters.c.count).where(
                usage_counters.c.day == day, usage_counters.c.key == key
            )
        ).scalar()
    return value or 0


def count_counters(day: str, prefix: str) -> int:
    """How many counters exist for a day with a key prefix (e.g. visitors)."""
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count()).select_from(usage_counters).where(
                usage_counters.c.day == day, usage_counters.c.key.like(f"{prefix}%")
            )
        ).scalar()


def counter_history(key: str, days: list[str]):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(usage_counters.c.day, usage_counters.c.count).where(
                usage_counters.c.key == key, usage_counters.c.day.in_(days)
            )
        ).fetchall()
    found = dict(rows)
    return [{"day": d, "count": found.get(d, 0)} for d in days]


def prune_counters(before_day: str):
    with get_engine().begin() as conn:
        conn.execute(delete(usage_counters).where(usage_counters.c.day < before_day))


# ---------- users ----------

def count_users():
    with get_engine().connect() as conn:
        return conn.execute(select(func.count()).select_from(users)).scalar()


def count_owners():
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.count()).select_from(users).where(users.c.role == "owner")
        ).scalar()


def list_users():
    with get_engine().connect() as conn:
        rows = conn.execute(select(users).order_by(users.c.email)).fetchall()
    return [dict(r._mapping) for r in rows]


def get_user(user_id: int):
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).first()
    return dict(row._mapping) if row else None


def get_user_by_email(email: str):
    with get_engine().connect() as conn:
        row = conn.execute(
            select(users).where(func.lower(users.c.email) == email.strip().lower())
        ).first()
    return dict(row._mapping) if row else None


def create_user(email: str, password_hash: str, role: str, must_change_password: bool):
    with get_engine().begin() as conn:
        result = conn.execute(
            insert(users).values(
                email=email.strip().lower(), password_hash=password_hash, role=role,
                must_change_password=must_change_password, token_version=0,
                created_at=_now(),
            )
        )
        user_id = result.inserted_primary_key[0]
    return get_user(user_id)


def set_user_password(user_id: int, password_hash: str, must_change_password: bool):
    with get_engine().begin() as conn:
        conn.execute(
            update(users).where(users.c.id == user_id).values(
                password_hash=password_hash,
                must_change_password=must_change_password,
                token_version=users.c.token_version + 1,
            )
        )
    return get_user(user_id)


def set_user_role(user_id: int, role: str):
    with get_engine().begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(role=role))
    return get_user(user_id)


def delete_user(user_id: int):
    with get_engine().begin() as conn:
        result = conn.execute(delete(users).where(users.c.id == user_id))
    return result.rowcount > 0
