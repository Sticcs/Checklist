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

### Google sign-in (optional)

"Sign in with Google" (`backend/app/routers/auth.py`) is a separate, self-contained
account path - a Google-authenticated account is never merged with an existing
username/password account, even if the email matches (see
`get_or_create_google_user`'s docstring). It's entirely optional: unset, the login
route just 503s and the button still shows but errors if clicked.

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
   create an OAuth 2.0 Client ID, type "Web application." The consent screen can
   stay in "Testing" mode (add yourself, and anyone else who should be able to sign
   in, as test users) - no need to submit for verification for personal use, since
   the scopes used (`openid email profile`) aren't sensitive.
2. Add an authorized redirect URI: `<PUBLIC_BASE_URL>/api/auth/google/callback` -
   for this deployment, `https://checklist-kmtw.onrender.com/api/auth/google/callback`.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in Render's dashboard (they're
   `sync: false` in `render.yaml`, i.e. not stored in the repo). `PUBLIC_BASE_URL`
   is already set in `render.yaml` - update it there if the deployment URL ever
   changes.

This is also the one thing that makes the desktop app's data match the website's:
the app's own local server never handles Google sign-in - `frontend/src/pages/AuthPage.tsx`
points that one link at `PRODUCTION_URL` (an absolute URL, not the local server) when
running inside the desktop app (see `useIsDesktopApp`), so completing it lands the
app on the real deployed site, same account and tasks as the website. It's the only
account path that needs internet; local username/password/guest accounts are
unaffected and still fully offline.

## Building the desktop apps (Windows .exe / macOS .app)

`backend/desktop.py` runs the same FastAPI app as the web deployment, bound to
`127.0.0.1` on a free port, and shows it in a native window via
[pywebview](https://pywebview.flowrl.com/) instead of a browser tab -
everything else (routes, auth, subtasks, etc.) is identical. PyInstaller
bundles that plus the built frontend into a platform-native package -
`checklist.spec` builds whichever platform it's run on (there's no cross-
compiling: a Windows `.exe` has to be built on Windows, a macOS `.app` on
macOS).

One-time setup (from `backend/`, with the venv active):

```bash
pip install -r requirements-desktop.txt
```

On macOS this also pulls in `pyobjc` (pywebview's Cocoa/WebKit backend) via
an environment marker in `requirements-desktop.txt` - nothing extra to run.

Build (same command on both platforms):

```bash
cd frontend && npm run build && cd ../backend
pyinstaller checklist.spec
```

**Windows** lands the app at `backend/dist/ChecklistApp.exe` - a single portable
file (onefile mode), using the same artwork as the website's favicon as its icon
(regenerate `backend/icon.ico` via the command in `checklist.spec` if
`frontend/public/favicon.png` ever changes). Its database lives at
`%LOCALAPPDATA%\Checklist\checklist.db`.

**macOS** lands the app at `backend/dist/ChecklistApp.app`. Unlike Windows,
PyInstaller deprecates combining onefile mode with a `.app` bundle ("clashes
with macOS's security"), so the spec builds macOS in onedir mode instead -
`EXE()` produces just the bootloader, `COLLECT()` gathers every dependency
into `backend/dist/ChecklistApp/`, and `BUNDLE()` wraps that into the final
`.app` (icon from `backend/icon.icns` - regenerate via the command in
`checklist.spec` the same way as the `.ico`). Its database lives at
`~/Library/Application Support/Checklist/checklist.db`. The build produces an
ad-hoc code signature (enough to run locally), but it isn't notarized (that
needs a paid Apple Developer account) - see the Gatekeeper note below for
what that means for anyone downloading it.

Either platform's app is fully offline with no account syncing, independent
of both the web deployment's Postgres and local dev's `checklist.db` (see
`backend/app/paths.py`). To move tasks between it and the website, use
Export/Import in the sidebar (see below) rather than expecting the same
login to show the same data on both.

### Moving data between the website and the desktop app

Since the desktop app's database is intentionally separate (see above), the
sidebar's "💾 Export data" / "📤 Import data" buttons (`backend/app/routers/data.py`,
`frontend/src/components/Sidebar.tsx`) are the bridge between them: Export downloads
every task, subtask, and note as a JSON file from wherever you're currently logged in
(the website or the app); Import reads that file back in, additively - it adds the
imported tasks alongside whatever's already there rather than replacing anything, so
it's safe to import into an account that isn't empty. Both buttons work identically on
the website and inside the desktop app.

### Fullscreen and the responsive layout

`F11` toggles a real OS-level fullscreen inside the packaged app (via a `pywebview`
API the frontend calls - `backend/desktop.py`'s `expose_api`,
`frontend/src/hooks/useDesktopFullscreenHotkey.ts`); a plain browser tab already owns
`F11` itself, so this only activates inside the app. Below 900px width (the app
window's minimum size, see `min_size` in `desktop.py`) the sidebar and the
scratchpad/notepad/assessments column both hide inside the desktop app specifically,
leaving just the task list - the website's own mobile layout at that width is
unchanged (stacked panels, not hidden). See the `.desktop-app` class in `index.css`.

### Publishing it as the website's download

`DownloadAppButton` (`frontend/src/components/DownloadAppButton.tsx`, hidden
automatically when the site is already running inside the desktop app itself -
see `useIsDesktopApp`) sniffs `navigator.platform`/`navigator.userAgent` to
offer the right download by default, with a small link underneath to grab the
other platform's build instead - it just links to two static files,
`frontend/public/downloads/ChecklistApp.exe` and
`frontend/public/downloads/ChecklistApp-mac.zip` (the `.app` zipped with
`ditto -c -k --sequesterRsrc --keepParent`, the Apple-recommended way to zip
a bundle so it un-zips back into a working `.app`, not `zip`/`Compress`).
Render's build is Linux-only and can't produce either one, so there's no way
to build these as part of a normal deploy - after building above, copy the
result into place by hand and redeploy:

```bash
# Windows (build already names it ChecklistApp.exe, so this is a straight copy):
cp backend/dist/ChecklistApp.exe frontend/public/downloads/ChecklistApp.exe

# macOS (zip the .app bundle first):
cd backend/dist && ditto -c -k --sequesterRsrc --keepParent ChecklistApp.app ChecklistApp-mac.zip && cd ../..
cp backend/dist/ChecklistApp-mac.zip frontend/public/downloads/ChecklistApp-mac.zip
```

Both files are committed to the repo (~65 MB / ~90 MB) so Render's Docker build
can serve them without a separate build step - if the repo's size becomes a
concern later, moving them to a GitHub Release (or other external host) and
pointing `DownloadAppButton`'s hrefs there instead is a straightforward follow-up.

**Gatekeeper on macOS:** the app isn't notarized (no paid Apple Developer
account), so a fresh download will be quarantined by macOS and refuse to open
with a plain double-click ("Apple could not verify..."). The fix is a one-time
right-click (or Control-click) → **Open** → **Open** in the confirmation dialog,
instead of double-clicking - this is standard behavior for any unsigned/
unnotarized app, not specific to this one, and only has to be done once per
machine. Mentioning this on the download button/page is worth doing if this
ships to anyone other than the developer.

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
