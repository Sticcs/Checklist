import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
import html
import uuid
from datetime import date, timedelta, datetime, timezone
from contextlib import closing

DB_PATH = "checklist.db"

# ----------------------------- UI Config & State -----------------------------

st.set_page_config(page_title="Checklist", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "undo_stack" not in st.session_state:
    st.session_state.undo_stack = []
if "redo_stack" not in st.session_state:
    st.session_state.redo_stack = []
if "active_task_id" not in st.session_state:
    st.session_state.active_task_id = None
if "just_added_task_id" not in st.session_state:
    st.session_state.just_added_task_id = None
if "newly_added_task" not in st.session_state:
    st.session_state.newly_added_task = None

# Global Toast Queue
if "pending_toast" in st.session_state:
    st.toast(st.session_state.pending_toast)
    del st.session_state.pending_toast

def _sync_checkboxes_with_db(username):
    tasks = get_tasks(username)
    for t in tasks:
        st.session_state[f"chk_{t['id']}"] = bool(t['done'])
        
    subtasks = get_all_subtasks(username)
    for s in subtasks:
        st.session_state[f"subchk_{s['id']}"] = bool(s['done'])

# ----------------------------- Security & Auth -----------------------------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    with closing(get_conn()) as conn:
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                         (username.strip(), hash_password(password)))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False 

def verify_user(username, password):
    with closing(get_conn()) as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", 
                            (username.strip(), hash_password(password))).fetchone()
        return user is not None

# ----------------------------- Database layer -----------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_conn()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'Medium',
                category TEXT NOT NULL DEFAULT 'General',
                due_date TEXT,
                created_at TEXT NOT NULL,
                username TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN username TEXT")
            conn.execute("UPDATE tasks SET username = 'guest' WHERE username IS NULL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

def get_tasks(username):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE username = ? ORDER BY created_at DESC", (username,)).fetchall()
    return [dict(r) for r in rows]

def get_subtasks(task_id):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at ASC", (task_id,)
        ).fetchall()
    return [dict(r) for r in rows]

