# The Gem Exchange — Two Sales Agents

A small full-stack demo: two animated "dealer" agents — Siq at *Pacific
Gems* and Bucks at *Bucks' Exchange* — each backed by an LLM (via
OpenRouter) and its own SQLite inventory. Click a counter to chat; the
agent looks up real stock and prices via tool calls before answering.

```
sales-agents-app/
├── backend/     FastAPI + SQLite + OpenRouter tool-calling
└── frontend/    React (Vite) + animated SVG characters
```

## The two agents

- **Siq — Pacific Gems**: sells a small, curated line of certified fine
  gemstones (sapphires, emeralds, rubies, etc.), all sourced through one
  supplier. If he doesn't carry it, he says so and won't improvise a
  substitute source.
- **Bucks — Bucks' Exchange**: sells a higher-turnover, multi-origin stock
  of gems and mineral specimens. He's allowed to offer to *try* to source
  something he doesn't currently have, but his system prompt keeps him
  from quoting a firm price or promising anything he hasn't actually
  verified in the database.

Both agents can only state facts (name, price, stock, origin) that come
back from a tool call against their own inventory table — the system
prompt tells them never to invent these from memory, so this is enforced
by instruction, not by a hard technical constraint. Good enough for a demo;
see the hardening notes at the bottom before treating it as a source of
truth for real prices.

## 1. Get an OpenRouter API key

Sign up at https://openrouter.ai, create a key, and add credit (or use a
free-tier model). You have two ways to give it to the backend:

- **Env var** — set `OPENROUTER_API_KEY` directly (in `.env`, or as a
  platform env var when deployed).
- **Token file** — put the key alone in a plain text file (e.g. `token.txt`)
  and set `OPENROUTER_API_KEY_FILE` to its path. This is what
  `backend/llm_service.py` reads if `OPENROUTER_API_KEY` isn't set — handy
  if you keep secrets in your own file rather than `.env`. Either works;
  you only need one.

Also check https://openrouter.ai/models for a model slug that supports
tool/function calling, and set `OPENROUTER_MODEL` if you don't want the
default (`anthropic/claude-sonnet-4.5`).

## 2. Run it locally

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY (or OPENROUTER_API_KEY_FILE)
uvicorn main:app --reload --port 8000
```

The first run creates `inventory.db` next to `main.py` and seeds it with
both agents' items automatically. Visit http://localhost:8000/api/agents
to sanity check.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_URL=http://localhost:8000 is already correct for local
npm run dev
```

Open http://localhost:5173 — you should see two lantern-lit counters.

### Tests

The backend tests mock the model, so they need no API key or network:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## 3. How it works

- `backend/agent_config.py` — each agent's persona (system prompt) and
  visual theme (colors, used by the frontend).
- `backend/database.py` — SQLite schema + seed data + query helpers, one
  `inventory` table with an `agent_id` column (`siq` / `bucks`).
- `backend/llm_service.py` — the OpenRouter call, using the OpenAI-compatible
  SDK pointed at `https://openrouter.ai/api/v1`. Each agent is given two
  tools, `search_inventory` and `get_item_details`, implemented to only ever
  query *that agent's own* rows — this is what stops an agent from
  inventing stock or "seeing" the other agent's items.
- `backend/main.py` — three endpoints: `GET /api/agents`,
  `GET /api/agents/{id}/inventory`, `POST /api/chat`.
- Conversation history is kept client-side and replayed on every request
  (stateless backend) — simplest thing that works for a demo. Swap this for
  a session id + a `conversations` table if you want real persistence.
- `frontend/src/components/Character.jsx` — the animated SVG dealer figure
  (idle bob + lantern flicker always; a talking-mouth + glow pulse while
  waiting for a reply).

## 4. Add or change inventory

Edit `SIQ_ITEMS` / `BUCKS_ITEMS` in `backend/database.py` and delete the
existing `inventory.db` file (it's only seeded when the table is empty), or
add a small admin script if you want to edit it without restarting.

## 5. Deploy — Railway (recommended for a first deploy)

Push this whole folder to a GitHub repo, then in Railway:

**Backend service**
1. New Project → Deploy from GitHub repo → select the repo.
2. Set the service's root directory to `backend`.
3. Railway auto-detects Python; set the start command to:
   `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables: `OPENROUTER_API_KEY` (or upload a token file
   into the repo/volume and set `OPENROUTER_API_KEY_FILE`), `OPENROUTER_MODEL`
   if you're overriding the default, and `FRONTEND_ORIGIN` (fill this in
   after the frontend is deployed — comma-separated if you need more than
   one origin).
5. Deploy. Note the public URL Railway gives you, e.g.
   `https://your-backend.up.railway.app`.

**Frontend service**
1. In the same Railway project, "New Service" → same GitHub repo, but set
   root directory to `frontend`.
2. Build command: `npm install && npm run build`
   Start command: `npx serve -s dist -l $PORT`
   (or use Railway's static-site/Nixpacks static output option if offered).
3. Add environment variable `VITE_API_URL` = your backend's public URL from
   above. **Important:** Vite bakes env vars in at build time, so set this
   before/at deploy, not after.
4. Deploy. Then go back to the backend service and set `FRONTEND_ORIGIN` to
   this frontend's public URL, and redeploy the backend so CORS allows it.

## 6. Deploy — Render (alternative)

Same shape, two separate services:

1. **Backend**: New → Web Service → connect repo → root directory
   `backend` → build command `pip install -r requirements.txt` → start
   command `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add
   `OPENROUTER_API_KEY` (or `OPENROUTER_API_KEY_FILE`), `OPENROUTER_MODEL`,
   and `FRONTEND_ORIGIN` under Environment.
2. **Frontend**: New → Static Site → root directory `frontend` → build
   command `npm install && npm run build` → publish directory `dist`. Add
   `VITE_API_URL` under Environment (build-time), pointing at the backend's
   `.onrender.com` URL.
3. Update the backend's `FRONTEND_ORIGIN` to the frontend's `.onrender.com`
   URL once you have it, and redeploy the backend.

Render's free tier backend will spin down when idle and take ~30-60s to
wake on the first request — expected on a free plan, not a bug.

## 7. Things to harden before showing this to anyone else

- Rate-limit `/api/chat` (a public chat box wired to a paid API is an easy
  way to run up a bill).
- Move conversation history server-side (session cookie + table) instead of
  trusting the client to send it back honestly.
- Add basic input length limits on the chat endpoint.
- Never commit your token file or `.env` — both are already in
  `backend/.gitignore`.
