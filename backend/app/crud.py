import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta

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


def user_exists(username: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM users WHERE username = :username"), {"username": username.strip()}
        ).fetchone()
    return row is not None


def get_or_create_google_user(google_sub: str, email: str | None) -> str:
    """Finds the account already linked to this Google account, or creates
    one - keyed by google_sub, not email (an email could theoretically be
    reused across Google accounts over time; the sub is Google's own stable,
    permanent identifier). This account is entirely separate from any
    username/password account that happens to share the same email -
    there's no merging/linking with an existing manual account."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT username FROM users WHERE google_sub = :sub"), {"sub": google_sub}
        ).mappings().fetchone()
        if row:
            return row["username"]

        base_username = (email.split("@")[0].strip() if email else "") or f"google-{google_sub[:8]}"
        username = base_username
        suffix = 1
        while conn.execute(
            text("SELECT 1 FROM users WHERE username = :username"), {"username": username}
        ).fetchone():
            suffix += 1
            username = f"{base_username}{suffix}"

        # No login flow ever checks this password (Google accounts only
        # authenticate via the OAuth callback) - it just satisfies the
        # column's NOT NULL constraint with something nobody can guess.
        conn.execute(
            text("INSERT INTO users (username, password, google_sub) VALUES (:username, :password, :sub)"),
            {"username": username, "password": hash_password(secrets.token_urlsafe(32)), "sub": google_sub},
        )
        return username


def get_website_link(username: str) -> dict | None:
    """The website account this local account was last linked to (see
    set_website_link) - or None if it's never been linked. Desktop app only;
    lets Pull/Push/autosave (routers/auth.py) reuse those credentials
    without asking the user to re-enter them every time the app reopens."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT website_username, website_password FROM website_links WHERE username = :username"),
            {"username": username},
        ).mappings().fetchone()
    return dict(row) if row else None


def set_website_link(username: str, website_username: str, website_password: str) -> None:
    """Called after every successful Pull/Push (whichever credentials were
    used, freshly entered or already-stored) so the link always reflects the
    most recently *confirmed-working* website account - re-linking to a
    different one just overwrites the previous row, there's no history."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM website_links WHERE username = :username"), {"username": username})
        conn.execute(
            text(
                "INSERT INTO website_links (username, website_username, website_password, linked_at) "
                "VALUES (:username, :website_username, :website_password, :linked_at)"
            ),
            {
                "username": username,
                "website_username": website_username,
                "website_password": website_password,
                "linked_at": datetime.now().isoformat(),
            },
        )


def clear_website_link(username: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM website_links WHERE username = :username"), {"username": username})


# ----------------------------- Row -> dict helpers -----------------------------

def _task_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    d["pinned"] = bool(d["pinned"])
    d["urgent"] = bool(d["urgent"])
    return d


def _subtask_dict(row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    d["urgent"] = bool(d["urgent"])
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

def log_activity(username: str, action: str, detail: str, task_id: int | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO activity_log (username, action, detail, created_at, task_id) "
                "VALUES (:username, :action, :detail, :created_at, :task_id)"
            ),
            {
                "username": username,
                "action": action,
                "detail": detail,
                "created_at": datetime.now().isoformat(),
                "task_id": task_id,
            },
        )


def remove_latest_completed_log(username: str, task_id: int) -> None:
    """Deletes the most recent 'completed' activity log entry for a specific
    task - used when undo/redo restores a task's `done` field back to False,
    so the streak/heatmap stats (derived from this log) stop counting a
    completion that's being reversed. See adjust_completion_log."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM activity_log WHERE username = :username AND action = 'completed' "
                "AND task_id = :task_id ORDER BY created_at DESC LIMIT 1"
            ),
            {"username": username, "task_id": task_id},
        ).mappings().fetchone()
        if row:
            conn.execute(text("DELETE FROM activity_log WHERE id = :id"), {"id": row["id"]})


def adjust_completion_log(username: str, before_tasks: list[dict], after_tasks: list[dict]) -> None:
    """Called by undo/redo right after restoring `after_tasks` over
    `before_tasks`: for any task whose `done` field flips as a result, keeps
    the 'completed' activity log (and therefore the streak/heatmap stats
    derived from it) consistent with the state actually being restored -
    removing the log entry if a completion is being undone, adding one if a
    completion is being restored (e.g. redoing it, or undoing an
    "uncomplete"). Without this, undoing a completion would still count
    toward the streak forever, since undo/redo works by restoring a full
    prior snapshot rather than literally reversing the one action taken."""
    before_by_id = {t["id"]: t for t in before_tasks}
    for after in after_tasks:
        before = before_by_id.get(after["id"])
        if before is None:
            continue
        was_done = bool(before["done"])
        now_done = bool(after["done"])
        if was_done and not now_done:
            remove_latest_completed_log(username, after["id"])
        elif not was_done and now_done:
            log_activity(username, "completed", after["text"], task_id=after["id"])


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


