from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.db import init_db
from app.paths import resource_path
from app.routers import activity, auth, data, stats, subtasks, tasks, undo_redo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Checklist API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(subtasks.router)
app.include_router(activity.router)
app.include_router(stats.router)
app.include_router(undo_redo.router)
app.include_router(data.router)

# Serves the built React app (frontend/dist, produced by `npm run build`) so
# the whole thing is one deployment on one origin - no CORS, no cross-site
# cookie config, the auth cookie logic stays exactly what local dev already
# uses. Registered last: Starlette matches routes in registration order, so
# the /api/* routers above always win before this catch-all is even tried.
# In local dev this directory won't exist (Vite serves the frontend itself
# with its own dev server), so it's skipped entirely rather than erroring.
# In a frozen desktop build, resource_path() resolves this inside the
# PyInstaller bundle instead (see checklist.spec's `datas`).
FRONTEND_DIST = resource_path("frontend", "dist")

if FRONTEND_DIST.is_dir():

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
