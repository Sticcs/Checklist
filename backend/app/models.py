from pydantic import BaseModel


# ----------------------------- Auth -----------------------------

class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = True


class UserResponse(BaseModel):
    username: str
    is_guest: bool


# ----------------------------- Desktop <-> website sync -----------------------------

class SyncRequest(BaseModel):
    # Both optional: present when the user is (re)linking with a website
    # account's credentials, absent when the desktop app's autosave/Ctrl+S/
    # exit-save prompt is reusing the account already linked from a previous
    # call (see routers/auth.py's _resolve_website_credentials).
    username: str | None = None
    password: str | None = None


class WebsiteLinkResponse(BaseModel):
    linked: bool
    username: str | None = None


# ----------------------------- Subtasks -----------------------------

class SubtaskCreate(BaseModel):
    text: str


class SubtaskDoneUpdate(BaseModel):
    done: bool


class SubtaskUrgentUpdate(BaseModel):
    urgent: bool


class SubtaskDueDateUpdate(BaseModel):
    due_date: str | None = None


class SubtaskNotesUpdate(BaseModel):
    notes: str


class Subtask(BaseModel):
    id: int
    task_id: int
    text: str
    done: bool
    created_at: str
    urgent: bool
    due_date: str | None = None
    notes: str | None = None


class SubtaskMutationResponse(BaseModel):
    subtask: Subtask | None = None
    parent_done: bool


# ----------------------------- Tasks -----------------------------

class TaskCreate(BaseModel):
    text: str
    priority: str
    category: str
    due_date: str | None = None


class TaskUpdate(BaseModel):
    text: str
    priority: str
    category: str
    due_date: str | None = None


class TaskDoneUpdate(BaseModel):
    done: bool


class TaskPinnedUpdate(BaseModel):
    pinned: bool


class TaskPositionUpdate(BaseModel):
    position: float


class TaskNotesUpdate(BaseModel):
    notes: str


class TaskUrgentUpdate(BaseModel):
    urgent: bool


class TaskDueDateUpdate(BaseModel):
    due_date: str | None = None


class TaskAssignUpdate(BaseModel):
    # The id of the plain task this (assessment) task should be filed
    # under, or None to unassign it - see routers/tasks.py's /assign.
    assigned_task_id: int | None = None


class Task(BaseModel):
    id: int
    text: str
    done: bool
    priority: str
    category: str
    due_date: str | None
    created_at: str
    username: str
    pinned: bool
    position: float
    notes: str | None
    urgent: bool
    assigned_task_id: int | None = None
    subtasks: list[Subtask] = []


class TasksResponse(BaseModel):
    tasks: list[Task]
    can_undo: bool
    can_redo: bool


class MarkAllCompletedResponse(BaseModel):
    updated_count: int


class ClearResponse(BaseModel):
    deleted_count: int


# ----------------------------- Export / Import -----------------------------
# A deliberately portable subset of Task/Subtask - no id, task_id, username,
# created_at, or position, since those are meaningless (or actively wrong,
# e.g. an id colliding with one already in the target database) once the
# data moves to a different account/database, which is exactly the point of
# export/import (see the desktop app's offline database - README.md).

class ExportedSubtask(BaseModel):
    text: str
    done: bool = False
    urgent: bool = False
    due_date: str | None = None
    notes: str | None = None


class ExportedTask(BaseModel):
    # id is the *original* database id - never reused as-is on import (which
    # always inserts fresh rows), but needed to remap assigned_task_id
    # references (an assessment "filed under" a task, see
    # set_task_assignment) from old ids to whatever new ids that import
    # generates. See crud.import_data. Optional (not just for a partial/
    # hand-built import payload, but because export files captured before
    # this field existed don't have it) - assigned_task_id references just
    # can't be resolved without it, which import_data already handles by
    # leaving them unset rather than failing the whole import.
    id: int | None = None
    text: str
    priority: str
    category: str
    due_date: str | None = None
    done: bool = False
    pinned: bool = False
    urgent: bool = False
    notes: str | None = None
    assigned_task_id: int | None = None
    subtasks: list[ExportedSubtask] = []


class ExportPayload(BaseModel):
    version: int = 1
    exported_at: str
    tasks: list[ExportedTask]


class ImportResponse(BaseModel):
    imported_tasks: int
    imported_subtasks: int


# ----------------------------- Activity -----------------------------

class ActivityEntry(BaseModel):
    id: int
    action: str
    detail: str
    created_at: str


# ----------------------------- Stats -----------------------------

class DailyCount(BaseModel):
    date: str
    count: int


class StatsResponse(BaseModel):
    current_streak: int
    longest_streak: int
    completed_today: int
    completed_this_week: int
    total_completed: int
    daily_counts: list[DailyCount]
