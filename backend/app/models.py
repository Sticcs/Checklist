from pydantic import BaseModel


# ----------------------------- Auth -----------------------------

class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    is_guest: bool


# ----------------------------- Subtasks -----------------------------

class SubtaskCreate(BaseModel):
    text: str


class SubtaskDoneUpdate(BaseModel):
    done: bool


class SubtaskUrgentUpdate(BaseModel):
    urgent: bool


class Subtask(BaseModel):
    id: int
    task_id: int
    text: str
    done: bool
    created_at: str
    urgent: bool


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
    subtasks: list[Subtask] = []


class TasksResponse(BaseModel):
    tasks: list[Task]
    can_undo: bool
    can_redo: bool


class MarkAllCompletedResponse(BaseModel):
    updated_count: int


class ClearResponse(BaseModel):
    deleted_count: int


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
