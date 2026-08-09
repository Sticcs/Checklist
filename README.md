# Checklist

A todo-list app: FastAPI backend + React (Vite + TypeScript) frontend, backed by SQLite
locally and Postgres in production (via SQLAlchemy Core - same query code, either database).

Originally a single-file Streamlit app; rewritten to get real component state and a real
reactive DOM instead of fighting Streamlit's full-rerun model.

## Project structure

```
backend/    FastAPI app - auth, tasks, subtasks, activity log, undo/redo (see backend/app/main.py)
frontend/   React app - Vite + TypeScript + React Query (see frontend/src/App.tsx)
checklist.db  Shared SQLite database (both services read/write the same file)
```

## Running locally

Requires Python 3.11+ and Node.js (LTS).

**Backend** (from `backend/`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runs on `http://localhost:8000`.

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev
```

Runs on `http://localhost:5173` and proxies `/api` to the backend, so the two stay
same-origin (needed for the session cookie).

Open `http://localhost:5173` and use both together.

## Deploying (Render + Postgres)

The whole app deploys as a single Docker image: FastAPI serves the built React app
directly (see the catch-all route in `backend/app/main.py`), so there's one origin, one
deployment, and no CORS/cross-site cookie config to worry about. `Dockerfile` builds the
frontend in one stage and copies it into the Python runtime stage.

Render's free web service tier has no persistent disk, so production uses Postgres
instead of the local SQLite file. The backend's SQL layer (`backend/app/db.py`,
`backend/app/crud.py`) runs on SQLAlchemy Core: with no `DATABASE_URL` set it falls back
to SQLite (`checklist.db`, zero setup - this is what local dev still uses), and with
`DATABASE_URL` set it talks to Postgres instead. Tables are created automatically on
startup either way.

One-time setup:

1. Create a free Postgres database on [Neon](https://neon.tech) or
   [Supabase](https://supabase.com) and copy its connection string (`postgresql://...`).
   Free-tier databases on both pause after a period of inactivity and take a moment to
   wake up on the next request - normal, not a bug.
2. On [Render](https://render.com), create a new Web Service from this repo. It will pick
   up `render.yaml` automatically:
   - `SECRET_KEY` is generated for you.
   - `COOKIE_SECURE` is set to `true` (required for the auth cookie over HTTPS).
   - `DATABASE_URL` - paste the Postgres connection string from step 1.
3. Deploy. Every push to the connected branch redeploys automatically after that.

## Tests

Backend tests run against a throwaway temp database, never `checklist.db`:

```bash
cd backend && source .venv/bin/activate
pytest tests/
```

## Notes

- Auth is a signed httpOnly cookie (`itsdangerous`), not JWT/localStorage - avoids XSS token
  theft, and stays same-origin so no CORS config is needed in dev or prod.
- "Continue as Guest" mints a unique `guest_<id>` identity per session, so separate guest
  logins never see each other's tasks.
- Undo/redo is an in-memory per-user snapshot stack on the backend (`backend/app/undo.py`) -
  it resets on server restart, same as the original Streamlit session-state behavior.
- The database is picked by `DATABASE_URL`: unset locally (falls back to the
  `checklist.db` SQLite file), set in production (Postgres). See `backend/app/db.py`.
