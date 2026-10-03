from fastapi import APIRouter, Depends, HTTPException, status

from app import crud, undo
from app.models import (
    ClearResponse,
    LinkHiddenUpdate,
    MarkAllCompletedResponse,
    PageCreate,
    PageRename,
    SubtaskCreate,
    SubtaskMutationResponse,
    Task,
    TaskAssignUpdate,
    TaskCreate,
    TaskDoneUpdate,
    TaskDueDateUpdate,
    TaskInProgressUpdate,
    TaskLinksUpdate,
    TaskListIdUpdate,
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


def _require_movable_list(list_id: int, username: str) -> dict:
    """A task's list_id may only point at a 'main' or 'custom' list owned
    by the caller - the built-in 'shopping' list is never a valid target,
    since its items are found by category alone (see crud.py's Lists
    section), not list_id."""
    target_list = crud.get_list(list_id, username)
    if target_list is None or target_list["kind"] not in ("main", "custom"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return target_list


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


def _visible_task(task: dict, viewer_username: str) -> dict:
    """Filters a task's links down to what this particular viewer should
    see (see crud.visible_links) - a hidden link only stays visible to the
    collaborator who added it. Must wrap every Task-shaped response this
    router returns, since a task's links can include ones added (and
    hidden) by a collaborator other than whoever is fetching it."""
    task["links"] = crud.visible_links(task.get("links", []), viewer_username)
    return task


def _visible_tasks(tasks: list[dict], viewer_username: str) -> list[dict]:
    for task in tasks:
        _visible_task(task, viewer_username)
    return tasks


@router.get("", response_model=TasksResponse)
def list_tasks(current_user: CurrentUser = Depends(get_current_user)) -> TasksResponse:
    tasks = crud.get_tasks_with_subtasks(current_user.username)
    can_undo, can_redo = undo.status(current_user.username)
    return TasksResponse(tasks=_visible_tasks(tasks, current_user.username), can_undo=can_undo, can_redo=can_redo)


@router.get("/shared-with-me", response_model=list[Task])
def shared_with_me(current_user: CurrentUser = Depends(get_current_user)) -> list[Task]:
    # Registered before GET /{task_id} below - Starlette matches path
    # operations in registration order, so "shared-with-me" must be listed
    # first or it would be swallowed by {task_id}.
    return _visible_tasks(crud.get_shared_with_me(current_user.username), current_user.username)


@router.get("/{task_id}", response_model=Task)
def get_single_task(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    # Owner-or-collaborator gated (see _require_task_access) - used by the
    # frontend's AssignmentWorkspace for its periodic poll refresh, which
    # collaborators also need since they have no other single-task fetch.
    task = _require_task_access(task_id, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Task)
def create_task(body: TaskCreate, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Task text is required")
    if body.list_id is not None:
        _require_movable_list(body.list_id, current_user.username)
    task = crud.add_task(
        text, body.priority, body.category, body.due_date, current_user.username, list_id=body.list_id
    )
    task["subtasks"] = []
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}", response_model=Task)
def edit_task(
    task_id: int, body: TaskUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.update_task(
        task_id, body.text.strip(), body.priority, body.category, body.due_date, current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


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
    task = crud.set_done(task_id, body.done, owner_task["username"], actor_username=current_user.username)
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
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/pin", response_model=Task)
def toggle_pinned(
    task_id: int, body: TaskPinnedUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_pinned(task_id, body.pinned, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/position", response_model=Task)
def reposition_task(
    task_id: int, body: TaskPositionUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_position(task_id, body.position, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/list", response_model=Task)
def move_task(
    task_id: int, body: TaskListIdUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    _require_movable_list(body.list_id, current_user.username)
    task = crud.set_task_list_id(task_id, body.list_id, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/notes", response_model=Task)
def update_task_notes(
    task_id: int, body: TaskNotesUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_notes(task_id, body.notes, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/urgent", response_model=Task)
def toggle_task_urgent(
    task_id: int, body: TaskUrgentUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_urgent(task_id, body.urgent, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/in-progress", response_model=Task)
def toggle_task_in_progress(
    task_id: int, body: TaskInProgressUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_task_in_progress(task_id, body.in_progress, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/links", response_model=Task)
def update_task_links(
    task_id: int, body: TaskLinksUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    # Collaborator-accessible - see toggle_done's comment on owner_task["username"].
    # A new link added here with no id (the model defaults to "") gets one
    # assigned before saving - the frontend only ever omits it for a
    # brand-new link, never an existing one round-tripped from a GET.
    owner_task = _require_task_access(task_id, current_user.username)
    links = []
    for link in body.links:
        d = link.model_dump()
        if not d["id"]:
            d["id"] = crud.new_link_id()
        if not d["added_by"]:
            d["added_by"] = current_user.username
        links.append(d)
    # This is a whole-array replacement endpoint, but the client only ever
    # sees its own filtered view (crud.visible_links) - submitting that back
    # verbatim would silently delete any link another collaborator has
    # hidden from this viewer. Re-attach whatever's hidden from this viewer
    # before saving, so one person's edit can't destroy another's.
    visible_ids = {link["id"] for link in crud.visible_links(owner_task["links"], current_user.username)}
    hidden_from_viewer = [link for link in owner_task["links"] if link["id"] not in visible_ids]
    task = crud.set_task_links(
        task_id, links + hidden_from_viewer, owner_task["username"], actor_username=current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/links/{link_id}/hidden", response_model=Task)
def set_link_hidden(
    task_id: int, link_id: str, body: LinkHiddenUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    owner_task = _require_task_access(task_id, current_user.username)
    link = next((link for link in owner_task["links"] if link["id"] == link_id), None)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    if link["added_by"] != current_user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the collaborator who added a link can hide it")
    task = crud.set_link_hidden(
        task_id, link_id, body.hidden, owner_task["username"], actor_username=current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/pages", response_model=Task)
def update_task_pages(
    task_id: int, body: TaskPagesUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    # Collaborator-accessible - see toggle_done's comment on owner_task["username"].
    # Whole-array replacement, used only by the debounced content-autosave
    # path - see TaskPagesUpdate's own comment. Structural edits (add/
    # delete/rename a page) use the three dedicated routes below instead,
    # each of which (unlike this one) pushes an undo snapshot first.
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.set_task_pages(
        task_id, [page.model_dump() for page in body.pages], owner_task["username"], actor_username=current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.post("/{task_id}/pages", response_model=Task, status_code=status.HTTP_201_CREATED)
def add_page(task_id: int, body: PageCreate, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.add_task_page(task_id, body.title, owner_task["username"], actor_username=current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.delete("/{task_id}/pages/{page_id}", response_model=Task)
def delete_page(task_id: int, page_id: str, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.delete_task_page(task_id, page_id, owner_task["username"], actor_username=current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/pages/{page_id}", response_model=Task)
def rename_page(
    task_id: int, page_id: str, body: PageRename, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    owner_task = _require_task_access(task_id, current_user.username)
    task = crud.rename_task_page(
        task_id, page_id, body.title, owner_task["username"], actor_username=current_user.username
    )
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


@router.patch("/{task_id}/due-date", response_model=Task)
def update_task_due_date(
    task_id: int, body: TaskDueDateUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> Task:
    _require_task(task_id, current_user.username)
    task = crud.set_due_date(task_id, body.due_date, current_user.username)
    task["subtasks"] = crud.get_subtasks(task_id)
    return _visible_task(task, current_user.username)


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
    return _visible_task(task, current_user.username)


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
    subtask, parent_done = crud.add_subtask(
        task_id, text, owner_task["username"], actor_username=current_user.username
    )
    return SubtaskMutationResponse(subtask=subtask, parent_done=parent_done)
