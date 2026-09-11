from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.models import (
    SubtaskAssigneeUpdate,
    SubtaskDoneUpdate,
    SubtaskDueDateUpdate,
    SubtaskMutationResponse,
    SubtaskNotesUpdate,
    SubtaskUrgentUpdate,
)
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/subtasks", tags=["subtasks"])


def _require_owning_task(subtask_id: int, username: str) -> int:
    task_id = crud.get_subtask_owning_task_id(subtask_id)
    if task_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subtask not found")
    if crud.get_task(task_id, username) is None:
        # The subtask exists but doesn't belong (via its parent task) to this
        # user - report it the same as "not found" rather than leaking that a
        # subtask id exists at all.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subtask not found")
    return task_id


def _require_owning_task_access(subtask_id: int, username: str) -> tuple[int, str]:
    """Like _require_owning_task, but also allows an assignment collaborator
    (see crud.get_task_for_user via tasks.py's _require_task_access). Returns
    (task_id, owner_username) - callers must pass owner_username, not
    `username`, into every downstream crud call, same reasoning as tasks.py's
    _require_task_access."""
    task_id = crud.get_subtask_owning_task_id(subtask_id)
    if task_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subtask not found")
    task = crud.get_task_for_user(task_id, username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subtask not found")
    return task_id, task["username"]


@router.patch("/{subtask_id}", response_model=SubtaskMutationResponse)
def toggle_subtask_done(
    subtask_id: int, body: SubtaskDoneUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    task_id, owner_username = _require_owning_task_access(subtask_id, current_user.username)
    subtask, parent_done = crud.set_subtask_done(subtask_id, task_id, body.done, owner_username)
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)


@router.patch("/{subtask_id}/urgent", response_model=SubtaskMutationResponse)
def toggle_subtask_urgent(
    subtask_id: int, body: SubtaskUrgentUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    task_id = _require_owning_task(subtask_id, current_user.username)
    subtask = crud.set_subtask_urgent(subtask_id, body.urgent, current_user.username)
    task = crud.get_task(task_id, current_user.username)
    parent_done = bool(task["done"]) if task else False
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)


@router.patch("/{subtask_id}/due-date", response_model=SubtaskMutationResponse)
def update_subtask_due_date(
    subtask_id: int, body: SubtaskDueDateUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    task_id = _require_owning_task(subtask_id, current_user.username)
    subtask = crud.set_subtask_due_date(subtask_id, body.due_date, current_user.username)
    task = crud.get_task(task_id, current_user.username)
    parent_done = bool(task["done"]) if task else False
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)


@router.patch("/{subtask_id}/notes", response_model=SubtaskMutationResponse)
def update_subtask_notes(
    subtask_id: int, body: SubtaskNotesUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    task_id = _require_owning_task(subtask_id, current_user.username)
    subtask = crud.set_subtask_notes(subtask_id, body.notes)
    task = crud.get_task(task_id, current_user.username)
    parent_done = bool(task["done"]) if task else False
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)


@router.patch("/{subtask_id}/assignee", response_model=SubtaskMutationResponse)
def update_subtask_assignee(
    subtask_id: int, body: SubtaskAssigneeUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    # Collaborator-accessible - same mini task panel toggle_subtask_done and
    # remove_subtask already are (see _require_owning_task_access).
    task_id, owner_username = _require_owning_task_access(subtask_id, current_user.username)
    assignee = body.assigned_username
    if assignee is not None and assignee != owner_username and not crud.is_collaborator(task_id, assignee):
        # Don't trust the picker UI to only ever offer valid choices -
        # assignee must be the owner or a current collaborator.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a collaborator on this assignment")
    subtask = crud.set_subtask_assignee(subtask_id, assignee, owner_username)
    task = crud.get_task(task_id, owner_username)
    parent_done = bool(task["done"]) if task else False
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)


@router.delete("/{subtask_id}", response_model=SubtaskMutationResponse)
def remove_subtask(
    subtask_id: int, current_user: CurrentUser = Depends(get_current_user)
) -> SubtaskMutationResponse:
    task_id, owner_username = _require_owning_task_access(subtask_id, current_user.username)
    parent_done = crud.delete_subtask(subtask_id, task_id, owner_username)
    return SubtaskMutationResponse(subtask=None, parent_done=parent_done)
