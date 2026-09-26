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
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)

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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
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

# Fields the admin UI can set on an item, and the subset customers may see.
ITEM_EDITABLE_FIELDS = (
    "name", "category", "carat", "cut", "color", "clarity", "origin",
    "treatment", "certification", "price", "quantity", "status",
    "description", "story", "sales_guidance",
)
ITEM_PUBLIC_FIELDS = (
    "id", "name", "category", "carat", "cut", "color", "clarity", "origin",
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


def init_db():
    """Create tables and seed agents/items the first time only. Never
    overwrites data that's already there."""
    engine = get_engine()
    metadata.create_all(engine)
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


def list_items(agent_id: str):
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(items).where(items.c.agent_id == agent_id).order_by(items.c.name)
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
    with get_engine().begin() as conn:
        result = conn.execute(
            delete(items).where(items.c.agent_id == agent_id, items.c.id == item_id)
        )
    return result.rowcount > 0


def public_item(item: dict):
    return {k: item[k] for k in ITEM_PUBLIC_FIELDS}


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
