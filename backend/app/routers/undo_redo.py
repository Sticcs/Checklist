from fastapi import APIRouter, Depends, HTTPException, status

from app import crud, undo
from app.models import TasksResponse
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["undo"])


def _visible_tasks(tasks: list[dict], viewer_username: str) -> list[dict]:
    # A task owner can still have collaborator-added links hidden from them
    # (see crud.visible_links) - filtering here isn't redundant just because
    # undo/redo only ever touch the caller's own tasks.
    for task in tasks:
        task["links"] = crud.visible_links(task.get("links", []), viewer_username)
    return tasks


@router.post("/undo", response_model=TasksResponse)
def do_undo(current_user: CurrentUser = Depends(get_current_user)) -> TasksResponse:
    if not undo.undo(current_user.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to undo")
    tasks = _visible_tasks(crud.get_tasks_with_subtasks(current_user.username), current_user.username)
    can_undo, can_redo = undo.status(current_user.username)
    return TasksResponse(tasks=tasks, can_undo=can_undo, can_redo=can_redo)


@router.post("/redo", response_model=TasksResponse)
def do_redo(current_user: CurrentUser = Depends(get_current_user)) -> TasksResponse:
    if not undo.redo(current_user.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to redo")
    tasks = _visible_tasks(crud.get_tasks_with_subtasks(current_user.username), current_user.username)
    can_undo, can_redo = undo.status(current_user.username)
    return TasksResponse(tasks=tasks, can_undo=can_undo, can_redo=can_redo)
