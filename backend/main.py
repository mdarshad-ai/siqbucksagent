import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException

import admin_api
import auth
import database
import limits
import media
import pitch
import reservations
import routing
import storage
from chat_core import ChatMessage, ChatResponse, NonEmptyStr, run_chat, stream_chat

logger = logging.getLogger(__name__)

if os.environ.get("RENDER") and not os.environ.get("DATABASE_URL"):
    # Render's disk is wiped on every restart, so SQLite there loses all edits.
    logger.warning(
        "DATABASE_URL is not set - using a temporary SQLite file. Inventory, "
        "persona and user changes will be lost on restart. Set DATABASE_URL "
        "to your Supabase connection string."
    )
if os.environ.get("RENDER") and not os.environ.get("SUPABASE_URL"):
    logger.warning(
        "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set - photos and "
        "videos are saved to a temporary folder and will be lost on restart."
    )
database.init_db()
auth.bootstrap_owner()
limits.prune_old_counters()
try:
    storage.get_storage().ensure_ready()
except storage.StorageError:
    logger.exception("Media storage isn't ready - uploads will fail until it is")

app = FastAPI(title="Luxuria Gems API")

origins_env = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
origins = [o.strip() for o in origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


PUBLIC_AGENT_FIELDS = ("id", "display_name", "stall_name", "tagline", "theme")


@app.get("/api/agents")
def get_agents():
    # Metadata only - personas and selling rules stay server-side.
    return [{k: a[k] for k in PUBLIC_AGENT_FIELDS} for a in database.list_agents()]


@app.get("/api/agents/{agent_id}/inventory")
def get_inventory(agent_id: str):
    if not database.get_agent(agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    # Public view: leaves out the private sales guidance (and the story).
    return [database.public_item(i) for i in database.list_items(agent_id)]


class ChatRequest(BaseModel):
    agent_id: str
    message: NonEmptyStr = Field(max_length=2000)
    history: list[ChatMessage] = []


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    if not database.get_agent(req.agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    limits.check_chat_allowed(request)
    reservations.sweep()  # expire old holds so the dealer sees current stock
    return run_chat(req.agent_id, req.message, req.history)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request):
    """Same as /api/chat, but the reply streams in as server-sent events."""
    if not database.get_agent(req.agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    limits.check_chat_allowed(request)
    reservations.sweep()
    return StreamingResponse(
        stream_chat(req.agent_id, req.message, req.history),
        media_type="text/event-stream",
        # Don't let proxies buffer the stream.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RouteRequest(BaseModel):
    message: NonEmptyStr = Field(max_length=2000)


@app.post("/api/route")
def route(req: RouteRequest):
    """Pick which partner should answer an opening question (no AI call)."""
    return {"agent_id": routing.pick_agent(req.message)}


@app.get("/api/catalog")
def catalog(
    agent: str | None = None,
    category: str | None = None,
    q: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    include_reserved: bool = True,
    sort: Literal["newest", "price_asc", "price_desc", "carat_desc"] = "newest",
    limit: int = 24,
    offset: int = 0,
):
    """The browsable catalogue: one photo per stone, never sold-out stones."""
    reservations.sweep()
    limit = max(1, min(limit, 60))
    rows, total, categories = database.list_catalog(
        agent_id=agent, category=category, query=q[:200], min_price=min_price,
        max_price=max_price, include_reserved=include_reserved, sort=sort,
        limit=limit, offset=max(0, offset),
    )
    agents = {a["id"]: a for a in database.list_agents()}
    images = database.first_images([r["id"] for r in rows])
    return {
        "total": total,
        "categories": categories,
        "items": [media.catalog_entry(r, images.get(r["id"]), agents[r["agent_id"]]) for r in rows if r["agent_id"] in agents],
    }


def _public_stone(stone_id: int):
    item = database.get_public_item(stone_id)
    agent = database.get_agent(item["agent_id"]) if item else None
    if not item or not agent:
        raise HTTPException(status_code=404, detail="This stone isn't available.")
    return item, agent


@app.get("/api/stones/{stone_id}")
def stone(stone_id: int):
    reservations.sweep()
    item, agent = _public_stone(stone_id)
    return media.stone_page(item, agent)


@app.post("/api/stones/{stone_id}/pitch")
def stone_pitch(stone_id: int, request: Request):
    """The partner's opening pitch as server-sent events. A saved pitch is
    replayed for free; writing a new one counts toward the chat limits."""
    item, agent = _public_stone(stone_id)
    if not pitch.cached(item, agent):
        limits.check_chat_allowed(request)
    return StreamingResponse(
        pitch.stream_pitch(item, agent),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/featured")
def featured():
    """'On the counter tonight': stones the shop has chosen to feature."""
    agents = {a["id"]: a for a in database.list_agents()}
    stones = []
    for item in database.list_featured_items(limit=4):
        agent = agents.get(item["agent_id"])
        if agent:
            stones.append(
                {
                    **media.stone_card(item),
                    "agent": {k: agent[k] for k in ("id", "display_name", "stall_name", "theme")},
                }
            )
    return stones


Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class TranscriptMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ReservationRequest(BaseModel):
    agent_id: str
    item_id: int
    name: NonEmptyStr = Field(max_length=120)
    email: EmailStr
    phone: Text = Field(default="", max_length=40)
    note: Text = Field(default="", max_length=1000)
    consent: Literal[True]
    share_chat: bool = False
    transcript: list[TranscriptMessage] = Field(default=[], max_length=60)
    website: str = ""  # honeypot: people never see this field; bots fill it in


@app.post("/api/reservations", status_code=201)
def create_reservation(req: ReservationRequest, request: Request):
    if req.website:
        # Looks like a bot. Pretend it worked, store nothing.
        return {"reference": "LX-00000"}
    if not database.get_agent(req.agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    visitor = limits.visitor_id(request)
    reservations.check_request_allowed(visitor, limits.client_ip(request))
    transcript = [m.model_dump() for m in req.transcript[-40:]] if req.share_chat else None
    created = reservations.create_request(
        req.agent_id,
        req.item_id,
        {
            "customer_name": req.name,
            "email": str(req.email),
            "phone": req.phone,
            "note": req.note,
        },
        transcript,
        visitor,
    )
    return {"reference": reservations.reference(created["id"])}


app.include_router(admin_api.router)

# Local dev/tests keep uploads on disk; serve them like Supabase's public URLs.
_store = storage.get_storage()
if isinstance(_store, storage.LocalStorage):
    _store.ensure_ready()
    app.mount(
        storage.LOCAL_MEDIA_URL_PREFIX,
        StaticFiles(directory=_store.root),
        name="media-files",
    )


class SPAStaticFiles(StaticFiles):
    """Static files, falling back to index.html so client-side routes like
    /admin load the app instead of 404ing."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


# In a single-service deploy (see Dockerfile), the built frontend is copied
# here and served from the same origin as the API. Mounted last so the /api
# routes above take precedence. Local dev (Vite on :5173) doesn't use this.
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).parent / "static"))
if STATIC_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="frontend")