def get_all_subtasks(username):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT s.* FROM subtasks s
            JOIN tasks t ON s.task_id = t.id
            WHERE t.username = ?
            """,
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]

def log_activity(username, action, detail):
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO activity_log (username, action, detail, created_at) VALUES (?, ?, ?, ?)",
            (username, action, detail, datetime.now().isoformat()),
        )
        conn.commit()

def get_activity_log(username, limit=15):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE username = ? ORDER BY created_at DESC LIMIT ?",
            (username, limit),
        ).fetchall()
    return [dict(r) for r in rows]

def _get_task_text(conn, task_id):
    row = conn.execute("SELECT text FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row["text"] if row else "(unknown task)"

def _restore_state(state_tasks, username):
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        for t in state_tasks:
            conn.execute(
                "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at, username, pinned) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t['id'], t['text'], t['done'], t['priority'], t['category'], t['due_date'], t['created_at'], username, t.get('pinned', 0))
            )
        conn.commit()

def _restore_subtasks(state_subtasks, username):
    with closing(get_conn()) as conn:
        task_ids = [r['id'] for r in conn.execute(
            "SELECT id FROM tasks WHERE username = ?", (username,)
        ).fetchall()]
        if task_ids:
            placeholders = ",".join(["?"] * len(task_ids))
            conn.execute(f"DELETE FROM subtasks WHERE task_id IN ({placeholders})", task_ids)
        for s in state_subtasks:
            conn.execute(
                "INSERT INTO subtasks (id, task_id, text, done, created_at) VALUES (?, ?, ?, ?, ?)",
                (s['id'], s['task_id'], s['text'], s['done'], s['created_at'])
            )
        conn.commit()

def save_state_for_undo(username):
    st.session_state.undo_stack.append({"tasks": get_tasks(username), "subtasks": get_all_subtasks(username)})
    st.session_state.redo_stack.clear() 
    if len(st.session_state.undo_stack) > 20: 
        st.session_state.undo_stack.pop(0)

def perform_undo(username):
    if st.session_state.undo_stack:
        st.session_state.redo_stack.append({"tasks": get_tasks(username), "subtasks": get_all_subtasks(username)})
        last_state = st.session_state.undo_stack.pop()
        _restore_state(last_state["tasks"], username)
        _restore_subtasks(last_state["subtasks"], username)
        st.session_state.pending_toast = "↩️ Undid last action"

def perform_redo(username):
    if st.session_state.redo_stack:
        st.session_state.undo_stack.append({"tasks": get_tasks(username), "subtasks": get_all_subtasks(username)})
        next_state = st.session_state.redo_stack.pop()
        _restore_state(next_state["tasks"], username)
        _restore_subtasks(next_state["subtasks"], username)
        st.session_state.pending_toast = "↪️ Redid last action"

def add_task(text, priority, category, due_date, username):
    save_state_for_undo(username)
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
    return new_id

def set_done(task_id, done, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND username = ?", (int(done), task_id, username))
        conn.execute("UPDATE subtasks SET done = ? WHERE task_id = ?", (int(done), task_id))
        conn.commit()
    status = "completed" if done else "unmarked"
    st.session_state.pending_toast = f"✅ Task {status}"
    log_activity(username, "completed" if done else "uncompleted", text)

def set_pinned(task_id, pinned, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("UPDATE tasks SET pinned = ? WHERE id = ? AND username = ?", (int(pinned), task_id, username))
        conn.commit()
    st.session_state.pending_toast = "📌 Task pinned" if pinned else "📌 Task unpinned"
    log_activity(username, "pinned" if pinned else "unpinned", text)

def delete_task(task_id, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        text = _get_task_text(conn, task_id)
        conn.execute("DELETE FROM subtasks WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Task deleted"
    log_activity(username, "deleted", text)

def clear_completed(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        done_ids = [r['id'] for r in conn.execute(
            "SELECT id FROM tasks WHERE done = 1 AND username = ?", (username,)
        ).fetchall()]
        if done_ids:
            placeholders = ",".join(["?"] * len(done_ids))
            conn.execute(f"DELETE FROM subtasks WHERE task_id IN ({placeholders})", done_ids)
        conn.execute("DELETE FROM tasks WHERE done = 1 AND username = ?", (username,))
        conn.commit()
    st.session_state.pending_toast = "🧹 Cleared completed tasks"
    if done_ids:
        log_activity(username, "cleared_completed", f"{len(done_ids)} task{'s' if len(done_ids) != 1 else ''}")

def clear_all(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE username = ?", (username,)).fetchone()["c"]
        conn.execute(
            "DELETE FROM subtasks WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)", (username,)
        )
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Cleared all tasks"
    if count:
        log_activity(username, "cleared_all", f"{count} task{'s' if count != 1 else ''}")

def add_subtask(task_id, text, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO subtasks (task_id, text, done, created_at) VALUES (?, ?, 0, ?)",
            (task_id, text, datetime.now().isoformat()),
        )
        conn.execute("UPDATE tasks SET done = 0 WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
    st.session_state.pending_toast = "➕ Subtask added"

def set_subtask_done(subtask_id, task_id, done, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE subtasks SET done = ? WHERE id = ?", (int(done), subtask_id))
        
        subtasks = conn.execute("SELECT done FROM subtasks WHERE task_id = ?", (task_id,)).fetchall()
        if subtasks:
            all_done = all(s['done'] for s in subtasks)
            if not done:
                conn.execute("UPDATE tasks SET done = 0 WHERE id = ? AND username = ?", (task_id, username))
            elif all_done:
                conn.execute("UPDATE tasks SET done = 1 WHERE id = ? AND username = ?", (task_id, username))
                    
        conn.commit()

def delete_subtask(subtask_id, task_id, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
        
        subtasks = conn.execute("SELECT done FROM subtasks WHERE task_id = ?", (task_id,)).fetchall()
        if subtasks:
            all_done = all(s['done'] for s in subtasks)
            if all_done:
                conn.execute("UPDATE tasks SET done = 1 WHERE id = ? AND username = ?", (task_id, username))
                    
        conn.commit()
    st.session_state.pending_toast = "🗑️ Subtask deleted"

def mark_all_completed(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE username = ? AND done = 0", (username,)
        ).fetchone()["c"]
        conn.execute("UPDATE tasks SET done = 1 WHERE username = ?", (username,))
        conn.execute(
            "UPDATE subtasks SET done = 1 WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)",
            (username,)
        )
        conn.commit()
    st.session_state.pending_toast = "✅ Marked all as completed"
    if count:
        log_activity(username, "marked_all_completed", f"{count} task{'s' if count != 1 else ''}")

def update_task(task_id, text, priority, category, due_date, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        old_text = _get_task_text(conn, task_id)
        conn.execute(
            "UPDATE tasks SET text = ?, priority = ?, category = ?, due_date = ? WHERE id = ? AND username = ?",
            (text, priority, category, due_date, task_id, username),
        )
        conn.commit()
    st.session_state.pending_toast = "💾 Task updated"
    detail = text if text == old_text else f"{old_text} → {text}"
    log_activity(username, "edited", detail)

# ----------------------------- Callback Handlers -----------------------------

def handle_task_toggle(task_id, current_done, username):
    set_done(task_id, not current_done, username)

def handle_task_pin(task_id, current_pinned, username):
    set_pinned(task_id, not current_pinned, username)

def handle_task_delete(task_id, username):
    st.session_state.active_task_id = None
    delete_task(task_id, username)

def handle_subtask_add(task_id, username):
    st.session_state.active_task_id = task_id
    key = f"new_sub_{task_id}"
    new_text = st.session_state.get(key, "").strip()
    if new_text:
        add_subtask(task_id, new_text, username)
        st.session_state[key] = "" 

def handle_subtask_toggle(subtask_id, task_id, current_done, username):
    st.session_state.active_task_id = task_id
    set_subtask_done(subtask_id, task_id, not current_done, username)

def handle_subtask_delete(subtask_id, task_id, username):
    st.session_state.active_task_id = task_id
    delete_subtask(subtask_id, task_id, username)

# ----------------------------- Styles & Theming -----------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORIES = ["House", "Work", "Study", "Personal", "Custom"]
PRIORITIES = ["High", "Medium", "Low"]

CAT_KEYS = {"House": "H", "Work": "W", "Study": "S", "Personal": "P", "Custom": ""}
PRI_KEYS = {"High": "T", "Medium": "M", "Low": "L"}

ACTIVITY_META = {
    "added": ("➕", "Added"),
    "completed": ("✅", "Completed"),
    "uncompleted": ("↩️", "Unmarked"),
    "pinned": ("📌", "Pinned"),
    "unpinned": ("📌", "Unpinned"),
    "deleted": ("🗑️", "Deleted"),
    "edited": ("✏️", "Edited"),
    "cleared_completed": ("🧹", "Cleared completed"),
    "cleared_all": ("🗑️", "Cleared all"),
    "marked_all_completed": ("✅", "Marked all completed"),
}

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1.25rem !important;
    }

    /* Streamlit's default block-container padding (96px top / 160px bottom) was
       enough on its own to push total page content past the viewport height,
       forcing stMain to scroll as a *second*, independent scroll region on top
       of the task panel's own internal scroll - trimming it down means the page
       fits in one viewport and only the task list itself needs to scroll. */
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stMain"] {
        overflow: hidden !important;
    }
    /* Streamlit's default <hr> (from st.write("---")) carries a huge 32px
       top/bottom margin - with several dividers stacked in the sidebar that
       added up to a lot of dead vertical space. */
    section[data-testid="stSidebar"] hr {
        margin: 0.75rem 0 !important;
    }
    section[data-testid="stSidebar"] h2 {
        margin-bottom: 0.4rem !important;
    }
    section[data-testid="stSidebar"] .profile-indicator {
        margin-bottom: 0.4rem !important;
    }

    /* Destroy Streamlit's janky skeleton loading animations */
    div[data-testid="stSkeleton"] { display: none !important; opacity: 0 !important; pointer-events: none !important; }
    
    /* Smooth transitions for optimistic UI feedback */
    .optimistic-fade {
        transform: scale(0.95) !important;
        opacity: 0 !important;
        pointer-events: none !important;
        transition: all 0.2s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
    }
    .optimistic-btn {
        opacity: 0.6 !important;
        pointer-events: none !important;
        filter: grayscale(1) !important;
        transition: all 0.1s ease !important;
    }

    section.main, [data-testid="stMain"] {
        transition: margin-left 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
    }
    .block-container {
        transition: max-width 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), padding 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
    }

    .stApp {
        background-attachment: fixed !important;
        background-size: cover !important;
        background-position: center !important;
        transition: background-image 0.3s ease;
    }
    [data-testid="stSidebar"] {
        box-shadow: 5px 0 25px rgba(0,0,0,0.5);
        transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), width 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.3s ease, background-color 0.3s ease !important;
    }
    [data-testid="stHeader"] {
        background: transparent !important;
    }
    
    body.custom-dark .stApp {
        background-image: url("https://images.unsplash.com/photo-1518800524495-b963b722bd92?fm=jpg&q=60&w=3000&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTh8fG1pbmltYWwlMjBkYXJrfGVufDB8fDB8fHww") !important;
    }
    body.custom-dark [data-testid="stSidebar"] {
        background-color: rgba(14, 17, 23, 0.75) !important;
        backdrop-filter: blur(10px);
    }
    
    body.custom-light .stApp {
        background-image: url("https://img.magnific.com/free-vector/green-monstera-leaves-with-copy-space-vector_53876-111532.jpg?semt=ais_hybrid&w=740&q=80") !important;
    }
    body.custom-light [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.85) !important;
        box-shadow: 5px 0 25px rgba(0,0,0,0.15);
        backdrop-filter: blur(10px);
    }
    
    h1, h2, h3, h4 {
        font-weight: 500 !important;
        letter-spacing: -0.5px;
    }

    /* Stack the icon buttons neatly */
    div[data-testid="stColumn"]:nth-child(2) div[data-testid="stButton"] button {
        padding: 0.1rem 0 !important;
        min-height: 2rem !important;
        margin-bottom: 0.2rem !important;
    }

    .task-row {
        padding: 0.8rem 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.25);
        display: flex;
        flex-direction: column;
        justify-content: center;
        transition: opacity 0.05s ease;
        cursor: pointer;
    }
    .task-row.is-done { opacity: 0.4; }
    .task-title {
        font-size: 1.05rem;
        font-weight: 400;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: color 0.05s ease;
    }
    .task-title.is-done { text-decoration: line-through; }
    
    @keyframes slideInDown {
        0% { opacity: 0; transform: translateY(-20px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .new-task-anim { animation: slideInDown 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
    
    .border-High { border-left: 2px solid #e74c3c; padding-left: 12px; }
    .border-Medium { border-left: 2px solid #f39c12; padding-left: 12px; }
    .border-Low { border-left: 2px solid #3498db; padding-left: 12px; }

    /* Task card "done" fill (green) - driven entirely by the server-rendered
       data-done attribute on each card's own marker via :has(), not by a JS
       poller. This paints the instant the new HTML lands (no per-tick JS delay,
       so no flash of unstyled content on rerun), and can't drift onto the wrong
       card the way an optimistic client-side class toggle could when a DOM
       position gets reused for a different task after a resort (e.g. completed
       tasks moving to the top of the list). */
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .task-card-marker[data-done="true"]) {
        background-color: rgba(46, 204, 113, 1) !important;
        border-color: rgba(39, 174, 96, 1) !important;
        transition: background-color 0.3s ease, border-color 0.3s ease;
    }
    body.custom-dark div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .task-card-marker[data-done="true"]) {
        background-color: rgba(29, 131, 72, 1) !important;
        border-color: rgba(20, 90, 50, 1) !important;
    }

    /* Real toggle button for a task card - kept functional (clicked by JS to
       actually commit the completion) but never shown; clicking the card
       itself is the whole interaction now. */
    div[data-testid="stElementContainer"]:has(.hidden-toggle-marker) + div[data-testid="stElementContainer"] {
        display: none !important;
    }

    /* First click on a task card's empty space "arms" it - a light, obviously
       different fill that reads as "click again to confirm" - before the
       second click actually commits the completion (or reverts it, for an
       already-completed card). Smooth transition so it visibly "lights up"
       rather than snapping. */
    div[data-testid="stVerticalBlock"].armed-complete {
        background-color: rgba(255, 255, 255, 0.97) !important;
        border-color: rgba(46, 204, 113, 0.6) !important;
        box-shadow: 0 0 0 2px rgba(46, 204, 113, 0.25) !important;
        transition: background-color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease !important;
    }
    body.custom-dark div[data-testid="stVerticalBlock"].armed-complete {
        background-color: rgba(255, 255, 255, 0.18) !important;
        border-color: rgba(46, 204, 113, 0.7) !important;
        box-shadow: 0 0 0 2px rgba(46, 204, 113, 0.3) !important;
    }

    .meta-tags {
        display: flex;
        gap: 8px;
        font-size: 0.75rem;
        opacity: 0.8;
    }
    .badge {
        background: rgba(128, 128, 128, 0.15);
        padding: 2px 8px;
        border-radius: 4px;
        letter-spacing: 0.2px;
    }
    .activity-log-entry {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.5rem;
        padding: 0.35rem 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.15);
        font-size: 0.82rem;
    }
    .activity-log-entry:last-child {
        border-bottom: none;
    }
    .activity-log-entry > span:first-child {
        overflow-wrap: anywhere;
    }
    .activity-log-time {
        opacity: 0.55;
        font-size: 0.72rem;
        white-space: nowrap;
        flex-shrink: 0;
    }
    .overdue {
        color: #e74c3c;
        background: rgba(231, 76, 60, 0.15);
        font-weight: 600;
    }
    
    @keyframes pulse-urgent {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }
    .urgent-badge {
        color: #e74c3c;
        font-weight: bold;
        font-size: 0.75rem;
        border: 1px solid #e74c3c;
        padding: 2px 6px;
        border-radius: 4px;
        text-transform: uppercase;
        animation: pulse-urgent 1.5s infinite;
        line-height: 1;
    }
    .pin-badge {
        font-size: 0.85rem;
        margin-right: 2px;
        transform: rotate(0deg);
        display: inline-block;
    }

    .profile-indicator {
        font-size: 0.85rem;
        font-weight: 500;
        opacity: 0.75;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 0.8rem;
    }
    .profile-indicator span {
        background: rgba(128, 128, 128, 0.2);
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
    }
    .guest-note {
        font-size: 0.72rem;
        font-style: italic;
        opacity: 0.55;
        margin: -0.5rem 0 0.6rem 30px;
        line-height: 1.3;
    }

    div[data-testid="stButton"] button {
        width: 100%;
        height: auto !important;
        padding: 0.4rem 0.2rem !important;
        transition: background-color 0.18s cubic-bezier(0.2, 0.8, 0.2, 1), border-color 0.18s cubic-bezier(0.2, 0.8, 0.2, 1), color 0.18s cubic-bezier(0.2, 0.8, 0.2, 1), transform 0.12s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
        will-change: background-color, transform;
    }
    div[data-testid="stButton"] button:active {
        transform: scale(0.97) !important;
    }
    
    .stButton button p, .stButton button * {
        white-space: normal !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        font-size: 0.85rem !important;
        text-align: center;
    }
    
    div[data-testid="stHorizontalBlock"] { gap: 0.4rem; }

    /* Category/Priority/Due option rows: size each button to its own label
       instead of forcing equal-width columns (which wrapped longer labels
       onto two lines while shorter ones sat on one, at any zoom level).
       Buttons wrap onto a new row instead of being squeezed. */
    div[data-testid="stElementContainer"]:has(.option-row-marker) ~ div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        row-gap: 0.4rem !important;
    }
    div[data-testid="stElementContainer"]:has(.option-row-marker) ~ div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 0 1 auto !important;
        width: auto !important;
    }
    div[data-testid="stElementContainer"]:has(.option-row-marker) ~ div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button {
        width: auto !important;
        white-space: nowrap !important;
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
    }
    div[data-testid="stElementContainer"]:has(.option-row-marker) ~ div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button p,
    div[data-testid="stElementContainer"]:has(.option-row-marker) ~ div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button * {
        white-space: nowrap !important;
    }

    section[data-testid="stSidebar"] button {
        border-radius: 6px;
        font-weight: 400;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    
    .login-container {
        padding: 2rem;
        border-radius: 12px;
        background: rgba(128,128,128,0.1);
        margin-top: 4rem;
    }

    /* Subtask panel: its own neutral surface, isolated from the parent task's
       priority color-coding (which is painted on the card behind it). */
    div[data-testid="stExpander"] {
        border: none !important;
        background: rgba(255, 255, 255, 0.92) !important;
        border-radius: 10px !important;
        padding: 0.15rem 0.7rem 0.35rem 0.7rem !important;
        margin-top: 0.45rem !important;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
        transition: background-color 0.3s ease;
    }
    body.custom-dark div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.07) !important;
        box-shadow: none;
    }
    div[data-testid="stExpanderDetails"] {
        background: transparent !important;
        background-color: transparent !important;
        animation: expandFade 0.3s ease;
        transition: all 0.3s ease;
    }
    div[data-testid="stExpander"] summary {
        transition: opacity 0.2s ease;
        padding: 0.3rem 0 !important;
    }
    div[data-testid="stExpander"] summary svg {
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    @keyframes expandFade {
        0% { opacity: 0; transform: translateY(-6px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .subtask-progress-wrap {
        margin: 0.35rem 0 0.15rem 0;
    }
    .subtask-row {
        font-size: 0.92rem;
        display: flex;
        align-items: center;
        transition: opacity 0.15s ease;
        margin: 0 !important;
        padding: 0.5rem 0.1rem !important;
        /* Was 0.14 alpha, which is essentially invisible on a light background -
           bumped enough to actually read as a minimalist divider on both themes. */
        border-bottom: 1px solid rgba(128, 128, 128, 0.3);
    }
    .subtask-row.is-done {
        text-decoration: line-through;
        opacity: 0.5;
    }
    
    /* Elegant Minimalist Focus Border for Editing Subtasks */
    .green-focus-border {
        border-color: rgba(46, 204, 113, 0.8) !important;
        box-shadow: 0 0 0 1px rgba(46, 204, 113, 0.5), 0 4px 12px rgba(46, 204, 113, 0.1) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    
    /* First Task Prompt Animation */
    .first-task-prompt {
        color: rgba(46, 204, 113, 1);
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: -12px;
        margin-bottom: 12px;
        margin-left: 4px;
        animation: subtle-bounce 2s infinite;
    }
    body.custom-dark .first-task-prompt {
        color: rgba(46, 204, 113, 0.9);
    }
    @keyframes subtle-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(3px); }
    }

    /* CSS Progressive Disclosure Logic */
    .progressive-base {
        transition: max-height 0.4s ease-in-out, opacity 0.4s ease-in-out, transform 0.4s ease-in-out !important;
    }
    .progressive-hidden {
        max-height: 0px !important;
        opacity: 0 !important;
        overflow: hidden !important;
        transform: translateY(-10px) !important;
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        pointer-events: none !important;
    }
    .progressive-visible {
        max-height: 300px !important;
        opacity: 1 !important;
        transform: translateY(0) !important;
        pointer-events: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()

# AEST Timezone offset logic
LOCAL_TZ = timezone(timedelta(hours=10))

def _get_local_today():
    return datetime.now(LOCAL_TZ).date()

# ----------------------------- Auth Routing -----------------------------

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; margin-top: 2rem;'>✅ My Checklist</h1>", unsafe_allow_html=True)
        st.write("")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            with st.form("login_form", border=False):
                l_user = st.text_input("Username", key="login_user", placeholder="Enter your username")
                l_pass = st.text_input("Password", type="password", key="login_pass", placeholder="Enter your password")
                if st.form_submit_button("Login", type="primary", use_container_width=True):
                    if verify_user(l_user, l_pass):
                        st.session_state.logged_in = True
                        st.session_state.username = l_user.strip()
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

        with tab2:
            with st.form("signup_form", border=False):
                s_user = st.text_input("Choose a Username", key="sign_user", placeholder="Pick a username")
                s_pass = st.text_input("Choose a Password", type="password", key="sign_pass", placeholder="Pick a password")
                if st.form_submit_button("Create Account", type="primary", use_container_width=True):
                    if s_user and s_pass:
                        if create_user(s_user, s_pass):
                            st.success("Account created! You can now log in.")
                        else:
                            st.error("Username already exists. Pick another one.")
                    else:
                        st.warning("Please fill in both fields.")
                    
        st.write("---")
        if st.button("Continue as Guest", type="secondary", use_container_width=True):
            st.session_state.logged_in = True
            # Every guest session used to share the literal username "guest", so
            # any two people who both clicked "Continue as Guest" landed on the
            # exact same tasks. Each guest session now gets its own throwaway
            # identity instead, isolated the same way a real account is.
            st.session_state.username = f"guest_{uuid.uuid4().hex[:12]}"
            st.rerun()

else:
    st.markdown(
        """
        <style>
        /* --- Right List Column Scrolling --- */
        div[data-testid="stColumn"]:has(#right-col-anchor) {
            height: 88vh !important;
            max-height: 88vh !important;
            overflow-y: scroll !important;
            scroll-behavior: smooth !important;
            padding-right: 15px !important;
            padding-bottom: 3rem !important;
            -ms-overflow-style: none !important;
            scrollbar-width: none !important;
            mask-image: linear-gradient(to bottom, black calc(100% - 36px), transparent 100%);
            -webkit-mask-image: linear-gradient(to bottom, black calc(100% - 36px), transparent 100%);
        }
        div[data-testid="stColumn"]:has(#right-col-anchor)::-webkit-scrollbar {
            display: none !important;
        }

        /* --- "Completed" progress bar, styled as a floating pill. Real CSS
           position:sticky doesn't work here - Streamlit wraps this element in its
           own tightly-fitted layout wrapper (sized to just the bar itself), which
           becomes its sticky containing block and caps the "stick" range to
           roughly its own height instead of the whole scrollable list. A JS-driven
           fixed-position clone (see the script below) handles staying visible
           while scrolled; this rule just styles the real element for when it's
           at the natural top of the list. --- */
        div[data-testid="stElementContainer"]:has(#overall-progress-marker) + div[data-testid="stElementContainer"] {
            padding: 0.6rem 1rem !important;
            /* Vertical alignment with the left panel is corrected dynamically in
               JS (see alignProgressBarWithLeftPanel below) instead of a fixed
               margin here - the exact gap above this bar varies (e.g. the
               one-rerun-only toast/tracker markers that appear right after
               adding a task each add their own spacing), so a hardcoded value
               only stayed correct in whichever specific case it was measured in. */
            margin: 0 2px 0.4rem 2px !important;
            border-radius: 12px !important;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            background: rgba(255, 255, 255, 0.92);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        }
        body.custom-dark div[data-testid="stElementContainer"]:has(#overall-progress-marker) + div[data-testid="stElementContainer"] {
            background: rgba(14, 17, 23, 0.92);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
        }

        /* --- Left Control Panel (Glassmorphism & Legibility) --- */
        div[data-testid="stColumn"]:has(#left-panel-marker) {
            background: rgba(255, 255, 255, 0.65) !important;
            padding: 1.5rem !important;
            border-radius: 16px !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            height: fit-content !important;
        }
        body.custom-dark div[data-testid="stColumn"]:has(#left-panel-marker) {
            background: rgba(14, 17, 23, 0.55) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
        }

        /* Captions: Category, Priority, Due */
        div[data-testid="stColumn"]:has(#left-panel-marker) div[data-testid="stCaptionContainer"] p {
            color: #2c3e50 !important;
            font-weight: 700 !important;
            font-size: 0.85rem !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 0.5rem;
        }
        body.custom-dark div[data-testid="stColumn"]:has(#left-panel-marker) div[data-testid="stCaptionContainer"] p {
            color: #ecf0f1 !important;
        }
        
        /* Fixed-Height Quote Wrapper for 0 Layout Shift */
        .quote-wrapper {
            height: 90px;
            position: relative;
            display: flex;
            align-items: center;
            margin-bottom: 0.5rem;
        }
        #dynamic-header {
            position: absolute;
            width: 100%;
            font-size: clamp(1.8rem, 3vw, 2.75rem);
            font-weight: 700;
            line-height: 1.1;
            transition: opacity 0.5s ease-in-out;
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ----------------------------- Main App Flow (Logged In) -----------------------------
    
    st.session_state.setdefault("task_input", "")
    # None (not any real option) so no button starts pre-selected - the user has
    # to actively choose a category/priority/due for every task.
    st.session_state.setdefault("new_category", None)
    st.session_state.setdefault("new_priority", None)
    st.session_state.setdefault("new_due_preset", None)
    st.session_state.setdefault("new_due_custom", None)
    st.session_state.setdefault("options_modified", False)
    st.session_state.setdefault("focus_custom", False)

    def _end_of_week(base):
        return base + timedelta(days=(6 - base.weekday()))

    DUE_PRESETS = {
        "Today": lambda: _get_local_today().isoformat(),
        "Tomorrow": lambda: (_get_local_today() + timedelta(days=1)).isoformat(),
        "This week": lambda: _end_of_week(_get_local_today()).isoformat(),
        "Next week": lambda: (_end_of_week(_get_local_today()) + timedelta(days=7)).isoformat(),
        "Custom": lambda: (
            st.session_state.new_due_custom.isoformat() if st.session_state.new_due_custom else None
        ),
        "No date": lambda: None,
    }

    def set_category(cat): 
        st.session_state.new_category = cat
        st.session_state.options_modified = True
        if cat == "Custom":
            st.session_state.focus_custom = True
        
    def set_priority(pri): 
        st.session_state.new_priority = pri
        st.session_state.options_modified = True
        
    def set_due_preset(preset): 
        st.session_state.new_due_preset = preset
        st.session_state.options_modified = True

    def submit_new_task():
        text = st.session_state.task_input.strip()
        if text and st.session_state.new_category and st.session_state.new_priority and st.session_state.new_due_preset:
            due_date = DUE_PRESETS[st.session_state.new_due_preset]()
            cat = st.session_state.new_category
            if cat == "Custom":
                cat = st.session_state.get("custom_cat_input", "").strip()
                if not cat:
                    cat = "General"

            new_id = add_task(text, st.session_state.new_priority, cat, due_date, st.session_state.username)
            st.session_state.just_added_task_id = new_id
            st.session_state.newly_added_task = {
                "priority": st.session_state.new_priority,
                "due": due_date
            }

            st.session_state.task_input = ""
            st.session_state.options_modified = False
            # Reset the picked options back to defaults too - not just the text
            # box. Leaving the last selection in place made the category/priority/
            # due buttons still render as "selected" (red/primary) for the next
            # task even though the client-side JS flags that actually gate the
            # Category -> Priority -> Due -> Add reveal chain reset to false the
            # moment the text box clears. Since the buttons already *looked*
            # selected, nothing prompted a click to re-set those JS flags, so the
            # chain would get stuck and Due/Add would never appear.
            st.session_state.new_category = None
            st.session_state.new_priority = None
            st.session_state.new_due_preset = None
            st.session_state.new_due_custom = None
            if "custom_cat_input" in st.session_state:
                st.session_state.custom_cat_input = ""

    # Each option group below reruns in isolation (st.fragment) instead of the whole
    # app, so clicking Category/Priority/Due no longer flickers/re-renders the task list.
    @st.fragment
    def render_category_picker():
        st.markdown("<div id='step-cat-marker' class='option-row-marker'></div>", unsafe_allow_html=True)
        st.caption("Category")
        cat_cols = st.columns(len(CATEGORIES), gap="small")
        for col, cat in zip(cat_cols, CATEGORIES):
            with col:
                btn_label = f"{cat} [{CAT_KEYS[cat]}]" if CAT_KEYS[cat] else cat
                st.button(
                    btn_label,
                    key=f"cat_btn_{cat}",
                    on_click=set_category,
                    args=(cat,),
                    type="primary" if st.session_state.new_category == cat else "secondary",
                )

        if st.session_state.new_category == "Custom":
            st.text_input("Custom Category", placeholder="E.g., Groceries", key="custom_cat_input", label_visibility="collapsed")
            if st.session_state.focus_custom:
                components.html(
                    "<script>setTimeout(() => { const inp = window.parent.document.querySelector('input[placeholder=\"E.g., Groceries\"]'); if(inp) inp.focus(); }, 150);</script>",
                    height=0, width=0
                )
                st.session_state.focus_custom = False

    @st.fragment
    def render_priority_picker():
        st.markdown("<div id='step-pri-marker' class='option-row-marker'></div>", unsafe_allow_html=True)
        st.caption("Priority")
        pri_cols = st.columns(len(PRIORITIES), gap="small")
        for col, pri in zip(pri_cols, PRIORITIES):
            with col:
                st.button(
                    f"{pri} [{PRI_KEYS[pri]}]",
                    key=f"pri_btn_{pri}",
                    on_click=set_priority,
                    args=(pri,),
                    type="primary" if st.session_state.new_priority == pri else "secondary",
                )

    @st.fragment
    def render_due_picker():
        st.markdown("<div id='step-due-marker' class='option-row-marker'></div>", unsafe_allow_html=True)
        st.caption("Due")
        due_cols = st.columns(len(DUE_PRESETS), gap="small")
        for i, (col, preset) in enumerate(zip(due_cols, DUE_PRESETS.keys())):
            with col:
                st.button(
                    f"{preset} [{i+1}]",
                    key=f"due_btn_{preset}",
                    on_click=set_due_preset,
                    args=(preset,),
                    type="primary" if st.session_state.new_due_preset == preset else "secondary",
                )

        if st.session_state.new_due_preset == "Custom":
            st.date_input("Pick a date", key="new_due_custom", label_visibility="collapsed")

    tasks = get_tasks(st.session_state.username)
    sidebar_categories = sorted({t["category"] for t in tasks}) if tasks else []

    # ----------------------------- Sidebar -----------------------------

    with st.sidebar:
        # Guest usernames carry a unique suffix internally (for data isolation
        # between separate guest sessions) that has no business being shown.
        is_guest = st.session_state.username.startswith("guest_")
        display_name = "Guest" if is_guest else st.session_state.username
        st.markdown(f"<div class='profile-indicator'><span>👤</span> {html.escape(display_name)}</div>", unsafe_allow_html=True)
        if is_guest:
            st.markdown("<div class='guest-note'>Tasks won't be saved after you sign out</div>", unsafe_allow_html=True)
        if st.button("Sign out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.undo_stack.clear()
            st.session_state.redo_stack.clear()
            st.session_state.active_task_id = None
            st.rerun()
            
        st.write("---")
        
        st.header("Filters")
        search = st.text_input("Search", label_visibility="collapsed", placeholder="Search tasks...")
        status_filter = st.radio("Status", ["All", "Active", "Completed"], horizontal=True, label_visibility="collapsed")
        pinned_filter = st.checkbox("📌 Pinned only")

        # `default=` only seeds st.multiselect the very first time it's created; on
        # later reruns Streamlit keeps whatever was last selected. If a category
        # disappears (e.g. after Clear all) that stale selection can end up outside
        # the new `options` list, which breaks the widget - and every task added
        # afterwards silently fails the filter. Reconcile it by hand each run: drop
        # categories that no longer exist, and auto-include ones seen for the first
        # time so newly added tasks aren't hidden.
        _cat_key = "category_filter_widget"
        _prev_known = st.session_state.get("known_categories", [])
        _prev_selected = st.session_state.get(_cat_key, sidebar_categories)
        _new_categories = [c for c in sidebar_categories if c not in _prev_known]
        _merged = [c for c in _prev_selected if c in sidebar_categories] + _new_categories
        st.session_state[_cat_key] = list(dict.fromkeys(_merged))  # de-dupe, preserve order
        st.session_state["known_categories"] = sidebar_categories

        category_filter = st.multiselect("Category", sidebar_categories, key=_cat_key)
        sort_by = st.selectbox("Sort by", ["Priority", "Due date", "Newest first"])
        
        st.write("---")
        
        col_u, col_r = st.columns(2)
        with col_u:
            if st.button("↩️ Undo", disabled=len(st.session_state.undo_stack) == 0):
                perform_undo(st.session_state.username)
                st.rerun()
        with col_r:
            if st.button("↪️ Redo", disabled=len(st.session_state.redo_stack) == 0):
                perform_redo(st.session_state.username)
                st.rerun()

        if st.button("Mark all completed"):
            mark_all_completed(st.session_state.username)
            st.rerun()
        if st.button("Clear completed"):
            clear_completed(st.session_state.username)
            st.rerun()
        if st.button("Clear all"):
            clear_all(st.session_state.username)
            st.rerun()

        st.write("---")
        
        with st.expander("Activity Logs"):
            logs = get_activity_log(st.session_state.username, limit=15)
            if not logs:
                st.caption("No recent activity.")
            else:
                for log in logs:
                    icon, label = ACTIVITY_META.get(log["action"], ("•", log["action"].replace("_", " ").title()))
                    when = datetime.fromisoformat(log["created_at"])
                    time_str = when.strftime("%b %d, %I:%M %p").replace(" 0", " ")
                    st.markdown(
                        f"<div class='activity-log-entry'>"
                        f"<span>{icon} <b>{label}:</b> {html.escape(log['detail'])}</span>"
                        f"<span class='activity-log-time'>{time_str}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ----------------------------- Main Layout -----------------------------

    left_col, spacer_col, right_col = st.columns([1, 0.25, 1.4])

    with left_col:
        st.markdown("<div id='left-panel-marker'></div>", unsafe_allow_html=True)
        st.markdown("<div class='quote-wrapper'><div id='dynamic-header'>Stay locked in.</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div id='options-state' data-modified='{str(st.session_state.options_modified).lower()}' style='display:none;'></div>", unsafe_allow_html=True)

        st.text_input(
            "Task",
            placeholder="E.g., Review Big O time complexity",
            key="task_input",
            label_visibility="collapsed",
        )
        
        if not tasks:
            st.markdown("<div class='first-task-prompt'>↑ Type your first task here</div>", unsafe_allow_html=True)

        with st.container():
            render_category_picker()

        with st.container():
            render_priority_picker()

        with st.container():
            render_due_picker()

        with st.container():
            st.markdown("<div id='step-add-marker'></div>", unsafe_allow_html=True)
            st.write("")
            st.button("Add task", on_click=submit_new_task, type="primary")

    with spacer_col:
        st.empty()

    with right_col:
        st.markdown("<div id='right-col-anchor'></div>", unsafe_allow_html=True)
        
        # New UI Task Data payload for the Custom Toast Notification
        new_task_toast = st.session_state.get("newly_added_task")
        if new_task_toast:
            st.markdown(f"<div id='custom-toast-data' data-priority='{new_task_toast['priority']}' data-due='{new_task_toast['due'] or ''}' style='display:none;'></div>", unsafe_allow_html=True)
            st.session_state.newly_added_task = None
        
        just_added = st.session_state.get("just_added_task_id")
        if just_added:
            st.markdown(f"<div id='latest-task-tracker' data-task-id='{just_added}'></div>", unsafe_allow_html=True)
            st.session_state.just_added_task_id = None
        
        filtered = tasks
        if search:
            filtered = [t for t in filtered if search.lower() in t["text"].lower()]
        if status_filter == "Active":
            filtered = [t for t in filtered if not t["done"]]
        elif status_filter == "Completed":
            filtered = [t for t in filtered if t["done"]]
        if category_filter:
            filtered = [t for t in filtered if t["category"] in category_filter]
        if pinned_filter:
            filtered = [t for t in filtered if t["pinned"]]

        if sort_by == "Priority":
            filtered.sort(key=lambda t: PRIORITY_ORDER.get(t["priority"], 3))
        elif sort_by == "Due date":
            filtered.sort(key=lambda t: (t["due_date"] is None, t["due_date"]))
        # Completed tasks float to the top of whatever secondary sort was chosen
        # above, and pinned tasks float above *those* - list.sort is stable, so
        # each pass only breaks ties left by the previous one.
        filtered.sort(key=lambda t: not t["done"])
        filtered.sort(key=lambda t: not t["pinned"])

        # st.empty() gives these slots a stable identity that's explicitly blanked
        # every run before being conditionally refilled, so a deleted task can't
        # leave a stale "X / Y completed" total behind. Two separate empty()
        # placeholders (rather than one wrapping .container()) so no extra
        # stVerticalBlock gets inserted around the marker+bar - that wrapper was
        # only tall enough for its own two children, which cut off the sticky
        # bar's "stick" range to ~its own height instead of the full scroll list.
        marker_slot = st.empty()
        progress_slot = st.empty()
        if tasks:
            done_count = sum(1 for t in tasks if t["done"])
            marker_slot.markdown("<div id='overall-progress-marker'></div>", unsafe_allow_html=True)
            progress_slot.progress(done_count / len(tasks), text=f"{done_count} / {len(tasks)} completed")

        st.write("")

        if not filtered:
            st.caption("No tasks match your filters yet.")
        else:
            today = _get_local_today().isoformat()
            now_time = datetime.now()
            
            for t in filtered:
                with st.container(border=True):
                    st.markdown(f"<div class='task-card-marker' data-task-id='{t['id']}' data-done='{str(bool(t['done'])).lower()}' data-pinned='{str(bool(t['pinned'])).lower()}' style='display:none;'></div>", unsafe_allow_html=True)
                    
                    # Layout: Main task body (left), Stacked buttons (right)
                    col_main, col_btns = st.columns([9, 0.8], vertical_alignment="center")
                    
                    with col_main:
                        done_class = "is-done" if t["done"] else ""
                        created_time = datetime.fromisoformat(t["created_at"])
                        is_new_task = (now_time - created_time).total_seconds() < 2
                        anim_class = "new-task-anim" if is_new_task else ""
                        
                        tags_html = f'<span class="badge">{t["category"]}</span>'
                        
                        urgent_html = ""
                        if t["due_date"]:
                            overdue = (not t["done"]) and t["due_date"] < today
                            due_class = "badge overdue" if overdue else "badge"
                            tags_html += f'<span class="{due_class}">{t["due_date"]}</span>'
                            
                            if t["due_date"] == today and not t["done"]:
                                urgent_html = '<span class="urgent-badge">🚨 Urgent!</span>'
                        
                        pin_html = '<span class="pin-badge" title="Pinned">📌</span>' if t["pinned"] else ""
                        html_string = f"""<div class="task-row border-{t['priority']} {done_class} {anim_class}"><div class="task-title {done_class}">{pin_html}<span>{t['text']}</span>{urgent_html}</div><div class="meta-tags">{tags_html}</div></div>"""
                        
                        st.markdown(html_string, unsafe_allow_html=True)

                        # Real toggle button, kept in the DOM but visually hidden
                        # (see CSS) - clicking anywhere on the card's own empty
                        # space now drives completion via a JS arm/confirm dance
                        # (see setupMagic's card-click handler) that ends by
                        # clicking this button, so the actual state change still
                        # goes through the normal Streamlit callback.
                        st.markdown(f"<div class='hidden-toggle-marker' data-task-id='{t['id']}' style='display:none;'></div>", unsafe_allow_html=True)
                        st.button("toggle-done", key=f"tog_{t['id']}",
                                  on_click=handle_task_toggle, args=(t["id"], bool(t["done"]), st.session_state.username))

                        # ---------------- Subtasks ----------------
                        subtasks = get_subtasks(t["id"])
                        sub_total = len(subtasks)
                        sub_done = sum(1 for s in subtasks if s["done"])

                        # st.empty() gives this slot a stable identity that's explicitly
                        # blanked every run before being conditionally refilled, instead of
                        # relying on Streamlit to notice the block was skipped - which is
                        # what let a stale "Subtasks: X/Y" survive a run where sub_total hit 0.
                        sub_progress_slot = st.empty()
                        if sub_total > 0:
                            with sub_progress_slot.container():
                                st.markdown('<div class="subtask-progress-wrap">', unsafe_allow_html=True)
                                st.progress(sub_done / sub_total, text=f"Subtasks: {sub_done}/{sub_total}")
                                st.markdown('</div>', unsafe_allow_html=True)

                        expander_label = f"📋 Subtasks ({sub_done}/{sub_total})" if sub_total else "📋 Add subtasks"
                        
                        is_expanded = (st.session_state.active_task_id == t["id"])
                        
                        with st.expander(expander_label, expanded=is_expanded):
                            for s in subtasks:
                                sc_main, sc_btn = st.columns([9, 0.8], vertical_alignment="center")
                                with sc_main:
                                    sub_class = "is-done" if s["done"] else ""
                                    st.markdown(
                                        f'<div class="subtask-row {sub_class}">{s["text"]}</div>',
                                        unsafe_allow_html=True,
                                    )
                                with sc_btn:
                                    if s["done"]:
                                        st.button("↩️", key=f"subtog_{s['id']}",
                                                  on_click=handle_subtask_toggle, args=(s["id"], t["id"], bool(s["done"]), st.session_state.username), use_container_width=True)
                                    else:
                                        st.button("✔️", key=f"subtog_{s['id']}",
                                                  on_click=handle_subtask_toggle, args=(s["id"], t["id"], bool(s["done"]), st.session_state.username), use_container_width=True)

                                    st.button("🗑️", key=f"subdel_{s['id']}",
                                              on_click=handle_subtask_delete, args=(s["id"], t["id"], st.session_state.username), use_container_width=True)

                            st.caption("⚡ Press `/` to quickly start typing a subtask")
                            with st.form(key=f"add_sub_form_{t['id']}", clear_on_submit=True, border=False):
                                new_sc1, new_sc2 = st.columns([6, 1.5])
                                with new_sc1:
                                    st.text_input(
                                        "New subtask",
                                        key=f"new_sub_{t['id']}",
                                        placeholder="Add a subtask... (Press '/' to focus)",
                                        label_visibility="collapsed",
                                    )
                                with new_sc2:
                                    st.form_submit_button(
                                        "Add", use_container_width=True,
                                        on_click=handle_subtask_add, args=(t['id'], st.session_state.username)
                                    )

                        if st.session_state.get(f"editing_{t['id']}"):
                            with st.form(f"edit_form_{t['id']}"):
                                e_text = st.text_input("Task text", value=t["text"], label_visibility="collapsed")
                                e_col1, e_col2, e_col3 = st.columns(3)
                                with e_col1:
                                    e_priority = st.selectbox(
                                        "Priority", PRIORITIES,
                                        index=PRIORITIES.index(t["priority"]) if t["priority"] in PRIORITIES else 1,
                                    )
                                with e_col2:
                                    cat_options = CATEGORIES if t["category"] in CATEGORIES else CATEGORIES + [t["category"]]
                                    e_category = st.selectbox(
                                        "Category", cat_options, index=cat_options.index(t["category"])
                                    )
                                with e_col3:
                                    e_due = st.date_input(
                                        "Due date",
                                        value=date.fromisoformat(t["due_date"]) if t["due_date"] else None,
                                    )
                                save_col, cancel_col = st.columns(2)
                                with save_col:
                                    if st.form_submit_button("Save", use_container_width=True):
                                        update_task(
                                            t["id"], e_text.strip(), e_priority, e_category,
                                            e_due.isoformat() if e_due else None, st.session_state.username
                                        )
                                        st.session_state[f"editing_{t['id']}"] = False
                                        st.rerun()
                                with cancel_col:
                                    if st.form_submit_button("Cancel", use_container_width=True):
                                        st.session_state[f"editing_{t['id']}"] = False
                                        st.rerun()
                                        
                    with col_btns:
                        st.button("📌", key=f"pin_{t['id']}",
                                  on_click=handle_task_pin, args=(t["id"], bool(t["pinned"]), st.session_state.username),
                                  use_container_width=True, type="primary" if t["pinned"] else "secondary")
                        if st.button("✏️", key=f"edit_{t['id']}", use_container_width=True):
                            st.session_state[f"editing_{t['id']}"] = True
                        st.button("🗑️", key=f"del_{t['id']}",
                                  on_click=handle_task_delete, args=(t["id"], st.session_state.username), use_container_width=True)

# ----------------------------- Custom JavaScript Injection -----------------------------
components.html(
    """
    <script>
    const doc = window.parent.document;
    
    // Setup Progressive States
    window.textLocked = false;
    window.categorySelected = false;
    window.prioritySelected = false;
    window.dueSelected = false;
    
    const quotes = [
        "Stay locked in.", 
        "September is coming.", 
        "Trust the data.", 
        "Focus.", 
        "Execute."
    ];
    
    let qIdx = 0;
    setInterval(() => {
        const header = doc.getElementById('dynamic-header');
        if (header) {
            header.style.opacity = 0; 
            setTimeout(() => {
                qIdx = (qIdx + 1) % quotes.length;
                header.innerText = quotes[qIdx];
                header.style.opacity = 1; 
            }, 500); 
        }
    }, 8000); 

    // Sync Background Mode & Force Strict DOM Painting for Colors
    setInterval(() => {
        const bg = window.getComputedStyle(doc.querySelector('.stApp') || doc.body).backgroundColor;
        const rgb = bg.match(/\d+/g);
        if (rgb && rgb.length >= 3) {
            const luma = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
            // Compare against the *current* class (not just "was it dark before"),
            // so the very first tick on a fresh load - with no class yet applied -
            // still resolves to the correct wallpaper instead of requiring a
            // manual dark->light round trip to self-correct.
            const shouldBeDark = luma < 128;
            if (shouldBeDark && !doc.body.classList.contains('custom-dark')) {
                doc.body.classList.add('custom-dark');
                doc.body.classList.remove('custom-light');
            } else if (!shouldBeDark && !doc.body.classList.contains('custom-light')) {
                doc.body.classList.add('custom-light');
                doc.body.classList.remove('custom-dark');
            }
        }
        // Task card "done" coloring is handled purely by CSS :has() reading the
        // server-rendered data-done attribute on each card's marker (see the
        // stylesheet above) - no JS needed, which also means no per-tick delay
        // where a card briefly shows unstyled after a rerun, and no risk of a
        // color getting stuck on the wrong card if a resort reuses its DOM
        // position for a different task.
    }, 100);

    // Keeps the progress bar's top edge lined up with the task entry panel's
    // top edge, measured and re-applied every tick rather than assuming a
    // fixed gap - the space above the bar isn't constant (e.g. the toast/
    // tracker markers that render for exactly one rerun right after adding a
    // task add their own extra spacing), so any hardcoded correction only
    // stays right in whichever specific case it was measured against.
    setInterval(() => {
        const leftPanel = doc.getElementById('left-panel-marker');
        const marker = doc.getElementById('overall-progress-marker');
        if (!leftPanel || !marker) return;
        const leftCol = leftPanel.closest('div[data-testid="stColumn"]');
        const container = marker.closest('div[data-testid="stElementContainer"]');
        const bar = container ? container.nextElementSibling : null;
        if (!leftCol || !bar) return;

        // Measure from the *natural* position (no prior correction applied),
        // so repeated ticks don't compound an existing offset.
        bar.style.removeProperty('margin-top');
        const delta = bar.getBoundingClientRect().top - leftCol.getBoundingClientRect().top;
        if (Math.abs(delta) > 1) {
            bar.style.setProperty('margin-top', `${-delta}px`, 'important');
        }
    }, 150);

    // Persist Scroll memory - remembers the right column's scroll position across
    // reruns (native mouse-wheel/scrollbar scrolling handles the actual scrolling;
    // the old floating up/down buttons were unreliable and have been removed).
    if (!doc.body.dataset.scrollMemoryBound) {
        doc.body.dataset.scrollMemoryBound = "true";

        const getScrollCol = () => {
            const anchor = doc.getElementById('right-col-anchor');
            return anchor ? anchor.closest('div[data-testid="stColumn"]') : null;
        };

        const scrollBindTimer = setInterval(() => {
            const col = getScrollCol();
            if (col && !col.dataset.scrollBound) {
                col.dataset.scrollBound = "true";
                col.style.overflowAnchor = 'none';
                const savedScroll = sessionStorage.getItem('rightColScroll');
                if (savedScroll !== null) {
                    col.scrollTop = parseInt(savedScroll);
                }
                col.addEventListener('scroll', () => {
                    sessionStorage.setItem('rightColScroll', col.scrollTop);
                });
                clearInterval(scrollBindTimer);
            }
        }, 300);
    }

    // Fake "sticky" progress bar: mirrors the real bar's content into a
    // fixed-position clone that only appears once the real one has scrolled
    // above the column's own top edge, so it reads as anchored throughout the
    // whole list instead of just its first ~700px (see the CSS comment above
    // for why real position:sticky doesn't reach that far here). Being a real,
    // separately-painted element with an opaque background, it also fully
    // occludes cards passing underneath instead of letting them bleed through.
    setInterval(() => {
        const marker = doc.getElementById('overall-progress-marker');
        const container = marker ? marker.closest('div[data-testid="stElementContainer"]') : null;
        const bar = container ? container.nextElementSibling : null;
        const anchor = doc.getElementById('right-col-anchor');
        const col = anchor ? anchor.closest('div[data-testid="stColumn"]') : null;
        const existing = doc.getElementById('sticky-progress-clone');

        if (!bar || !col) {
            if (existing) existing.style.display = 'none';
            return;
        }

        let clone = existing;
        if (!clone) {
            clone = doc.createElement('div');
            clone.id = 'sticky-progress-clone';
            doc.body.appendChild(clone);
        }

        const colRect = col.getBoundingClientRect();
        const barRect = bar.getBoundingClientRect();
        const isDark = doc.body.classList.contains('custom-dark');

        clone.innerHTML = bar.innerHTML;
        clone.style.cssText = `
            position: fixed;
            top: ${colRect.top + 6}px;
            left: ${colRect.left}px;
            width: ${Math.max(colRect.width - 15, 0)}px;
            z-index: 999;
            padding: 0.6rem 1rem;
            border-radius: 12px;
            box-sizing: border-box;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            background: ${isDark ? 'rgba(14, 17, 23, 0.92)' : 'rgba(255, 255, 255, 0.92)'};
            box-shadow: 0 4px 16px rgba(0, 0, 0, ${isDark ? '0.25' : '0.06'});
            pointer-events: none;
            display: ${barRect.top < colRect.top ? 'block' : 'none'};
        `;
    }, 100);

    // Custom Minimalist Notification Toast Trigger
    setInterval(() => {
        const toastData = doc.getElementById('custom-toast-data');
        if (toastData) {
            const priority = toastData.getAttribute('data-priority');
            const due = toastData.getAttribute('data-due');
            toastData.removeAttribute('id'); 
            
            let dueStr = "No due date";
            if (due && due !== 'None') {
                const today = new Date();
                today.setHours(0,0,0,0);
                const dueDate = new Date(due + 'T00:00:00'); 
                const diffTime = dueDate - today;
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (diffDays === 0) dueStr = "Due today";
                else if (diffDays === 1) dueStr = "Due tomorrow";
                else if (diffDays > 1) dueStr = `Due in ${diffDays} days`;
                else dueStr = `Overdue by ${Math.abs(diffDays)} days`;
            }

            let bg = '#3498db'; 
            if (priority === 'High') bg = '#e74c3c'; 
            else if (priority === 'Medium') bg = '#f39c12'; 

            const customToast = doc.createElement('div');
            customToast.innerHTML = `<strong>${priority} Priority</strong> &bull; ${dueStr}`;
            customToast.style.cssText = `
                position: fixed;
                bottom: 40px;
                left: 50%;
                transform: translateX(-50%) translateY(20px);
                background: ${bg};
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 0.95rem;
                font-weight: 500;
                box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                opacity: 0;
                transition: all 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
                z-index: 999999;
            `;
            doc.body.appendChild(customToast);

            requestAnimationFrame(() => {
                customToast.style.opacity = '1';
                customToast.style.transform = 'translateX(-50%) translateY(0)';
            });

            setTimeout(() => {
                customToast.style.opacity = '0';
                customToast.style.transform = 'translateX(-50%) translateY(20px)';
                setTimeout(() => customToast.remove(), 400);
            }, 4000);
        }
    }, 200);

    // Strict Step-By-Step Progressive Disclosure Engine
    setInterval(() => {
        const taskInput = doc.querySelector('input[placeholder="E.g., Review Big O time complexity"]');
        const catMarker = doc.getElementById('step-cat-marker');
        const priMarker = doc.getElementById('step-pri-marker');
        const dueMarker = doc.getElementById('step-due-marker');
        const addMarker = doc.getElementById('step-add-marker');
        
        const catBlock = catMarker ? catMarker.closest('div[data-testid="stVerticalBlock"]') : null;
        const priBlock = priMarker ? priMarker.closest('div[data-testid="stVerticalBlock"]') : null;
        const dueBlock = dueMarker ? dueMarker.closest('div[data-testid="stVerticalBlock"]') : null;
        const addBlock = addMarker ? addMarker.closest('div[data-testid="stVerticalBlock"]') : null;
        
        [catBlock, priBlock, dueBlock, addBlock].forEach(block => {
            if (block) block.classList.add('progressive-base');
        });

        if (taskInput && taskInput.value.trim().length === 0) {
            window.textLocked = false;
            window.categorySelected = false;
            window.prioritySelected = false;
            window.dueSelected = false;
        }

        // Self-healing: the optimistic click/hotkey handlers set these flags the
        // instant a button is clicked, for a snappy reveal - but that's a purely
        // client-side guess made ahead of the server confirming it. If that guess
        // ever misses (e.g. a race with a fragment rerun replacing the button
        // node right as it's clicked), the flag would stay false forever and the
        // rest of the chain would never reveal, even though the option really
        // did get selected server-side. OR it with a check of the *actual*
        // rendered state (Streamlit marks the selected button type="primary") so
        // a missed optimistic update still self-corrects within one tick once
        // the real rerun lands - selection state can never get permanently
        // stuck out of sync with what's really selected.
        const rowHasSelection = (block) => !!(block && block.querySelector('[data-testid="stBaseButton-primary"]'));
        window.categorySelected = window.categorySelected || rowHasSelection(catBlock);
        window.prioritySelected = window.prioritySelected || rowHasSelection(priBlock);
        window.dueSelected = window.dueSelected || rowHasSelection(dueBlock);

        // Always compute the desired visibility from scratch and apply it, every
        // tick - never conditionally skip based on "have I seen this DOM node
        // before". A category/priority/due button click reruns only its own
        // st.fragment, which replaces that fragment's marker with a brand new DOM
        // node; a stale "first time seen -> force hidden" branch here would snap
        // an already-unlocked section back to hidden for a tick (or, if that tick
        // raced with a rerun, get stuck) even though the underlying selection
        // state said it should stay visible.
        const setVisible = (block, visible) => {
            if (!block) return;
            block.classList.toggle('progressive-visible', visible);
            block.classList.toggle('progressive-hidden', !visible);
        };
        setVisible(catBlock, window.textLocked);
        setVisible(priBlock, window.textLocked && window.categorySelected);
        setVisible(dueBlock, window.textLocked && window.categorySelected && window.prioritySelected);
        setVisible(addBlock, window.textLocked && window.categorySelected && window.prioritySelected && window.dueSelected);
    }, 100);

    // Finds the bordered task-card block enclosing a button/input that lives
    // inside one of its columns (e.g. the delete button, or a subtask input
    // nested inside the subtasks expander). Streamlit no longer exposes a
    // dedicated "bordered wrapper" testid for st.container(border=True), so
    // the card is just a stVerticalBlock — but a button's *nearest*
    // stVerticalBlock ancestor is its own column's inner block, not the
    // card. Climb past each column/row pair until the block found actually
    // contains the card's marker.
    function findEnclosingCard(el) {
        let node = el;
        for (let i = 0; i < 6 && node; i++) {
            const block = node.closest('[data-testid="stVerticalBlock"]');
            if (!block) return null;
            if (block.querySelector('.task-card-marker')) return block;
            const col = block.closest('[data-testid="stColumn"]');
            const hBlock = col ? col.closest('[data-testid="stHorizontalBlock"]') : null;
            if (!hBlock) return null;
            node = hBlock;
        }
        return null;
    }

    // Finds which task's card an element lives inside by checking .contains()
    // from each card marker outward, rather than climbing up from the element -
    // climbing doesn't reliably reach the card from deep inside the subtasks
    // expander (its own nested block structure breaks findEnclosingCard's
    // column/row-pair assumption), but every card's marker->card lookup is the
    // same reliable pattern already used by the color-forcer poller.
    function findTaskIdContaining(el) {
        const markers = doc.querySelectorAll('.task-card-marker');
        for (const marker of markers) {
            const card = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || marker.closest('div[data-testid="stVerticalBlock"]');
            if (card && card.contains(el)) return marker.getAttribute('data-task-id');
        }
        return null;
    }

    // Smoothly collapses a task/subtask row (height + fade) before letting the
    // real delete click through, so removal never causes an abrupt jump.
    function collapseAndDelete(el, btn) {
        if (!el || el.dataset.collapsing === 'true') return;
        el.dataset.collapsing = 'true';
        const startHeight = el.getBoundingClientRect().height;
        el.style.overflow = 'hidden';
        el.style.maxHeight = startHeight + 'px';
        el.style.transition = 'max-height 0.26s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease, transform 0.22s ease, margin 0.26s ease, padding 0.26s ease';
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                el.style.maxHeight = '0px';
                el.style.opacity = '0';
                el.style.transform = 'scale(0.97)';
                el.style.marginTop = '0px';
                el.style.marginBottom = '0px';
                el.style.paddingTop = '0px';
                el.style.paddingBottom = '0px';
                el.style.pointerEvents = 'none';
            });
        });
        const cleanup = () => {
            ['overflow', 'maxHeight', 'transition', 'opacity', 'transform',
             'marginTop', 'marginBottom', 'paddingTop', 'paddingBottom', 'pointerEvents']
                .forEach(p => el.style.removeProperty(p.replace(/[A-Z]/g, m => '-' + m.toLowerCase())));
            delete el.dataset.collapsing;
        };

        const originalMarker = el.querySelector('.task-card-marker');
        const originalTaskId = originalMarker ? originalMarker.getAttribute('data-task-id') : null;

        setTimeout(() => {
            btn.click();
            // Streamlit patches list positions in place rather than always
            // replacing the DOM node, so once the list shrinks this exact
            // element can end up reused for a *different* surviving task - which
            // would otherwise render invisible (opacity still forced to 0 above)
            // forever. But Streamlit's patch can land in more than one mutation
            // (e.g. an intermediate update before the final content settles) -
            // cleaning up on the *first* mutation regardless of what it was used
            // to fire while this task itself was still mid-removal, undoing the
            // collapse and making it flash back to full size for a moment before
            // actually disappearing. Only clean up once we can tell *why*: either
            // this node left the document entirely (nothing to fix), or its
            // marker now names a genuinely different task (that one needs its
            // forced-zero styling cleared, not this one).
            const resolveIfSettled = () => {
                if (!el.isConnected) return true;
                const marker = el.querySelector('.task-card-marker');
                const currentTaskId = marker ? marker.getAttribute('data-task-id') : null;
                if (currentTaskId !== originalTaskId) {
                    cleanup();
                    return true;
                }
                return false;
            };
            const observer = new MutationObserver(() => {
                if (resolveIfSettled()) observer.disconnect();
            });
            observer.observe(el, { childList: true, subtree: true, attributes: true });
            // Safety net in case this node never mutates as expected.
            setTimeout(() => { observer.disconnect(); resolveIfSettled(); }, 800);
        }, 250);
    }

    // Streamlit resizes the main content pane the instant the sidebar is
    // collapsed/expanded (only the sidebar itself slides, over ~0.3s) — the
    // content pane's width snaps in a single frame, with nothing to visually
    // ease. Rather than fight React for control of that width, mask the snap
    // with a brief, deliberate opacity settle timed to the sidebar's slide,
    // so the change reads as an eased transition instead of a hard cut.
    function smoothMainResize() {
        const main = doc.querySelector('[data-testid="stMain"]');
        if (!main || main.dataset.resizing === 'true') return;
        main.dataset.resizing = 'true';
        main.style.setProperty('transition', 'opacity 0.16s ease-out', 'important');
        main.style.setProperty('opacity', '0.45', 'important');
        setTimeout(() => {
            main.style.setProperty('transition', 'opacity 0.22s ease-in', 'important');
            main.style.setProperty('opacity', '1', 'important');
            setTimeout(() => {
                main.style.removeProperty('transition');
                main.style.removeProperty('opacity');
                delete main.dataset.resizing;
            }, 240);
        }, 110);
    }

    // --- TRUE OPTIMISTIC UI: Event Delegation ---
    doc.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;

        if (btn.closest('[data-testid="stSidebarCollapseButton"], [data-testid="stExpandSidebarButton"]')) {
            smoothMainResize();
        }

        const txt = btn.innerText.trim();

        if (txt === '🗑️') {
            let target = null;
            if (!e.target.closest('div[data-testid="stExpanderDetails"]')) {
                target = findEnclosingCard(btn);
            } else {
                target = btn.closest('div[data-testid="stColumn"]')?.parentElement;
            }
            if (target && target.dataset.collapsing !== 'true') {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                collapseAndDelete(target, btn);
            }
        }
        else if (txt === '✔️' || txt === '↩️') {
            // Instantly flip the icon so it feels perfectly responsive
            const p = btn.querySelector('p');
            if (p) p.innerText = txt === '✔️' ? '↩️' : '✔️';

            // Subtasks aren't reordered by any sort, so an optimistic class toggle
            // here is safe. Main tasks ARE resorted (completed tasks jump to the
            // top) - toggling .is-done on "whatever card is at this DOM position"
            // ahead of the real rerun risks it landing on a *different* task once
            // the list reorders and Streamlit reuses that position for someone
            // else. Main-task done styling is driven purely by CSS reading the
            // server-rendered data-done attribute instead (see stylesheet), so it
            // only ever reflects the real state, just slightly less instantly.
            const isSubtask = btn.closest('div[data-testid="stExpanderDetails"]') !== null;
            if (isSubtask) {
                const subRow = btn.closest('div[data-testid="stColumn"]')?.parentElement.querySelector('.subtask-row');
                if (subRow) subRow.classList.toggle('is-done', txt === '✔️');
            }
        }
        else if (txt === 'Add task') {
            // Fades the button via CSS instead of breaking innerText react node sync
            btn.classList.add('optimistic-fade');
            
            window.textLocked = false;
            window.categorySelected = false;
            window.prioritySelected = false;
            window.dueSelected = false;
            const inputs = doc.querySelectorAll('input[placeholder="E.g., Review Big O time complexity"]');
            if(inputs.length) {
                inputs[0].value = ''; 
                inputs[0].blur();
            }
        }
        else if (txt.includes('Clear completed') || txt.includes('Clear all')) {
            const markers = doc.querySelectorAll('.task-card-marker');
            markers.forEach(m => {
                const c = m.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || m.closest('div[data-testid="stVerticalBlock"]');
                if (c) c.classList.add('optimistic-fade');
            });
        }
        
        // Match by the trailing hotkey bracket, not the label text: the category
        // "Custom" button and the due-preset "Custom [5]" button both contain the
        // substring "Custom", so plain text matching mis-detects which group a
        // click belongs to (and can leave Due/Add stuck hidden).
        const bracketMatch = txt.match(/\[([^\]]+)\]$/);
        const bracketKey = bracketMatch ? bracketMatch[1] : null;
        const isCat = ['H', 'W', 'S', 'P'].includes(bracketKey) || txt === 'Custom';
        const isPri = ['T', 'M', 'L'].includes(bracketKey);
        const isDue = ['1', '2', '3', '4', '5', '6'].includes(bracketKey);

        const isOptionBtn = (isCat || isPri || isDue);
        if (isOptionBtn && !txt.includes('Add task') && btn.closest('div[data-testid="stHorizontalBlock"]')) {
            const block = btn.closest('div[data-testid="stHorizontalBlock"]');
            if (block) {
                block.querySelectorAll('button').forEach(b => {
                    b.style.backgroundColor = '';
                    b.style.borderColor = 'rgba(128, 128, 128, 0.2)';
                    b.style.color = '';
                });
                btn.style.backgroundColor = '#ff4b4b';
                btn.style.borderColor = '#ff4b4b';
                btn.style.color = 'white';
                
                if (isCat) window.categorySelected = true;
                if (isPri) window.prioritySelected = true;
                if (isDue) window.dueSelected = true;
            }
        }
    }, true);

    // --- Click-to-complete: task cards have no checkmark button anymore.
    // Clicking any empty space on the card "arms" it (a light, obviously-
    // different fill, smoothly transitioned in) as a confirmation step; a
    // second click while armed actually commits the toggle by clicking the
    // real (hidden) Streamlit button for that task. Clicking anything
    // interactive within the card (pin/edit/delete, the subtask expander and
    // everything inside it) never arms/confirms, and disarms whatever else
    // was armed so a card can't get stuck lit up. ---
    let armedTaskId = null;
    function disarmCard(taskId) {
        const m = doc.querySelector(`.task-card-marker[data-task-id="${taskId}"]`);
        const c = m ? m.closest('div[data-testid="stVerticalBlock"]') : null;
        if (c) c.classList.remove('armed-complete');
        if (armedTaskId === taskId) armedTaskId = null;
    }
    doc.addEventListener('click', (e) => {
        const isInteractive = !!e.target.closest('button, a, input, textarea, [data-testid="stExpander"]');

        let clickedCard = null, clickedTaskId = null;
        const markers = doc.querySelectorAll('.task-card-marker');
        for (const m of markers) {
            const c = m.closest('div[data-testid="stVerticalBlock"]');
            if (c && c.contains(e.target)) {
                clickedCard = c;
                clickedTaskId = m.getAttribute('data-task-id');
                break;
            }
        }

        if (isInteractive) {
            if (armedTaskId && armedTaskId !== clickedTaskId) disarmCard(armedTaskId);
            return;
        }

        if (!clickedCard) {
            if (armedTaskId) disarmCard(armedTaskId);
            return;
        }

        if (armedTaskId && armedTaskId !== clickedTaskId) disarmCard(armedTaskId);

        if (clickedCard.classList.contains('armed-complete')) {
            disarmCard(clickedTaskId);
            const toggleMarker = clickedCard.querySelector('.hidden-toggle-marker');
            const container = toggleMarker ? toggleMarker.closest('div[data-testid="stElementContainer"]') : null;
            const hiddenBtn = container && container.nextElementSibling
                ? container.nextElementSibling.querySelector('button') : null;
            if (hiddenBtn) hiddenBtn.click();
        } else {
            clickedCard.classList.add('armed-complete');
            armedTaskId = clickedTaskId;
        }
    }, true);

    if (!doc.getElementById('enter-indicator')) {
        const style = doc.createElement('style');
        style.innerHTML = `
            #enter-indicator {
                position: fixed;
                bottom: 32px;
                right: 32px;
                background-color: rgba(128, 128, 128, 0.9); 
                color: #fff;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 0.9rem;
                font-weight: 600;
                opacity: 0;
                transform: translateY(10px);
                transition: all 0.2s ease, background-color 0.2s ease;
                pointer-events: none;
                z-index: 999999;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            }
            #enter-indicator.visible {
                opacity: 1;
                transform: translateY(0);
            }
        `;
        doc.head.appendChild(style);

        const indicator = doc.createElement('div');
        indicator.id = 'enter-indicator';
        doc.body.appendChild(indicator);
    }

    // Elegant Focus bindings for Subtasks (Robust Poller)
    setInterval(() => {
        const allCards = doc.querySelectorAll('.task-card-marker');
        let activeCard = null;

        if (doc.activeElement && doc.activeElement.tagName.toLowerCase() === 'input' && doc.activeElement.placeholder && doc.activeElement.placeholder.includes('Add a subtask')) {
            activeCard = findEnclosingCard(doc.activeElement);
        }

        allCards.forEach(marker => {
            const card = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || marker.closest('div[data-testid="stVerticalBlock"]');
            if (!card) return;
            if (card === activeCard) {
                card.classList.add('green-focus-border');
            } else {
                card.classList.remove('green-focus-border');
            }
        });
    }, 50);

    // Tracks whichever subtask panel the user most recently expanded by hand,
    // so the '/' hotkey can fall back to *that* task when it's not the newest
    // one. Tied directly to the click that opens it (checked right after the
    // native <details> toggle applies) rather than polled - polling for "which
    // panels are open right now changed since last tick" was noisy: any
    // unrelated rerun that happened to re-assert an expander's open state could
    // look like a fresh "just expanded" event and hijack the target, which is
    // exactly what made '/' occasionally jump to the wrong task.
    doc.addEventListener('click', (e) => {
        const summary = e.target.closest('div[data-testid="stExpander"] summary');
        if (!summary) return;
        setTimeout(() => {
            const details = summary.closest('details');
            if (details && details.open) {
                const tid = findTaskIdContaining(details);
                if (tid) window.lastExpandedTaskId = tid;
            }
        }, 20);
    }, true);

    function setupMagic() {
        const indicator = doc.getElementById('enter-indicator');
        
        setInterval(() => {
            const inputs = doc.querySelectorAll('input[type="text"]');
            let taskInput = null;
            let customInput = null;
            inputs.forEach(inp => {
                if(inp.placeholder === "E.g., Review Big O time complexity") taskInput = inp;
                if(inp.placeholder === "E.g., Groceries") customInput = inp;
            });
            
            const tracker = doc.getElementById('latest-task-tracker');
            if (tracker) {
                window.latestTaskId = tracker.getAttribute('data-task-id');
                tracker.removeAttribute('id'); 
            }
            
            const activeTag = doc.activeElement ? doc.activeElement.tagName.toLowerCase() : '';
            const isTyping = (activeTag === 'input' || activeTag === 'textarea');

            if (customInput && doc.activeElement === customInput) {
                indicator.classList.add('visible');
                indicator.innerText = 'Enter to confirm custom tag';
                indicator.style.backgroundColor = 'rgba(155, 89, 182, 0.95)'; 
            } else if (taskInput && taskInput.value.trim().length > 0) {
                indicator.classList.add('visible');
                
                if (!window.textLocked) {
                    indicator.innerText = 'Enter to lock text & open options';
                    indicator.style.backgroundColor = 'rgba(243, 156, 18, 0.95)';
                } else if (!window.categorySelected) {
                    indicator.innerText = 'Select a category (Use hotkeys)';
                    indicator.style.backgroundColor = 'rgba(52, 152, 219, 0.95)';
                } else if (!window.prioritySelected) {
                    indicator.innerText = 'Select a priority';
                    indicator.style.backgroundColor = 'rgba(52, 152, 219, 0.95)';
                } else if (!window.dueSelected) {
                    indicator.innerText = 'Select a due date';
                    indicator.style.backgroundColor = 'rgba(52, 152, 219, 0.95)';
                } else {
                    indicator.innerText = 'Enter to finish adding task';
                    indicator.style.backgroundColor = 'rgba(46, 204, 113, 0.95)';
                }
                
                const addTaskBtn = Array.from(doc.querySelectorAll('button')).find(b => b.innerText.includes('Add task') && !b.innerText.includes('Cancel'));
                if (addTaskBtn) {
                    if (window.textLocked && window.categorySelected && window.prioritySelected && window.dueSelected) {
                        addTaskBtn.style.backgroundColor = 'rgba(46, 204, 113, 1)'; 
                        addTaskBtn.style.borderColor = 'rgba(46, 204, 113, 1)';
                        addTaskBtn.style.color = 'white';
                        addTaskBtn.style.pointerEvents = 'auto';
                        addTaskBtn.style.opacity = '1';
                    } else {
                        addTaskBtn.style.backgroundColor = 'rgba(128, 128, 128, 0.4)'; 
                        addTaskBtn.style.borderColor = 'transparent';
                        addTaskBtn.style.color = 'rgba(255, 255, 255, 0.5)';
                        addTaskBtn.style.pointerEvents = 'none';
                    }
                }
                
            } else if (!isTyping && window.latestTaskId) {
                indicator.classList.add('visible');
                indicator.innerText = 'Press / to add subtasks to your new task';
                indicator.style.backgroundColor = 'rgba(46, 204, 113, 0.95)';
            } else {
                indicator.classList.remove('visible');
                const addTaskBtn = Array.from(doc.querySelectorAll('button')).find(b => b.innerText.includes('Add task') && !b.innerText.includes('Cancel'));
                if (addTaskBtn) {
                    addTaskBtn.style.backgroundColor = 'rgba(128, 128, 128, 0.4)'; 
                    addTaskBtn.style.borderColor = 'transparent';
                    addTaskBtn.style.color = 'rgba(255, 255, 255, 0.5)';
                    addTaskBtn.style.pointerEvents = 'none';
                }
            }
        }, 200);

        if (window.magicKeyboardAttached) return;
        window.magicKeyboardAttached = true;

        doc.addEventListener('keydown', function(e) {
            const inputs = doc.querySelectorAll('input[type="text"]');
            let taskInput = null;
            let customInput = null;
            inputs.forEach(inp => {
                if(inp.placeholder === "E.g., Review Big O time complexity") taskInput = inp;
                if(inp.placeholder === "E.g., Groceries") customInput = inp;
            });

            const activeTag = doc.activeElement ? doc.activeElement.tagName.toLowerCase() : '';

            // Login/Sign-up: Enter advances username -> password, then submits
            // the form natively (Streamlit auto-submits forms on Enter).
            if (e.key === 'Enter' && activeTag === 'input') {
                const advanceMap = {
                    'Enter your username': 'Enter your password',
                    'Pick a username': 'Pick a password',
                };
                const nextPlaceholder = advanceMap[doc.activeElement.placeholder];
                if (nextPlaceholder) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    const next = doc.querySelector(`input[placeholder="${nextPlaceholder}"]`);
                    if (next) next.focus();
                    return;
                }
            }

            const isTyping = (activeTag === 'input' || activeTag === 'textarea');
            const hasText = taskInput ? taskInput.value.trim().length > 0 : false;
            const key = e.key.toLowerCase();
            
            const isHotkey = ['1','2','3','4','5','6','h','w','s','p','t','m','l'].includes(key);

            if (!isTyping) {
                // Intercept and destroy Streamlit native hotkeys for our mapped keys —
                // but only once the task box already has text. Before that, a
                // hotkey-shaped letter (h/w/s/p/t/m/l/1-6) is just the first
                // character of a new task; consuming it here would focus the
                // (still-empty) box without actually typing the letter into it.
                if ((isHotkey && hasText) || key === '/') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }

                if (key === '/') {
                    let targetInput = null;
                    // Prefer the task that was added most recently (the common
                    // "just added a task, now add its subtasks" flow), then fall
                    // back to whichever panel was last expanded by hand.
                    const focusTaskId = window.latestTaskId || window.lastExpandedTaskId;

                    if (focusTaskId) {
                        const cardMarker = doc.querySelector(`.task-card-marker[data-task-id="${focusTaskId}"]`);
                        if (cardMarker) {
                            const targetCard = cardMarker.closest('div[data-testid="stVerticalBlock"]');
                            if (targetCard) {
                                const subInputs = targetCard.querySelectorAll('input[placeholder*="Add a subtask"]');
                                if (subInputs.length > 0) targetInput = subInputs[0];
                            }
                        }
                    }
                    
                    if (!targetInput) {
                        const subInputs = Array.from(doc.querySelectorAll('input[placeholder*="Add a subtask"]'))
                            .filter(inp => inp.getBoundingClientRect().height > 0);
                        if (subInputs.length > 0) targetInput = subInputs[0];
                    }
                    
                    if (targetInput) {
                        const detailsEl = targetInput.closest('details');
                        if (detailsEl && !detailsEl.open) {
                            const summary = detailsEl.querySelector('summary');
                            if (summary) summary.click();
                        }
                        
                        setTimeout(() => {
                            targetInput.focus();
                        }, 50);
                    }
                    
                    window.latestTaskId = null; 
                    return;
                }

                // Execute Hotkey selection (Even if Text is Locked, as long as it has text)
                if (hasText && isHotkey) {
                    const clickBtn = (textFragment) => {
                        const buttons = Array.from(doc.querySelectorAll('button'));
                        const btn = buttons.find(b => b.innerText.includes(textFragment) || b.innerText.trim() === textFragment);
                        if(btn) {
                            const parentRow = btn.closest('div[data-testid="stHorizontalBlock"]');
                            if(parentRow) {
                                const siblings = parentRow.querySelectorAll('button');
                                siblings.forEach(sib => {
                                    sib.style.removeProperty('background-color');
                                    sib.style.removeProperty('border-color');
                                    sib.style.removeProperty('color');
                                });
                            }
                            btn.style.backgroundColor = '#ff4b4b';
                            btn.style.borderColor = '#ff4b4b';
                            btn.style.color = 'white';
                            
                            btn.click();
                        }
                    };

                    if (key === '1') { clickBtn('Today [1]'); window.dueSelected = true; }
                    if (key === '2') { clickBtn('Tomorrow [2]'); window.dueSelected = true; }
                    if (key === '3') { clickBtn('This week [3]'); window.dueSelected = true; }
                    if (key === '4') { clickBtn('Next week [4]'); window.dueSelected = true; }
                    if (key === '5') { clickBtn('Custom [5]'); window.dueSelected = true; }
                    if (key === '6') { clickBtn('No date [6]'); window.dueSelected = true; }
                    
                    if (key === 'h') { clickBtn('House [H]'); window.categorySelected = true; }
                    if (key === 'w') { clickBtn('Work [W]'); window.categorySelected = true; }
                    if (key === 's') { clickBtn('Study [S]'); window.categorySelected = true; }
                    if (key === 'p') { clickBtn('Personal [P]'); window.categorySelected = true; }
                    
                    if (key === 't') { clickBtn('High [T]'); window.prioritySelected = true; }
                    if (key === 'm') { clickBtn('Medium [M]'); window.prioritySelected = true; }
                    if (key === 'l') { clickBtn('Low [L]'); window.prioritySelected = true; }
                    
                    return; 
                } 
                else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && taskInput) {
                    if (taskInput.value.trim().length === 0) {
                        taskInput.focus();
                    }
                }
            }

            if ((e.ctrlKey || e.metaKey) && !isTyping) {
                if (key === 'z') {
                    e.preventDefault();
                    const buttons = Array.from(doc.querySelectorAll('button'));
                    const undoBtn = buttons.find(b => b.innerText.includes('Undo'));
                    if (undoBtn && !undoBtn.disabled) undoBtn.click();
                } else if (key === 'y') {
                    e.preventDefault();
                    const buttons = Array.from(doc.querySelectorAll('button'));
                    const redoBtn = buttons.find(b => b.innerText.includes('Redo'));
                    if (redoBtn && !redoBtn.disabled) redoBtn.click();
                }
            }

            if (e.key === 'Enter') {
                if (activeTag === 'input' && doc.activeElement !== taskInput && doc.activeElement !== customInput) return; 
                
                if (customInput && doc.activeElement === customInput) {
                    e.preventDefault();
                    customInput.blur(); 
                    return;
                }
                
                if (taskInput && taskInput.value.trim().length > 0) {
                    e.preventDefault(); 
                    
                    // Lock text on first Enter
                    if (!window.textLocked) {
                        window.textLocked = true;
                        taskInput.blur(); 
                    } 
                    // Add Task on subsequent Enter ONLY IF all sections are filled
                    else if (window.textLocked && window.categorySelected && window.prioritySelected && window.dueSelected) {
                        const buttons = doc.querySelectorAll('button');
                        buttons.forEach(btn => {
                            if(btn.innerText.includes('Add task') && !btn.innerText.includes('Cancel')) {
                                btn.classList.add('optimistic-fade');
                                window.textLocked = false;
                                window.categorySelected = false;
                                window.prioritySelected = false;
                                window.dueSelected = false;
                                taskInput.value = '';
                                btn.click();
                            }
                        });
                    }
                }
            }
        }, true); 
    }
    
    setTimeout(setupMagic, 500);
    </script>
    """,
    height=0,
    width=0,
)
