from collections import defaultdict
from contextlib import closing
from datetime import datetime

import sqlite3

from app import undo
from app.db import get_conn
from app.security import hash_password, verify_password


# ----------------------------- Auth -----------------------------

def create_user(username: str, password: str) -> bool:
    with closing(get_conn()) as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username.strip(), hash_password(password)),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def verify_user(username: str, password: str) -> bool:
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT password FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    return row is not None and verify_password(password, row["password"])


# ----------------------------- Row -> dict helpers -----------------------------

def _task_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    d["pinned"] = bool(d["pinned"])
    return d


def _subtask_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    return d


# ----------------------------- Reads -----------------------------

def get_tasks(username: str) -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE username = ? ORDER BY created_at DESC", (username,)
        ).fetchall()
    return [_task_dict(r) for r in rows]


def get_subtasks(task_id: int) -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at ASC", (task_id,)
        ).fetchall()
    return [_subtask_dict(r) for r in rows]


def get_all_subtasks(username: str) -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT s.* FROM subtasks s
            JOIN tasks t ON s.task_id = t.id
            WHERE t.username = ?
            """,
            (username,),
        ).fetchall()
    return [_subtask_dict(r) for r in rows]


def get_tasks_with_subtasks(username: str) -> list[dict]:
    tasks = get_tasks(username)
    subtasks_by_task = defaultdict(list)
    for s in get_all_subtasks(username):
        subtasks_by_task[s["task_id"]].append(s)
    for t in tasks:
        t["subtasks"] = subtasks_by_task.get(t["id"], [])
    return tasks


def _get_task_text(conn: sqlite3.Connection, task_id: int) -> str:
    row = conn.execute("SELECT text FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row["text"] if row else "(unknown task)"


def get_task(task_id: int, username: str) -> dict | None:
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND username = ?", (task_id, username)
        ).fetchone()
    return _task_dict(row) if row else None


def get_subtask_owning_task_id(subtask_id: int) -> int | None:
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT task_id FROM subtasks WHERE id = ?", (subtask_id,)
        ).fetchone()
    return row["task_id"] if row else None


# ----------------------------- Activity log -----------------------------

def log_activity(username: str, action: str, detail: str) -> None:
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO activity_log (username, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (username, action, detail, datetime.now().isoformat()),
        )
        conn.commit()


def get_activity_log(username: str, limit: int = 15) -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE username = ? ORDER BY created_at DESC LIMIT ?",
            (username, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------- Undo/redo restore -----------------------------

def restore_state(state_tasks: list[dict], username: str) -> None:
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        for t in state_tasks:
            conn.execute(
                "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at, username, pinned) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    t["id"], t["text"], int(t["done"]), t["priority"], t["category"],
                    t["due_date"], t["created_at"], username, int(t.get("pinned", False)),
                ),
            )
        conn.commit()


def restore_subtasks(state_subtasks: list[dict], username: str) -> None:
    with closing(get_conn()) as conn:
        task_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM tasks WHERE username = ?", (username,)
        ).fetchall()]
        if task_ids:
            placeholders = ",".join(["?"] * len(task_ids))
            conn.execute(f"DELETE FROM subtasks WHERE task_id IN ({placeholders})", task_ids)
        for s in state_subtasks:
            conn.execute(
                "INSERT INTO subtasks (id, task_id, text, done, created_at) VALUES (?, ?, ?, ?, ?)",
                (s["id"], s["task_id"], s["text"], int(s["done"]), s["created_at"]),
            )
        conn.commit()


# ----------------------------- Task mutations -----------------------------

def add_task(text: str, priority: str, category: str, due_date: str | None, username: str) -> dict:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username) "
            "VALUES (?, 0, ?, ?, ?, ?, ?)",
            (text, priority, category or "General", due_date, datetime.now().isoformat(), username),
        )
        new_id = cur.lastrowid
        conn.commit()
    log_activity(username, "added", text)
    return get_task(new_id, username)


def set_done(task_id: int, done: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND username = ?", (int(done), task_id, username))
        conn.execute("UPDATE subtasks SET done = ? WHERE task_id = ?", (int(done), task_id))
        conn.commit()
    log_activity(username, "completed" if done else "uncompleted", text)
    return get_task(task_id, username)


def set_pinned(task_id: int, pinned: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("UPDATE tasks SET pinned = ? WHERE id = ? AND username = ?", (int(pinned), task_id, username))
        conn.commit()
    log_activity(username, "pinned" if pinned else "unpinned", text)
    return get_task(task_id, username)


def update_task(task_id: int, text: str, priority: str, category: str, due_date: str | None, username: str) -> dict | None:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        old_text = _get_task_text(conn, task_id)
        conn.execute(
            "UPDATE tasks SET text = ?, priority = ?, category = ?, due_date = ? WHERE id = ? AND username = ?",
            (text, priority, category, due_date, task_id, username),
        )
        conn.commit()
    detail = text if text == old_text else f"{old_text} → {text}"
    log_activity(username, "edited", detail)
    return get_task(task_id, username)


def delete_task(task_id: int, username: str) -> None:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("DELETE FROM subtasks WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
    log_activity(username, "deleted", text)


def clear_completed(username: str) -> int:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        done_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM tasks WHERE done = 1 AND username = ?", (username,)
        ).fetchall()]
        if done_ids:
            placeholders = ",".join(["?"] * len(done_ids))
            conn.execute(f"DELETE FROM subtasks WHERE task_id IN ({placeholders})", done_ids)
        conn.execute("DELETE FROM tasks WHERE done = 1 AND username = ?", (username,))
        conn.commit()
    if done_ids:
        log_activity(username, "cleared_completed", f"{len(done_ids)} task{'s' if len(done_ids) != 1 else ''}")
    return len(done_ids)


def clear_all(username: str) -> int:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE username = ?", (username,)
        ).fetchone()["c"]
        conn.execute(
            "DELETE FROM subtasks WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)", (username,)
        )
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        conn.commit()
    if count:
        log_activity(username, "cleared_all", f"{count} task{'s' if count != 1 else ''}")
    return count


def mark_all_completed(username: str) -> int:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE username = ? AND done = 0", (username,)
        ).fetchone()["c"]
        conn.execute("UPDATE tasks SET done = 1 WHERE username = ?", (username,))
        conn.execute(
            "UPDATE subtasks SET done = 1 WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)",
            (username,),
        )
        conn.commit()
    if count:
        log_activity(username, "marked_all_completed", f"{count} task{'s' if count != 1 else ''}")
    return count


# ----------------------------- Subtask mutations -----------------------------

def add_subtask(task_id: int, text: str, username: str) -> tuple[dict, bool]:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subtasks (task_id, text, done, created_at) VALUES (?, ?, 0, ?)",
            (task_id, text, datetime.now().isoformat()),
        )
        new_id = cur.lastrowid
        conn.execute("UPDATE tasks SET done = 0 WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (new_id,)).fetchone()
    return _subtask_dict(row), False


def set_subtask_done(subtask_id: int, task_id: int, done: bool, username: str) -> tuple[dict | None, bool]:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE subtasks SET done = ? WHERE id = ?", (int(done), subtask_id))

        subtasks = conn.execute("SELECT done FROM subtasks WHERE task_id = ?", (task_id,)).fetchall()
        parent_done = None
        if subtasks:
            all_done = all(s["done"] for s in subtasks)
            if not done:
                conn.execute("UPDATE tasks SET done = 0 WHERE id = ? AND username = ?", (task_id, username))
                parent_done = False
            elif all_done:
                conn.execute("UPDATE tasks SET done = 1 WHERE id = ? AND username = ?", (task_id, username))
                parent_done = True

        conn.commit()
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        if parent_done is None:
            task_row = conn.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()
            parent_done = bool(task_row["done"]) if task_row else False

    return (_subtask_dict(row) if row else None), parent_done


def delete_subtask(subtask_id: int, task_id: int, username: str) -> bool:
    undo.save_snapshot(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))

        subtasks = conn.execute("SELECT done FROM subtasks WHERE task_id = ?", (task_id,)).fetchall()
        if subtasks:
            all_done = all(s["done"] for s in subtasks)
            if all_done:
                conn.execute("UPDATE tasks SET done = 1 WHERE id = ? AND username = ?", (task_id, username))

        conn.commit()
        task_row = conn.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()

    return bool(task_row["done"]) if task_row else False