def get_stats(username: str) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        # SUBSTR(created_at, 1, 10) takes the YYYY-MM-DD prefix off the
        # isoformat() timestamp - works identically on SQLite and Postgres,
        # so this needs no dialect branching.
        rows = conn.execute(
            text(
                """
                SELECT SUBSTR(created_at, 1, 10) AS day, COUNT(*) AS count
                FROM activity_log
                WHERE username = :username AND action = 'completed'
                GROUP BY day
                """
            ),
            {"username": username},
        ).mappings().all()

    counts_by_day: dict[str, int] = {r["day"]: r["count"] for r in rows}
    total_completed = sum(counts_by_day.values())

    today = date.today()
    today_iso = today.isoformat()
    completed_today = counts_by_day.get(today_iso, 0)

    week_start_iso = (today - timedelta(days=6)).isoformat()
    completed_this_week = sum(
        count for day, count in counts_by_day.items() if week_start_iso <= day <= today_iso
    )

    days_with_activity = set(counts_by_day.keys())

    # Current streak counts consecutive days ending today, or - if today
    # hasn't had a completion yet - ending yesterday, so an empty "so far
    # today" doesn't read as a broken streak while the day is still open.
    current_streak = 0
    cursor = today if today_iso in days_with_activity else today - timedelta(days=1)
    while cursor.isoformat() in days_with_activity:
        current_streak += 1
        cursor -= timedelta(days=1)

    longest_streak = 0
    if days_with_activity:
        sorted_days = sorted(date.fromisoformat(d) for d in days_with_activity)
        run = 1
        longest_streak = 1
        for prev_day, curr_day in zip(sorted_days, sorted_days[1:]):
            run = run + 1 if (curr_day - prev_day).days == 1 else 1
            longest_streak = max(longest_streak, run)

    daily_counts = [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "count": counts_by_day.get((today - timedelta(days=offset)).isoformat(), 0),
        }
        for offset in range(29, -1, -1)
    ]

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "completed_today": completed_today,
        "completed_this_week": completed_this_week,
        "total_completed": total_completed,
        "daily_counts": daily_counts,
    }


# ----------------------------- Undo/redo restore -----------------------------

