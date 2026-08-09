from fastapi import APIRouter, Depends, HTTPException, status

from app import crud, undo
from app.models import (
    ClearResponse,
    MarkAllCompletedResponse,
    SubtaskCreate,
    SubtaskMutationResponse,
    Task,
    TaskCreate,
    TaskDoneUpdate,
    TaskPinnedUpdate,
    TasksResponse,
    TaskUpdate,
)
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _require_task(task_id: int, username: str) -> dict:
    task = crud.get_task(task_id, username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.get("", response_model=TasksResponse)
def list_tasks(current_user: CurrentUser = Depends(get_current_user)) -> TasksResponse:
    tasks = crud.get_tasks_with_subtasks(current_user.username)
    can_undo, can_redo = undo.status(current_user.username)
    return TasksResponse(tasks=tasks, can_undo=can_undo, can_redo=can_redo)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Task)
def create_task(body: TaskCreate, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task text is required")
    task = crud.add_task(text, body.priority, body.category, body.due_date, current_user.username)
    task["subtasks"] = []
    return task


@router.patch("/{task_id}", response_model=Task)
def edit_task(
    task_id: int, body: TaskUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.update_task(
        task_id, body.text.strip(), body.priority, body.category, body.due_date, current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/done", response_model=Task)
def toggle_done(
    task_id: int, body: TaskDoneUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_done(task_id, body.done, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/pin", response_model=Task)
def toggle_pinned(
    task_id: int, body: TaskPinnedUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_pinned(task_id, body.pinned, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    _require_task(task_id, current_user.username)
    crud.delete_task(task_id, current_user.username)


@router.post("/mark-all-completed", response_model=MarkAllCompletedResponse)
def mark_all_completed(current_user: CurrentUser = Depends(get_current_user)) -> MarkAllCompletedResponse:
    count = crud.mark_all_completed(current_user.username)
    return MarkAllCompletedResponse(updated_count=count)


@router.post("/clear-completed", response_model=ClearResponse)
def clear_completed(current_user: CurrentUser = Depends(get_current_user)) -> ClearResponse:
    count = crud.clear_completed(current_user.username)
    return ClearResponse(deleted_count=count)


@router.post("/clear-all", response_model=ClearResponse)
def clear_all(current_user: CurrentUser = Depends(get_current_user)) -> ClearResponse:
    count = crud.clear_all(current_user.username)
    return ClearResponse(deleted_count=count)


@router.post("/{task_id}/subtasks", status_code=status.HTTP_201_CREATED, response_model=SubtaskMutationResponse)
def create_subtask(
    task_id: int, body: SubtaskCreate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    _require_task(task_id, current_user.username)
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subtask text is required")
    subtask, parent_done = crud.add_subtask(task_id, text, current_user.username)
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)
