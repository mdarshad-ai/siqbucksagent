"""Admin API: login, inventory, agent personas, and user management."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, StringConstraints

import auth
import database
from agent_config import CORE_RULES
from chat_core import ChatMessage, ChatResponse, NonEmptyStr, run_chat

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


@router.get("/agents/{agent_id}/items")
def list_items(agent_id: str, user: dict = Depends(auth.current_user)):
    _require_agent(agent_id)
    return database.list_items(agent_id)


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
    if not database.delete_item(agent_id, item_id):
        raise HTTPException(status_code=404, detail="Stone not found")


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
