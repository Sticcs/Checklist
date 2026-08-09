# Checklist

A todo-list app: FastAPI backend + React (Vite + TypeScript) frontend, backed by SQLite.

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