def restore_state(state_tasks: list[dict], username: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE username = :username"), {"username": username})
        for t in state_tasks:
            conn.execute(
                text(
                    "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at, username, pinned, position, notes, urgent) "
                    "VALUES (:id, :text, :done, :priority, :category, :due_date, :created_at, :username, :pinned, :position, :notes, :urgent)"
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
                    "position": t.get("position", 0),
                    # notes deliberately has no dedicated undo history (see
                    # set_task_notes), but it must still round-trip through
                    # restores triggered by *other* undo/redo actions -
                    # omitting it here would silently wipe notes on every
                    # task any time an unrelated action got undone.
                    "notes": t.get("notes"),
                    "urgent": int(t.get("urgent", False)),
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
                    "INSERT INTO subtasks (id, task_id, text, done, created_at, urgent, due_date, notes) "
                    "VALUES (:id, :task_id, :text, :done, :created_at, :urgent, :due_date, :notes)"
                ),
                {
                    "id": s["id"],
                    "task_id": s["task_id"],
                    "text": s["text"],
                    "done": int(s["done"]),
                    "created_at": s["created_at"],
                    "urgent": int(s.get("urgent", False)),
                    "due_date": s.get("due_date"),
                    # Like the matching comment in restore_state: subtask
                    # notes have no dedicated undo history of their own, but
                    # must still round-trip through restores triggered by
                    # *other* undo/redo actions, or any undo/redo at all
                    # would silently wipe every subtask's notes.
                    "notes": s.get("notes"),
                },
            )


# ----------------------------- Task mutations -----------------------------

def add_task(task_text: str, priority: str, category: str, due_date: str | None, username: str) -> dict:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        # New tasks join at the top of manual order, same place they already
        # appear in the default (newest-first) view.
        min_position = conn.execute(
            text("SELECT MIN(position) FROM tasks WHERE username = :username"), {"username": username}
        ).scalar_one()
        new_position = (min_position - 1) if min_position is not None else 0
        new_id = conn.execute(
            text(
                "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username, position) "
                "VALUES (:text, 0, :priority, :category, :due_date, :created_at, :username, :position) "
                "RETURNING id"
            ),
            {
                "text": task_text,
                "priority": priority,
                "category": category or "General",
                "due_date": due_date,
                "created_at": datetime.now().isoformat(),
                "username": username,
                "position": new_position,
            },
        ).scalar_one()
    log_activity(username, "added", task_text, task_id=new_id)
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
        # Finishing a subtask (whether individually or via its parent task
        # completing here) clears any urgent flag it had - there's no more
        # reason to keep flagging something that's already done.
        if done:
            conn.execute(
                text("UPDATE subtasks SET done = 1, urgent = 0 WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
        else:
            conn.execute(
                text("UPDATE subtasks SET done = 0 WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
    log_activity(username, "completed" if done else "uncompleted", task_text, task_id=task_id)
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
    log_activity(username, "pinned" if pinned else "unpinned", task_text, task_id=task_id)
    return get_task(task_id, username)


def set_position(task_id: int, position: float, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET position = :position WHERE id = :id AND username = :username"),
            {"position": position, "id": task_id, "username": username},
        )
    return get_task(task_id, username)


def set_task_urgent(task_id: int, urgent: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET urgent = :urgent WHERE id = :id AND username = :username"),
            {"urgent": int(urgent), "id": task_id, "username": username},
        )
    return get_task(task_id, username)


def set_task_assignment(task_id: int, assigned_task_id: int | None, username: str) -> dict | None:
    """`task_id` is the assessment being filed under `assigned_task_id` (a
    plain task) - see the Alt+click flow in TaskListPage.tsx's assignment
    selection state. assigned_task_id=None unassigns it. Caller (routers/
    tasks.py's /assign) is responsible for confirming both ids already
    belong to `username` before calling this."""
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET assigned_task_id = :assigned_task_id WHERE id = :id AND username = :username"),
            {"assigned_task_id": assigned_task_id, "id": task_id, "username": username},
        )
    return get_task(task_id, username)


def set_due_date(task_id: int, due_date: str | None, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        task_text = _get_task_text(conn, task_id)
        conn.execute(
            text("UPDATE tasks SET due_date = :due_date WHERE id = :id AND username = :username"),
            {"due_date": due_date, "id": task_id, "username": username},
        )
    log_activity(username, "edited", task_text, task_id=task_id)
    return get_task(task_id, username)


def set_task_notes(task_id: int, notes: str, username: str) -> dict | None:
    # Deliberately does NOT call undo.save_snapshot(). Every other mutation
    # does, but notes autosave on a debounce while typing - snapshotting on
    # every save would flood the 20-entry undo stack with near-identical
    # in-progress drafts and push out the structural edits (add/delete/
    # complete) a user would actually want to undo. restore_state still
    # carries whatever notes value was captured in an *existing* snapshot,
    # so undoing an unrelated action doesn't wipe notes - it just means
    # notes edits themselves aren't a distinct undo step.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks SET notes = :notes WHERE id = :id AND username = :username"),
            {"notes": notes or None, "id": task_id, "username": username},
        )
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
    log_activity(username, "edited", detail, task_id=task_id)
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
        # Any assessment assigned under this task (see set_task_assignment)
        # would otherwise be left pointing at an id that no longer exists.
        conn.execute(
            text("UPDATE tasks SET assigned_task_id = NULL WHERE assigned_task_id = :id AND username = :username"),
            {"id": task_id, "username": username},
        )
    log_activity(username, "deleted", task_text, task_id=task_id)


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
            # Same dangling-reference cleanup as delete_task, for whichever
            # of these completed tasks had assessments assigned under them.
            unassign_stmt = text(
                "UPDATE tasks SET assigned_task_id = NULL WHERE assigned_task_id IN :task_ids AND username = :username"
            ).bindparams(bindparam("task_ids", expanding=True))
            conn.execute(unassign_stmt, {"task_ids": done_ids, "username": username})
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
            text(
                "UPDATE subtasks SET done = 1, urgent = 0 "
                "WHERE task_id IN (SELECT id FROM tasks WHERE username = :username)"
            ),
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
        # Finishing a subtask clears any urgent flag it had - no more reason
        # to keep flagging something that's already done.
        if done:
            conn.execute(text("UPDATE subtasks SET done = 1, urgent = 0 WHERE id = :id"), {"id": subtask_id})
        else:
            conn.execute(text("UPDATE subtasks SET done = 0 WHERE id = :id"), {"id": subtask_id})

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


def set_subtask_urgent(subtask_id: int, urgent: bool, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subtasks SET urgent = :urgent WHERE id = :id"),
            {"urgent": int(urgent), "id": subtask_id},
        )
        row = conn.execute(
            text("SELECT * FROM subtasks WHERE id = :id"), {"id": subtask_id}
        ).mappings().fetchone()
    return _subtask_dict(row) if row else None


def set_subtask_due_date(subtask_id: int, due_date: str | None, username: str) -> dict | None:
    undo.save_snapshot(username)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subtasks SET due_date = :due_date WHERE id = :id"),
            {"due_date": due_date, "id": subtask_id},
        )
        row = conn.execute(
            text("SELECT * FROM subtasks WHERE id = :id"), {"id": subtask_id}
        ).mappings().fetchone()
    return _subtask_dict(row) if row else None


def set_subtask_notes(subtask_id: int, notes: str) -> dict | None:
    # Mirrors set_task_notes: no undo.save_snapshot() since notes autosave on
    # a debounce while typing, and snapshotting every keystroke-driven save
    # would flood the undo stack with near-identical drafts.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subtasks SET notes = :notes WHERE id = :id"),
            {"notes": notes or None, "id": subtask_id},
        )
        row = conn.execute(
            text("SELECT * FROM subtasks WHERE id = :id"), {"id": subtask_id}
        ).mappings().fetchone()
    return _subtask_dict(row) if row else None


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


# ----------------------------- Export / Import -----------------------------

def import_data(tasks: list[dict], username: str, *, replace: bool = False) -> tuple[int, int]:
    """Additive by default: existing tasks are left alone, imported ones land
    as a new batch on top (see the position math below) - unlike
    restore_state/restore_subtasks, which are specifically an undo/redo
    primitive that intentionally wipes and replaces everything.

    With replace=True, this *does* wipe first - every existing task/subtask
    for `username` is deleted before the batch is inserted, same as clear_all
    followed by a plain import. Used by the desktop app's Pull/Push (see
    routers/auth.py's /sync and /push) so they act as a mirror/copy rather
    than an ever-growing merge; the regular file-based Import (routers/
    data.py's POST /api/import, no query param) keeps the additive default,
    since silently wiping a user's data because they imported a backup file
    would be a nasty surprise.

    Deliberately doesn't touch streak/heatmap stats (get_stats reads
    activity_log rows dated by when a task was actually completed) - the
    export format has no original completion date to attribute an imported
    done=True task to, and fabricating a "completed today" entry for
    already-old work would inflate the streak with activity that didn't
    happen today."""
    if not tasks and not replace:
        return 0, 0

    undo.save_snapshot(username)
    engine = get_engine()
    imported_tasks = 0
    imported_subtasks = 0
    now = datetime.now().isoformat()

    with engine.begin() as conn:
        if replace:
            conn.execute(
                text("DELETE FROM subtasks WHERE task_id IN (SELECT id FROM tasks WHERE username = :username)"),
                {"username": username},
            )
            conn.execute(text("DELETE FROM tasks WHERE username = :username"), {"username": username})

        # Same "joins at the top" convention as add_task, computed once for
        # the whole batch so the imported tasks keep their relative order
        # among themselves instead of landing reversed (one-at-a-time top
        # insertion would put the *last* imported task at the very top).
        # After a replace-mode delete there's nothing left to join above, so
        # this naturally comes out as just -len(tasks).
        min_position = conn.execute(
            text("SELECT MIN(position) FROM tasks WHERE username = :username"), {"username": username}
        ).scalar_one()
        base_position = (min_position if min_position is not None else 0) - len(tasks)

        for i, t in enumerate(tasks):
            new_task_id = conn.execute(
                text(
                    "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username, pinned, position, notes, urgent) "
                    "VALUES (:text, :done, :priority, :category, :due_date, :created_at, :username, :pinned, :position, :notes, :urgent) "
                    "RETURNING id"
                ),
                {
                    "text": t["text"],
                    "done": int(t.get("done", False)),
                    "priority": t.get("priority") or "Medium",
                    "category": t.get("category") or "General",
                    "due_date": t.get("due_date"),
                    "created_at": now,
                    "username": username,
                    "pinned": int(t.get("pinned", False)),
                    "position": base_position + i,
                    "notes": t.get("notes"),
                    "urgent": int(t.get("urgent", False)),
                },
            ).scalar_one()
            imported_tasks += 1

            for s in t.get("subtasks") or []:
                conn.execute(
                    text(
                        "INSERT INTO subtasks (task_id, text, done, created_at, urgent, due_date, notes) "
                        "VALUES (:task_id, :text, :done, :created_at, :urgent, :due_date, :notes)"
                    ),
                    {
                        "task_id": new_task_id,
                        "text": s["text"],
                        "done": int(s.get("done", False)),
                        "created_at": now,
                        "urgent": int(s.get("urgent", False)),
                        "due_date": s.get("due_date"),
                        "notes": s.get("notes"),
                    },
                )
                imported_subtasks += 1

    log_activity(
        username,
        "imported",
        f"{imported_tasks} task{'s' if imported_tasks != 1 else ''}, "
        f"{imported_subtasks} subtask{'s' if imported_subtasks != 1 else ''}",
    )
    return imported_tasks, imported_subtasks
