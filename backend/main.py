import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
from agent_config import get_agent, list_agents_public
from llm_service import chat_with_agent, _get_api_key

database.init_db()

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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    history: list[ChatMessage]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/agents")
def get_agents():
    return list_agents_public()


@app.get("/api/agents/{agent_id}/inventory")
def get_inventory(agent_id: str):
    if not get_agent(agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    return database.list_inventory(agent_id)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not get_agent(req.agent_id):
        raise HTTPException(status_code=404, detail="Unknown agent")
    if not _get_api_key():
        raise HTTPException(
            status_code=500,
            detail=(
                "No OpenRouter API key found. Set OPENROUTER_API_KEY, or put "
                "it in a file and set OPENROUTER_API_KEY_FILE to that path."
            ),
        )

    history_dicts = [h.model_dump() for h in req.history]
    try:
        reply, updated_history = chat_with_agent(req.agent_id, req.message, history_dicts)
    except Exception as exc:  # surface OpenRouter/model errors clearly instead of a bare 500
        raise HTTPException(status_code=502, detail=str(exc))
    return ChatResponse(reply=reply, history=updated_history)
