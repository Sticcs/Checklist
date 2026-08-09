from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routers import activity, auth, subtasks, tasks, undo_redo


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Checklist API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(subtasks.router)
app.include_router(activity.router)
app.include_router(undo_redo.router)
