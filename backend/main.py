import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import admin_api
import auth
import database
import limits
import storage
from chat_core import ChatMessage, ChatResponse, NonEmptyStr, run_chat

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

app = FastAPI(title="Night Market Sales Agents API")

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
    return run_chat(req.agent_id, req.message, req.history)


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
