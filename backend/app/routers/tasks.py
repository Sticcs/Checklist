from fastapi import APIRouter, Depends, HTTPException, status

from app import crud, undo
from app.models import (
    ClearResponse,
    MarkAllCompletedResponse,
    SubtaskCreate,
    SubtaskMutationResponse,
    Task,
    TaskAssignUpdate,
    TaskCreate,
    TaskDoneUpdate,
    TaskDueDateUpdate,
    TaskInProgressUpdate,
    TaskLinksUpdate,
    TaskNotesUpdate,
    TaskPagesUpdate,
    TaskPinnedUpdate,
    TaskPositionUpdate,
    TasksResponse,
    TaskUpdate,
    TaskUrgentUpdate,
)
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _require_task(task_id: int, username: str) -> dict:
    task = crud.get_task(task_id, username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


def _require_task_access(task_id: int, username: str) -> dict:
    """Like _require_task, but also allows an assignment collaborator (see
    crud.get_task_for_user) - not just the owner. The returned dict's
    "username" is always the task's real owner: every downstream crud call
    must be passed task["username"], never the caller's own username,
    since every crud mutation filters its WHERE clause by whichever
    username it's given."""
    task = crud.get_task_for_user(task_id, username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@router.get("", response_model=TasksResponse)
def list_tasks(current_user: CurrentUser = Depends(get_current_user)) -> TasksResponse:
    tasks = crud.get_tasks_with_subtasks(current_user.username)
    can_undo, can_redo = undo.status(current_user.username)
    return TasksResponse(tasks=tasks, can_undo=can_undo, can_redo=can_redo)


@router.get("/shared-with-me", response_model=list[Task])
def shared_with_me(current_user: CurrentUser = Depends(get_current_user)) -> list[Task]:
    # Registered before GET /{task_id} below - Starlette matches path
    # operations in registration order, so "shared-with-me" must be listed
    # first or it would be swallowed by {task_id}.
    return crud.get_shared_with_me(current_user.username)


@router.get("/{task_id}", response_model=Task)
def get_single_task(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    # Owner-or-collaborator gated (see _require_task_access) - used by the
    # frontend's AssignmentWorkspace for its periodic poll refresh, which
    # collaborators also need since they have no other single-task fetch.
    task = _require_task_access(task_id, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Task)
def create_task(body: TaskCreate, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task text is required")
    if body.list_id is not None:
        # Must belong to the caller and be a real 'custom' list - the
        # built-in 'shopping' list is never targeted by list_id (its items
        # are found by category alone, see crud.py's Lists section).
        target_list = crud.get_list(body.list_id, current_user.username)
        if target_list is None or target_list["kind"] != "custom":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    task = crud.add_task(
        text, body.priority, body.category, body.due_date, current_user.username, list_id=body.list_id
    )
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
    # Collaborator-accessible (see _require_task_access) - AssignmentWorkspace's
    # "Mark as Finished" button. owner_task["username"] (not current_user.username)
    # is threaded into crud.set_done since every crud mutation filters by
    # whichever username it's given, and a collaborator's own username won't
    # match the row's owner column.
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.set_done(task_id, body.done, owner_task["username"])
    task["subtasks"] = crud.get_subtasks(task_id)
    # Notify the owner when a collaborator (not the owner themselves) checks
    # something off - gated on a real false->true transition (owner_task's
    # prior "done" is already in hand, no extra query needed) so repeatedly
    # marking an already-done item doesn't spam a new notification per call.
    if current_user.username != owner_task["username"] and body.done and not owner_task["done"]:
        crud.create_notification(
            owner_task["username"],
            "item_checked",
            f'{current_user.username} checked off "{owner_task["text"]}"',
            actor_username=current_user.username,
            task_id=task_id,
        )
    return task


@router.patch("/{task_id}/pin", response_model=Task)
def toggle_pinned(
    task_id: int, body: TaskPinnedUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_pinned(task_id, body.pinned, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/position", response_model=Task)
def reposition_task(
    task_id: int, body: TaskPositionUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_position(task_id, body.position, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/notes", response_model=Task)
def update_task_notes(
    task_id: int, body: TaskNotesUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_notes(task_id, body.notes, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/urgent", response_model=Task)
def toggle_task_urgent(
    task_id: int, body: TaskUrgentUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_urgent(task_id, body.urgent, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/in-progress", response_model=Task)
def toggle_task_in_progress(
    task_id: int, body: TaskInProgressUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_in_progress(task_id, body.in_progress, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/links", response_model=Task)
def update_task_links(
    task_id: int, body: TaskLinksUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    # Collaborator-accessible - see toggle_done's comment on owner_task["username"].
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.set_task_links(task_id, [link.model_dump() for link in body.links], owner_task["username"])
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/pages", response_model=Task)
def update_task_pages(
    task_id: int, body: TaskPagesUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    # Collaborator-accessible - see toggle_done's comment on owner_task["username"].
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.set_task_pages(task_id, [page.model_dump() for page in body.pages], owner_task["username"])
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/due-date", response_model=Task)
def update_task_due_date(
    task_id: int, body: TaskDueDateUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_due_date(task_id, body.due_date, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return task


@router.patch("/{task_id}/assign", response_model=Task)
def assign_task(
    task_id: int, body: TaskAssignUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    # task_id here is the assessment; body.assigned_task_id is the plain
    # task it's being filed under (or None to unassign) - see
    # crud.set_task_assignment's docstring. Both existence/ownership checks
    # happen here (the same _require_task every other route in this file
    # uses), so crud.set_task_assignment can just trust task_id and a
    # non-None assigned_task_id both already belong to this user.
    _require_task(task_id, current_user.username)
    if body.assigned_task_id is not None:
        _require_task(body.assigned_task_id, current_user.username)
    task = crud.set_task_assignment(task_id, body.assigned_task_id, current_user.username)
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
    # Collaborator-accessible - see toggle_done's comment on owner_task["username"].
    owner_task = _require_task_access(task_id, current_user.username)
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subtask text is required")
    subtask, parent_done = crud.add_subtask(task_id, text, owner_task["username"])
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)
