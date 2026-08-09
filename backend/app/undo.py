"""Per-username undo/redo stacks, re-keying main.py's st.session_state-based
model onto the authenticated username from the auth cookie (itself the direct
substitute for Streamlit's per-browser-session identity - and actually cleaner
for guests, since each guest login already mints its own unique username).

Lives in FastAPI process memory: lost on restart, and only correct with a
single uvicorn worker (the default). Both are non-regressions - st.session_state
had the identical restart-loses-history behavior - not a new limitation.
"""

from app import crud

MAX_STACK_SIZE = 20

_stacks: dict[str, dict[str, list]] = {}


def _stack_for(username: str) -> dict[str, list]:
    return _stacks.setdefault(username, {"undo": [], "redo": []})


def save_snapshot(username: str) -> None:
    stack = _stack_for(username)
    stack["undo"].append({
        "tasks": crud.get_tasks(username),
        "subtasks": crud.get_all_subtasks(username),
    })
    stack["redo"].clear()
    if len(stack["undo"]) > MAX_STACK_SIZE:
        stack["undo"].pop(0)


def status(username: str) -> tuple[bool, bool]:
    stack = _stack_for(username)
    return bool(stack["undo"]), bool(stack["redo"])


def undo(username: str) -> bool:
    stack = _stack_for(username)
    if not stack["undo"]:
        return False
    stack["redo"].append({
        "tasks": crud.get_tasks(username),
        "subtasks": crud.get_all_subtasks(username),
    })
    last_state = stack["undo"].pop()
    crud.restore_state(last_state["tasks"], username)
    crud.restore_subtasks(last_state["subtasks"], username)
    return True


def redo(username: str) -> bool:
    stack = _stack_for(username)
    if not stack["redo"]:
        return False
    stack["undo"].append({
        "tasks": crud.get_tasks(username),
        "subtasks": crud.get_all_subtasks(username),
    })
    next_state = stack["redo"].pop()
    crud.restore_state(next_state["tasks"], username)
    crud.restore_subtasks(next_state["subtasks"], username)
    return True
