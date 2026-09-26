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
# edit .env: set OPENROUTER_API_KEY (or OPENROUTER_API_KEY_FILE),
# and ADMIN_EMAIL / ADMIN_PASSWORD for your /admin login
uvicorn main:app --reload --port 8000
```

The first run creates `inventory.db` (SQLite) next to `main.py` and seeds
it with both agents and their items automatically. Delete that file to
start over. Visit http://localhost:8000/api/agents
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

- `backend/agent_config.py` — the locked **core rules** every agent follows
  (check inventory with tools, never invent prices, keep sales guidance
  private), plus the default personas and starting inventory used to seed
  an empty database.
- `backend/database.py` — SQLAlchemy tables for `agents` (editable persona
  and selling style), `agent_versions` (publish history), `items` (the
  inventory, including each stone's story and private sales guidance) and
  `users` (admin logins). SQLite locally, Postgres (Supabase) in production.
- `backend/llm_service.py` — the OpenRouter call, using the OpenAI-compatible
  SDK pointed at `https://openrouter.ai/api/v1`. The system prompt is the
  agent's persona + selling style + core rules. Each agent has three tools,
  `search_inventory`, `get_item_details` and `show_item`, which only ever
  touch *that agent's own* stones; `get_item_details` also returns the
  stone's story and sales guidance, and `show_item` puts a stone card in
  the chat.
- `backend/main.py` — public endpoints: `GET /api/agents`,
  `GET /api/agents/{id}/inventory` (never includes story or guidance),
  `POST /api/chat`.
- `backend/admin_api.py` + `backend/auth.py` — the `/api/admin` endpoints
  and logins behind the admin page.
- `backend/storage.py` + `backend/media.py` — stone photos/videos: Supabase
  Storage in production (browsers upload with short-lived signed URLs), a
  local `backend/uploads/` folder in development; YouTube/Vimeo link
  parsing; and the stone cards shown in the chat.
- Conversation history is kept client-side and replayed on every request
  (stateless backend) — simplest thing that works for a demo.
- `frontend/src/admin/` — the admin page at `/admin`.
- `frontend/src/components/Character.jsx` — the animated SVG dealer figure.

## 4. Admin page: inventory, personas and users

Open `/admin` (locally: http://localhost:5173/admin). The first owner account
is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` when there are no users yet.

- **Inventory** (owners and staff): add, edit and delete each dealer's
  stones — price, stock, status (available / reserved / sold), carat, cut,
  colour, clarity, origin, treatment and certification — plus the stone's
  memory:
  - **Story**: things the dealer may tell customers (provenance, what makes
    it special, who it suits).
  - **Sales guidance**: private coaching the dealer follows but never
    quotes. Don't put real secrets here (like a floor price): an AI can
    sometimes be talked into revealing its instructions.
- **Photos & videos** (owners and staff), in each stone's edit screen:
  upload photos (JPG/PNG/WebP) and videos (MP4/MOV/WebM, up to 50 MB each),
  or add a YouTube/Vimeo link for longer videos. Set captions, drag to
  reorder (the first item is the main image), and pick a video's still
  frame. Files upload straight from the browser to Supabase Storage.
- **Stone cards in the chat**: when a dealer recommends a stone it calls the
  `show_item` tool, and the customer sees a card under the reply with the
  photos (tap for full screen), videos that play in place, price, stock and
  key details. Sold-out stones never get a card, and there are at most three
  cards per reply.
- **Agents** (owners only): edit each dealer's name, stall, tagline,
  persona and selling style. Test a draft in the preview chat (real
  inventory, customers don't see it), then **Publish**. Every publish is
  kept in the history and can be loaded back. The core rules are shown
  read-only and always apply.
- **Settings** (owners only): chat usage today and over the last 7 days,
  and the chat limits that protect your OpenRouter bill: a short-burst
  limit and a daily limit per visitor (shared IPs get 3x), a daily cap for
  the whole shop, and how many past messages are sent to the AI with each
  question. Customers who hit a limit get a friendly message in the
  dealer's voice. Counts reset at midnight UTC.
- **Users** (owners only): add owners or staff. A new user gets a one-time
  temporary password (shown once) and must choose their own at first login.
  Owners can change roles, reset passwords and remove users.

## 5. Deploy — Railway (paid after a trial)

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

## 6. Deploy — Render + Supabase (free)

`render.yaml` and the root `Dockerfile` deploy the whole app as **one free
Render web service** (the FastAPI backend serves the built React frontend
alongside `/api`). The data lives in a free **Supabase** Postgres database,
so inventory, personas and users survive restarts and redeploys.

**1. Supabase**

1. Create a project at https://supabase.com (free). Save the database
   password you choose.
2. Click **Connect** at the top of the project, and copy the
   **Session pooler** connection string. (Not "Direct connection": Render
   can't reach that one.) Replace `[YOUR-PASSWORD]` in it with your
   database password.

3. For photos and videos, copy two more values:
   - **Project URL**: Project Settings → Data API, just the
     `https://abcdefgh.supabase.co` part (anything after it, like
     `/rest/v1`, is ignored)
   - **Secret key**: Project Settings → API Keys → create or copy a
     **secret** key (`sb_secret_…`), or use the legacy `service_role` key.
     It has full access, so it only ever goes into Render, never the
     frontend or the repo.

The tables, the starting inventory and the `stone-media` storage bucket are
created automatically on the app's first start.

**2. Render**

1. Sign up at https://render.com (no credit card needed) and connect GitHub.
2. New → **Blueprint** → pick this repo. Render reads `render.yaml`.
3. Fill in the values it asks for:
   - `OPENROUTER_API_KEY` — your OpenRouter key
   - `DATABASE_URL` — the Supabase connection string from above
   - `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` — the Project URL and
     secret key from above
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD` — your first owner login (password
     at least 10 characters)
4. **Apply** and wait for the build. The shop is at the service's
   `https://….onrender.com` URL, and the admin page at `/admin`.

If the service already exists, add the same variables (plus
`ADMIN_JWT_SECRET`, any long random string) on its **Environment** page
instead, then redeploy.

Every push to `main` redeploys automatically. Things to know about the free
plans:

- Render sleeps after 15 minutes without traffic; the next visit takes
  about a minute to wake it up.
- Supabase's free plan includes 1 GB of file storage and about 5 GB of
  downloads a month. Videos only download when a customer presses play;
  15–60 second clips at 1080p (10–30 MB) keep you well inside the limits.
- Supabase pauses a free project after about a week with no activity.
  Resume it from the Supabase dashboard if the app can't reach it.
- Anyone with the URL can chat, and each chat is billed to your OpenRouter
  account. Set a credit limit on the key in OpenRouter to cap spend.

## 7. Things to harden before showing this to anyone else

- Move conversation history server-side (session cookie + table) instead of
  trusting the client to send it back honestly.
- Never commit your token file or `.env` — both are already in
  `backend/.gitignore`.
