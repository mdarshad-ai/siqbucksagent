"""Admin API: login, inventory, agent personas, and user management."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, StringConstraints

import logging

import auth
import database
import gemgenerate
import limits
import media
import reservations
import storage
from agent_config import CORE_RULES
from chat_core import ChatMessage, ChatResponse, NonEmptyStr, run_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin")

Text = Annotated[str, StringConstraints(strip_whitespace=True)]


def _require_agent(agent_id: str):
    agent = database.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")
    return agent


# ---------- login / account ----------

class LoginRequest(BaseModel):
    email: NonEmptyStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _session(user):
    return {"token": auth.issue_token(user), "user": auth.public_user(user)}


@router.post("/login")
def login(req: LoginRequest):
    email = req.email.lower()
    auth.check_login_allowed(email)
    user = database.get_user_by_email(email)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        auth.record_login_failure(email)
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    auth.clear_login_failures(email)
    return _session(user)


@router.get("/me")
def me(user: dict = Depends(auth.current_user_allow_password_change)):
    return auth.public_user(user)


@router.post("/me/password")
def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(auth.current_user_allow_password_change),
):
    if not auth.verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is wrong.")
    auth.validate_new_password(req.new_password)
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="Choose a different password.")
    user = database.set_user_password(
        user["id"], auth.hash_password(req.new_password), must_change_password=False
    )
    # Changing the password invalidates old tokens, so hand back a fresh one.
    return _session(user)


# ---------- agents ----------

class AgentFields(BaseModel):
    display_name: NonEmptyStr = Field(max_length=80)
    stall_name: NonEmptyStr = Field(max_length=120)
    tagline: Text = Field(default="", max_length=200)
    persona: NonEmptyStr = Field(max_length=8000)
    selling_rules: Text = Field(default="", max_length=8000)


class AgentUpdate(AgentFields):
    note: Text = Field(default="", max_length=255)


class PreviewRequest(BaseModel):
    draft: AgentFields
    message: NonEmptyStr = Field(max_length=2000)
    history: list[ChatMessage] = []


@router.get("/agents")
def list_agents(user: dict = Depends(auth.current_user)):
    fields = ("id", "display_name", "stall_name")
    return [{k: a[k] for k in fields} for a in database.list_agents()]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, user: dict = Depends(auth.require_owner)):
    agent = _require_agent(agent_id)
    return {**agent, "core_rules": CORE_RULES}


@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, req: AgentUpdate, user: dict = Depends(auth.require_owner)):
    _require_agent(agent_id)
    fields = req.model_dump(exclude={"note"})
    agent = database.update_agent(agent_id, fields, user["email"], note=req.note)
    return {**agent, "core_rules": CORE_RULES}


@router.get("/agents/{agent_id}/versions")
def agent_versions(agent_id: str, user: dict = Depends(auth.require_owner)):
    _require_agent(agent_id)
    return database.list_agent_versions(agent_id)


@router.post("/agents/{agent_id}/preview", response_model=ChatResponse)
def preview_agent(agent_id: str, req: PreviewRequest, user: dict = Depends(auth.require_owner)):
    """Chat with an unsaved draft persona against the real inventory."""
    _require_agent(agent_id)
    return run_chat(agent_id, req.message, req.history, agent_override=req.draft.model_dump())


# ---------- inventory ----------

class ItemFields(BaseModel):
    name: NonEmptyStr = Field(max_length=200)
    category: Text = Field(default="", max_length=80)
    carat: float | None = Field(default=None, ge=0)
    cut: Text = Field(default="", max_length=80)
    color: Text = Field(default="", max_length=120)
    clarity: Text = Field(default="", max_length=120)
    origin: Text = Field(default="", max_length=120)
    treatment: Text = Field(default="", max_length=120)
    certification: Text = Field(default="", max_length=200)
    price: float = Field(ge=0)
    quantity: int = Field(ge=0)
    status: Literal[database.ITEM_STATUSES] = "available"
    description: Text = Field(default="", max_length=2000)
    story: Text = Field(default="", max_length=5000)
    sales_guidance: Text = Field(default="", max_length=5000)
    featured: bool = False
    sku: Text = Field(default="", max_length=40)


@router.get("/agents/{agent_id}/items")
def list_items(agent_id: str, user: dict = Depends(auth.current_user)):
    _require_agent(agent_id)
    reservations.sweep()
    return database.list_items(agent_id, with_media_counts=True)


@router.post("/agents/{agent_id}/items", status_code=201)
def create_item(agent_id: str, req: ItemFields, user: dict = Depends(auth.current_user)):
    _require_agent(agent_id)
    return database.create_item(agent_id, req.model_dump())


@router.put("/agents/{agent_id}/items/{item_id}")
def update_item(
    agent_id: str, item_id: int, req: ItemFields, user: dict = Depends(auth.current_user)
):
    _require_agent(agent_id)
    item = database.update_item(agent_id, item_id, req.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Stone not found")
    return item


@router.delete("/agents/{agent_id}/items/{item_id}", status_code=204)
def delete_item(agent_id: str, item_id: int, user: dict = Depends(auth.current_user)):
    _require_agent(agent_id)
    removed = database.delete_item(agent_id, item_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Stone not found")
    _delete_files(removed)


# ---------- media ----------

def _require_item(agent_id: str, item_id: int):
    _require_agent(agent_id)
    item = database.get_item(agent_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Stone not found")
    return item


def _delete_files(rows):
    paths = [p for r in rows for p in (r.get("path"), r.get("poster_path")) if p]
    if paths:
        storage.get_storage().delete(paths)


def _check_uploaded(item_id: int, path: str | None):
    """An uploaded path must belong to this stone and actually exist."""
    if not path:
        return
    if not path.startswith(f"items/{item_id}/") or ".." in path:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    try:
        found = storage.get_storage().exists(path)
    except storage.StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not found:
        raise HTTPException(status_code=400, detail="Upload not found - please try again")


class UploadRequest(BaseModel):
    content_type: str
    size_bytes: int = Field(gt=0)
    purpose: Literal["media", "poster", "certificate"] = "media"


class MediaCreate(BaseModel):
    path: str = Field(max_length=500)
    content_type: str
    size_bytes: int = Field(gt=0)
    poster_path: str | None = Field(default=None, max_length=500)
    caption: Text = Field(default="", max_length=300)


class LinkCreate(BaseModel):
    url: NonEmptyStr = Field(max_length=500)
    caption: Text = Field(default="", max_length=300)


class MediaUpdate(BaseModel):
    caption: Text | None = Field(default=None, max_length=300)
    poster_path: str | None = Field(default=None, max_length=500)


class MediaOrder(BaseModel):
    ids: list[int]


def _admin_media_list(item):
    return [
        {**media.admin_media(m), "is_catalog": m["id"] == item.get("catalog_media_id")}
        for m in database.list_media(item["id"])
    ]


@router.get("/agents/{agent_id}/items/{item_id}/media")
def list_item_media(agent_id: str, item_id: int, user: dict = Depends(auth.current_user)):
    return _admin_media_list(_require_item(agent_id, item_id))


class CatalogImage(BaseModel):
    media_id: int | None = None


@router.put("/agents/{agent_id}/items/{item_id}/catalog-image")
def set_catalog_image(
    agent_id: str, item_id: int, req: CatalogImage, user: dict = Depends(auth.current_user)
):
    """Pick which photo represents the stone in the catalogue (None = first photo)."""
    _require_item(agent_id, item_id)
    if req.media_id is not None:
        row = database.get_media(item_id, req.media_id)
        if not row or row["kind"] != "image":
            raise HTTPException(status_code=400, detail="Choose one of this stone's photos.")
    database.set_catalog_media(item_id, req.media_id)
    return _admin_media_list(database.get_item(agent_id, item_id))


@router.post("/agents/{agent_id}/items/{item_id}/media/upload-url")
def create_upload_url(
    agent_id: str, item_id: int, req: UploadRequest, user: dict = Depends(auth.current_user)
):
    """A short-lived URL the browser uploads one file to directly."""
    _require_item(agent_id, item_id)
    allowed = {
        "poster": storage.IMAGE_TYPES,
        "certificate": storage.CERTIFICATE_TYPES,
    }.get(req.purpose, storage.ALLOWED_TYPES)
    ext = allowed.get(req.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Certificates can be PDF, JPG, PNG or WebP."
                if req.purpose == "certificate"
                else "Unsupported file type. Use JPG, PNG or WebP photos, or MP4/MOV/WebM videos."
            ),
        )
    if req.size_bytes > storage.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is larger than 50 MB.")
    path = f"items/{item_id}/{uuid.uuid4().hex}.{ext}"
    try:
        upload = storage.get_storage().create_upload(path, req.content_type)
    except storage.StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {**upload, "path": path, "headers": {"Content-Type": req.content_type}}


@router.put("/local-upload", include_in_schema=False)
async def local_upload(token: str, request: Request):
    """Upload target for LocalStorage (dev/tests). Authorised by the signed
    token in the URL, like Supabase's signed upload URLs."""
    store = storage.get_storage()
    if not isinstance(store, storage.LocalStorage):
        raise HTTPException(status_code=404)
    try:
        path, _ = store.read_upload_token(token)
        body = [chunk async for chunk in request.stream()]
        size = store.write(path, body)
    except storage.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"path": path, "size_bytes": size}


