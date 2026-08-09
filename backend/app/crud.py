from collections import defaultdict
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app import undo
from app.db import get_engine
from app.security import hash_password, verify_password


# ----------------------------- Auth -----------------------------

def create_user(username: str, password: str) -> bool:
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (username, password) VALUES (:username, :password)"),
                {"username": username.strip(), "password": hash_password(password)},
            )
        return True
    except IntegrityError:
        return False


def verify_user(username: str, password: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT password FROM users WHERE username = :username"),
            {"username": username.strip()},
        ).mappings().fetchone()
    return row is not None and verify_password(password, row["password"])


# ----------------------------- Row -> dict helpers -----------------------------

def _task_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    d["pinned"] = bool(d["pinned"])
    return d


def _subtask_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    return d


# ----------------------------- Reads -----------------------------

def get_tasks(username: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM tasks WHERE username = :username ORDER BY created_at DESC"),
            {"username": username},
        ).mappings().all()
    return [_task_dict(r) for r in rows]


def get_subtasks(task_id: int) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM subtasks WHERE task_id = :task_id ORDER BY created_at ASC"),
            {"task_id": task_id},
        ).mappings().all()
    return [_subtask_dict(r) for r in rows]


def get_all_subtasks(username: str) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.* FROM subtasks s
                JOIN tasks t ON s.task_id = t.id
                WHERE t.username = :username
                """
            ),
            {"username": username},
        ).mappings().all()
    return [_subtask_dict(r) for r in rows]


def get_tasks_with_subtasks(username: str) -> list[dict]:
    tasks = get_tasks(username)
    subtasks_by_task = defaultdict(list)
    for s in get_all_subtasks(username):
        subtasks_by_task[s["task_id"]].append(s)
    for t in tasks:
        t["subtasks"] = subtasks_by_task.get(t["id"], [])
    return tasks


def _get_task_text(conn, task_id: int) -> str:
    row = conn.execute(
        text("SELECT text FROM tasks WHERE id = :id"), {"id": task_id}
    ).mappings().fetchone()
    return row["text"] if row else "(unknown task)"


def get_task(task_id: int, username: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM tasks WHERE id = :id AND username = :username"),
            {"id": task_id, "username": username},
        ).mappings().fetchone()
    return _task_dict(row) if row else None


def get_subtask_owning_task_id(subtask_id: int) -> int | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT task_id FROM subtasks WHERE id = :id"), {"id": subtask_id}
        ).mappings().fetchone()
    return row["task_id"] if row else None


# ----------------------------- Activity log -----------------------------

def log_activity(username: str, action: str, detail: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO activity_log (username, action, detail, created_at) "
                "VALUES (:username, :action, :detail, :created_at)"
            ),
            {"username": username, "action": action, "detail": detail, "created_at": datetime.now().isoformat()},
        )


def get_activity_log(username: str, limit: int = 15) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM activity_log WHERE username = :username "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"username": username, "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


# ----------------------------- Undo/redo restore -----------------------------

def restore_state(state_tasks: list[dict], username: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE username = :username"), {"username": username})
        for t in state_tasks:
            conn.execute(
                text(
                    "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at, username, pinned) "
                    "VALUES (:id, :text, :done, :priority, :category, :due_date, :created_at, :username, :pinned)"
                ),
                {
                    "id": t["id"],
                    "text": t["text"],
                    "done": int(t["done"]),
                    "priority": t["priority"],
                    "category": t["category"],
                    "due_date": t["due_date"],
                    "created_at": t["created_at"],
                    "username": username,
                    "pinned": int(t.get("pinned", False)),
                },
            )


def restore_subtasks(state_subtasks: list[dict], username: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        task_ids = [
            r["id"]
            for r in conn.execute(
                text("SELECT id FROM tasks WHERE username = :username"), {"username": username}
            ).mappings().all()
        ]
        if task_ids:
            stmt = text("DELETE FROM subtasks WHERE task_id IN :task_ids").bindparams(
                bindparam("task_ids", expanding=True)
            )
            conn.execute(stmt, {"task_ids": task_ids})
        for s in state_subtasks:
            conn.execute(
                text(
                    "INSERT INTO subtasks (id, task_id, text, done, created_at) "
                    "VALUES (:id, :task_id, :text, :done, :created_at)"
                ),
                {
                    "id": s["id"],
                    "task_id": s["task_id"],
                    "text": s["text"],
                    "done": int(s["done"]),
                    "created_at": s["created_at"],
                },
            )


# ----------------------------- Task mutations -----------------------------

def add_task(task_text: str, priority: str, category: str, due_date: str | None, username: str) -> dict:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        new_id = conn.execute(
            text(
                "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username) "
                "VALUES (:text, 0, :priority, :category, :due_date, :created_at, :username) "
                "RETURNING id"
            ),
            {
                "text": task_text,
                "priority": priority,
                "category": category or "General",
                "due_date": due_date,
                "created_at": datetime.now().isoformat(),
                "username": username,
            },
        ).scalar_one()
    log_activity(username, "added", task_text)
    return get_task(new_id, username)


def set_done(task_id: int, done: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        task_text = _get_task_text(conn, task_id)
        conn.execute(
            text("UPDATE tasks SET done = :done WHERE id = :id AND username = :username"),
            {"done": int(done), "id": task_id, "username": username},
        )
        conn.execute(
            text("UPDATE subtasks SET done = :done WHERE task_id = :task_id"),
            {"done": int(done), "task_id": task_id},
        )
    log_activity(username, "completed" if done else "uncompleted", task_text)
    return get_task(task_id, username)


def set_pinned(task_id: int, pinned: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        task_text = _get_task_text(conn, task_id)
        conn.execute(
            text("UPDATE tasks SET pinned = :pinned WHERE id = :id AND username = :username"),
            {"pinned": int(pinned), "id": task_id, "username": username},
        )
    log_activity(username, "pinned" if pinned else "unpinned", task_text)
    return get_task(task_id, username)


def update_task(task_id: int, task_text: str, priority: str, category: str, due_date: str | None, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        old_text = _get_task_text(conn, task_id)
        conn.execute(
            text(
                "UPDATE tasks SET text = :text, priority = :priority, category = :category, due_date = :due_date "
                "WHERE id = :id AND username = :username"
            ),
            {
                "text": task_text,
                "priority": priority,
                "category": category,
                "due_date": due_date,
                "id": task_id,
                "username": username,
            },
        )
    detail = task_text if task_text == old_text else f"{old_text} → {task_text}"
    log_activity(username, "edited", detail)
    return get_task(task_id, username)


def delete_task(task_id: int, username: str) -> None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        task_text = _get_task_text(conn, task_id)
        conn.execute(text("DELETE FROM subtasks WHERE task_id = :task_id"), {"task_id": task_id})
        conn.execute(
            text("DELETE FROM tasks WHERE id = :id AND username = :username"),
            {"id": task_id, "username": username},
        )
    log_activity(username, "deleted", task_text)


def clear_completed(username: str) -> int:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        done_ids = [
            r["id"]
            for r in conn.execute(
                text("SELECT id FROM tasks WHERE done = 1 AND username = :username"),
                {"username": username},
            ).mappings().all()
        ]
        if done_ids:
            stmt = text("DELETE FROM subtasks WHERE task_id IN :task_ids").bindparams(
                bindparam("task_ids", expanding=True)
            )
            conn.execute(stmt, {"task_ids": done_ids})
        conn.execute(
            text("DELETE FROM tasks WHERE done = 1 AND username = :username"), {"username": username}
        )
    if done_ids:
        log_activity(username, "cleared_completed", f"{len(done_ids)} task{'s' if len(done_ids) != 1 else ''}")
    return len(done_ids)


def clear_all(username: str) -> int:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM tasks WHERE username = :username"), {"username": username}
        ).scalar_one()
        conn.execute(
            text("DELETE FROM subtasks WHERE task_id IN (SELECT id FROM tasks WHERE username = :username)"),
            {"username": username},
        )
        conn.execute(text("DELETE FROM tasks WHERE username = :username"), {"username": username})
    if count:
        log_activity(username, "cleared_all", f"{count} task{'s' if count != 1 else ''}")
    return count


def mark_all_completed(username: str) -> int:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM tasks WHERE username = :username AND done = 0"),
            {"username": username},
        ).scalar_one()
        conn.execute(text("UPDATE tasks SET done = 1 WHERE username = :username"), {"username": username})
        conn.execute(
            text("UPDATE subtasks SET done = 1 WHERE task_id IN (SELECT id FROM tasks WHERE username = :username)"),
            {"username": username},
        )
    if count:
        log_activity(username, "marked_all_completed", f"{count} task{'s' if count != 1 else ''}")
    return count


# ----------------------------- Subtask mutations -----------------------------

def add_subtask(task_id: int, subtask_text: str, username: str) -> tuple[dict, bool]:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        new_id = conn.execute(
            text(
                "INSERT INTO subtasks (task_id, text, done, created_at) "
                "VALUES (:task_id, :text, 0, :created_at) RETURNING id"
            ),
            {"task_id": task_id, "text": subtask_text, "created_at": datetime.now().isoformat()},
        ).scalar_one()
        conn.execute(
            text("UPDATE tasks SET done = 0 WHERE id = :id AND username = :username"),
            {"id": task_id, "username": username},
        )
        row = conn.execute(
            text("SELECT * FROM subtasks WHERE id = :id"), {"id": new_id}
        ).mappings().fetchone()
    return _subtask_dict(row), False


def set_subtask_done(subtask_id: int, task_id: int, done: bool, username: str) -> tuple[dict | None, bool]:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subtasks SET done = :done WHERE id = :id"), {"done": int(done), "id": subtask_id}
        )

        subtasks = conn.execute(
            text("SELECT done FROM subtasks WHERE task_id = :task_id"), {"task_id": task_id}
        ).mappings().all()
        parent_done = None
        if subtasks:
            all_done = all(s["done"] for s in subtasks)
            if not done:
                conn.execute(
                    text("UPDATE tasks SET done = 0 WHERE id = :id AND username = :username"),
                    {"id": task_id, "username": username},
                )
                parent_done = False
            elif all_done:
                conn.execute(
                    text("UPDATE tasks SET done = 1 WHERE id = :id AND username = :username"),
                    {"id": task_id, "username": username},
                )
                parent_done = True

        row = conn.execute(
            text("SELECT * FROM subtasks WHERE id = :id"), {"id": subtask_id}
        ).mappings().fetchone()
        if parent_done is None:
            task_row = conn.execute(
                text("SELECT done FROM tasks WHERE id = :id"), {"id": task_id}
            ).mappings().fetchone()
            parent_done = bool(task_row["done"]) if task_row else False

    return (_subtask_dict(row) if row else None), parent_done


def delete_subtask(subtask_id: int, task_id: int, username: str) -> bool:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM subtasks WHERE id = :id"), {"id": subtask_id})

        subtasks = conn.execute(
            text("SELECT done FROM subtasks WHERE task_id = :task_id"), {"task_id": task_id}
        ).mappings().all()
        if subtasks:
            all_done = all(s["done"] for s in subtasks)
            if all_done:
                conn.execute(
                    text("UPDATE tasks SET done = 1 WHERE id = :id AND username = :username"),
                    {"id": task_id, "username": username},
                )

        task_row = conn.execute(
            text("SELECT done FROM tasks WHERE id = :id"), {"id": task_id}
        ).mappings().fetchone()

    return bool(task_row["done"]) if task_row else False