@router.post("/agents/{agent_id}/items/{item_id}/media", status_code=201)
def add_uploaded_media(
    agent_id: str, item_id: int, req: MediaCreate, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    if req.content_type in storage.IMAGE_TYPES:
        kind = "image"
    elif req.content_type in storage.VIDEO_TYPES:
        kind = "video"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    _check_uploaded(item_id, req.path)
    if req.poster_path:
        if kind != "video":
            raise HTTPException(status_code=400, detail="Only videos have a still frame")
        _check_uploaded(item_id, req.poster_path)
    row = database.create_media(
        item_id,
        {
            "kind": kind,
            "path": req.path,
            "poster_path": req.poster_path,
            "content_type": req.content_type,
            "size_bytes": req.size_bytes,
            "caption": req.caption,
        },
    )
    return {**media.admin_media(row), "is_catalog": False}


@router.post("/agents/{agent_id}/items/{item_id}/media/link", status_code=201)
def add_video_link(
    agent_id: str, item_id: int, req: LinkCreate, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    parsed = media.parse_video_link(req.url)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a YouTube or Vimeo video link.",
        )
    embed_url, thumbnail_url = parsed
    row = database.create_media(
        item_id,
        {
            "kind": "embed",
            "external_url": embed_url,
            "thumbnail_url": thumbnail_url,
            "caption": req.caption,
        },
    )
    return {**media.admin_media(row), "is_catalog": False}


@router.patch("/agents/{agent_id}/items/{item_id}/media/{media_id}")
def update_media(
    agent_id: str, item_id: int, media_id: int, req: MediaUpdate,
    user: dict = Depends(auth.current_user),
):
    item = _require_item(agent_id, item_id)
    row = database.get_media(item_id, media_id)
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    fields = {}
    if req.caption is not None:
        fields["caption"] = req.caption
    if req.poster_path is not None:
        if row["kind"] != "video":
            raise HTTPException(status_code=400, detail="Only videos have a still frame")
        _check_uploaded(item_id, req.poster_path)
        fields["poster_path"] = req.poster_path
    updated = database.update_media(item_id, media_id, fields) if fields else row
    if "poster_path" in fields and row["poster_path"] and row["poster_path"] != req.poster_path:
        storage.get_storage().delete([row["poster_path"]])
    return {**media.admin_media(updated), "is_catalog": updated["id"] == item.get("catalog_media_id")}


@router.put("/agents/{agent_id}/items/{item_id}/media/order")
def reorder_media(
    agent_id: str, item_id: int, req: MediaOrder, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    if database.reorder_media(item_id, req.ids) is None:
        raise HTTPException(status_code=400, detail="The order must list each media item once.")
    return _admin_media_list(database.get_item(agent_id, item_id))


@router.delete("/agents/{agent_id}/items/{item_id}/media/{media_id}", status_code=204)
def delete_media(
    agent_id: str, item_id: int, media_id: int, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    row = database.delete_media(item_id, media_id)
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    _delete_files([row])


# ---------- users (owners only) ----------

Role = Literal[database.USER_ROLES]


class NewUser(BaseModel):
    email: EmailStr
    role: Role = "staff"


class RoleUpdate(BaseModel):
    role: Role


def _other_user(user_id: int, me: dict):
    target = database.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["id"] == me["id"]:
        raise HTTPException(
            status_code=400,
            detail="You can't change your own role or account here.",
        )
    return target


@router.get("/users")
def list_users(user: dict = Depends(auth.require_owner)):
    return [auth.public_user(u) for u in database.list_users()]


@router.post("/users", status_code=201)
def create_user(req: NewUser, user: dict = Depends(auth.require_owner)):
    if database.get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    temp_password = auth.generate_temp_password()
    new_user = database.create_user(
        req.email, auth.hash_password(temp_password), req.role, must_change_password=True
    )
    # The temporary password is only ever shown in this response.
    return {"user": auth.public_user(new_user), "temp_password": temp_password}


@router.patch("/users/{user_id}")
def update_user_role(user_id: int, req: RoleUpdate, user: dict = Depends(auth.require_owner)):
    target = _other_user(user_id, user)
    return auth.public_user(database.set_user_role(target["id"], req.role))


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, user: dict = Depends(auth.require_owner)):
    target = _other_user(user_id, user)
    temp_password = auth.generate_temp_password()
    updated = database.set_user_password(
        target["id"], auth.hash_password(temp_password), must_change_password=True
    )
    return {"user": auth.public_user(updated), "temp_password": temp_password}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, user: dict = Depends(auth.require_owner)):
    target = _other_user(user_id, user)
    database.delete_user(target["id"])


# ---------- chat limits & usage (owners only) ----------

class LimitSettings(BaseModel):
    burst_limit: int | None = None
    burst_window_minutes: int | None = None
    visitor_daily_limit: int | None = None
    global_daily_limit: int | None = None
    history_messages: int | None = None
    image_enabled: int | None = None
    image_visitor_daily_limit: int | None = None
    image_global_daily_limit: int | None = None


@router.get("/usage")
def usage(user: dict = Depends(auth.require_owner)):
    return limits.usage_summary()


@router.put("/settings/limits")
def update_limits(req: LimitSettings, user: dict = Depends(auth.require_owner)):
    values = {k: v for k, v in req.model_dump().items() if v is not None}
    return limits.update_settings(values, user["email"])


# ---------- GemGenerate: AI jewellery previews (owners only) ----------

def _gemgenerate_status():
    return {
        "model": gemgenerate.current_model(),
        "default_model": gemgenerate.DEFAULT_IMAGE_MODEL,
        "choices": gemgenerate.MODEL_CHOICES,
        "settings": list(gemgenerate.SETTINGS),
        "metals": list(gemgenerate.METALS),
        "styles": list(gemgenerate.STYLES),
        "saved_previews": database.count_generated(),
    }


@router.get("/gemgenerate")
def gemgenerate_status(user: dict = Depends(auth.require_owner)):
    return _gemgenerate_status()


class ImageModelUpdate(BaseModel):
    model: NonEmptyStr = Field(max_length=200)


@router.put("/gemgenerate/model")
def set_image_model(req: ImageModelUpdate, user: dict = Depends(auth.require_owner)):
    if not gemgenerate.valid_model(req.model):
        raise HTTPException(status_code=400, detail="Use an OpenRouter model id like provider/model-name")
    gemgenerate.set_model(req.model, user["email"])
    return _gemgenerate_status()


class ImageTestRequest(BaseModel):
    agent_id: str
    item_id: int
    setting: Literal[tuple(gemgenerate.SETTINGS)]
    metal: Literal[tuple(gemgenerate.METALS)]
    style: Literal[("",) + tuple(gemgenerate.STYLES)] = ""
    model: NonEmptyStr = Field(max_length=200)


@router.post("/gemgenerate/test")
def test_image_model(req: ImageTestRequest, user: dict = Depends(auth.require_owner)):
    """Try a model on one stone without saving or showing it to customers."""
    if not gemgenerate.valid_model(req.model):
        raise HTTPException(status_code=400, detail="Use an OpenRouter model id like provider/model-name")
    item = _require_item(req.agent_id, req.item_id)
    try:
        return gemgenerate.test_preview(item, req.setting, req.metal, req.style, req.model)
    except gemgenerate.GemGenerateError as exc:
        raise HTTPException(status_code=400, detail=f"Couldn't make a preview: {exc}")
    except Exception:
        logger.exception("GemGenerate test failed for model %s", req.model)
        raise HTTPException(
            status_code=502,
            detail="The image model failed. Check the model id supports image input and output on OpenRouter.",
        )


# ---------- reservation requests (owners and staff) ----------

STATUS_GROUPS = {
    "pending": ("pending",),
    "active": ("confirmed",),
    "closed": ("declined", "cancelled", "completed", "expired"),
}


class HoldRequest(BaseModel):
    hold_days: int = Field(default=reservations.DEFAULT_HOLD_DAYS, ge=1, le=30)


class ExtendRequest(BaseModel):
    extra_days: int = Field(ge=1, le=30)


class ReservationNote(BaseModel):
    admin_note: Text = Field(max_length=2000)


@router.get("/reservations/summary")
def reservation_summary(user: dict = Depends(auth.current_user)):
    reservations.sweep()
    return {"pending": database.count_reservations("pending")}


@router.get("/reservations")
def list_reservations(
    group: Literal["pending", "active", "closed"] = "pending",
    user: dict = Depends(auth.current_user),
):
    reservations.sweep()
    rows = database.list_reservations(STATUS_GROUPS[group])
    return [reservations.admin_view(r) for r in rows]


@router.post("/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int, req: HoldRequest, user: dict = Depends(auth.current_user)
):
    return reservations.admin_view(reservations.confirm(reservation_id, req.hold_days, user["email"]))


@router.post("/reservations/{reservation_id}/extend")
def extend_reservation(
    reservation_id: int, req: ExtendRequest, user: dict = Depends(auth.current_user)
):
    return reservations.admin_view(reservations.extend(reservation_id, req.extra_days, user["email"]))


@router.post("/reservations/{reservation_id}/decline")
def decline_reservation(reservation_id: int, user: dict = Depends(auth.current_user)):
    return reservations.admin_view(reservations.decline(reservation_id, user["email"]))


@router.post("/reservations/{reservation_id}/release")
def release_reservation(reservation_id: int, user: dict = Depends(auth.current_user)):
    return reservations.admin_view(reservations.release(reservation_id, user["email"]))


@router.post("/reservations/{reservation_id}/complete")
def complete_reservation(reservation_id: int, user: dict = Depends(auth.current_user)):
    return reservations.admin_view(reservations.complete(reservation_id, user["email"]))


@router.patch("/reservations/{reservation_id}")
def update_reservation_note(
    reservation_id: int, req: ReservationNote, user: dict = Depends(auth.current_user)
):
    if not database.get_reservation(reservation_id):
        raise HTTPException(status_code=404, detail="Request not found")
    updated = database.update_reservation(reservation_id, {"admin_note": req.admin_note})
    return reservations.admin_view(updated)


# ---------- certificates (owners and staff) ----------

class CertificateFields(BaseModel):
    title: Text = Field(default="", max_length=200)
    lab: Text = Field(default="", max_length=120)
    number: Text = Field(default="", max_length=120)


class CertificateCreate(CertificateFields):
    path: str = Field(max_length=500)
    content_type: str
    size_bytes: int = Field(gt=0)


@router.get("/agents/{agent_id}/items/{item_id}/certificates")
def list_certificates(agent_id: str, item_id: int, user: dict = Depends(auth.current_user)):
    _require_item(agent_id, item_id)
    return [media.admin_certificate(c) for c in database.list_certificates(item_id)]


@router.post("/agents/{agent_id}/items/{item_id}/certificates", status_code=201)
def add_certificate(
    agent_id: str, item_id: int, req: CertificateCreate, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    if req.content_type not in storage.CERTIFICATE_TYPES:
        raise HTTPException(status_code=400, detail="Certificates can be PDF, JPG, PNG or WebP.")
    _check_uploaded(item_id, req.path)
    row = database.create_certificate(item_id, req.model_dump())
    return media.admin_certificate(row)


class CertificateUpdate(BaseModel):
    title: Text | None = Field(default=None, max_length=200)
    lab: Text | None = Field(default=None, max_length=120)
    number: Text | None = Field(default=None, max_length=120)


@router.patch("/agents/{agent_id}/items/{item_id}/certificates/{certificate_id}")
def update_certificate(
    agent_id: str, item_id: int, certificate_id: int, req: CertificateUpdate,
    user: dict = Depends(auth.current_user),
):
    """Update only the fields sent, so quick edits to different fields can't
    overwrite each other."""
    _require_item(agent_id, item_id)
    if not database.get_certificate(item_id, certificate_id):
        raise HTTPException(status_code=404, detail="Certificate not found")
    fields = req.model_dump(exclude_none=True)
    row = database.update_certificate(item_id, certificate_id, fields) if fields else database.get_certificate(item_id, certificate_id)
    return media.admin_certificate(row)


@router.delete("/agents/{agent_id}/items/{item_id}/certificates/{certificate_id}", status_code=204)
def delete_certificate(
    agent_id: str, item_id: int, certificate_id: int, user: dict = Depends(auth.current_user)
):
    _require_item(agent_id, item_id)
    row = database.delete_certificate(item_id, certificate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found")
    _delete_files([row])
