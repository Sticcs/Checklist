import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
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
if "auth_msg" not in st.session_state:
    st.session_state.auth_msg = None

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
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

def _restore_state(state_tasks, username):
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        for t in state_tasks:
            conn.execute(
                "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at, username) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (t['id'], t['text'], t['done'], t['priority'], t['category'], t['due_date'], t['created_at'], username)
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
    return new_id

def set_done(task_id, done, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND username = ?", (int(done), task_id, username))
        conn.execute("UPDATE subtasks SET done = ? WHERE task_id = ?", (int(done), task_id))
        conn.commit()
    status = "completed" if done else "unmarked"
    st.session_state.pending_toast = f"✅ Task {status}"

def delete_task(task_id, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM subtasks WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Task deleted"

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

def clear_all(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute(
            "DELETE FROM subtasks WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)", (username,)
        )
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Cleared all tasks"

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
        conn.execute("UPDATE tasks SET done = 1 WHERE username = ?", (username,))
        conn.execute(
            "UPDATE subtasks SET done = 1 WHERE task_id IN (SELECT id FROM tasks WHERE username = ?)", 
            (username,)
        )
        conn.commit()
    st.session_state.pending_toast = "✅ Marked all as completed"

def update_task(task_id, text, priority, category, due_date, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute(
            "UPDATE tasks SET text = ?, priority = ?, category = ?, due_date = ? WHERE id = ? AND username = ?",
            (text, priority, category, due_date, task_id, username),
        )
        conn.commit()
    st.session_state.pending_toast = "💾 Task updated"

# ----------------------------- Callback Handlers -----------------------------

def handle_task_toggle(task_id, current_done, username):
    set_done(task_id, not current_done, username)

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

def attempt_login():
    l_user = st.session_state.get("login_user", "")
    l_pass = st.session_state.get("login_pass", "")
    if verify_user(l_user, l_pass):
        st.session_state.logged_in = True
        st.session_state.username = l_user.strip()
        st.session_state.auth_msg = None
    else:
        st.session_state.auth_msg = ("error", "Invalid username or password.")

def attempt_signup():
    s_user = st.session_state.get("sign_user", "")
    s_pass = st.session_state.get("sign_pass", "")
    if s_user and s_pass:
        if create_user(s_user, s_pass):
            st.session_state.auth_msg = ("success", "Account created! You can now log in.")
        else:
            st.session_state.auth_msg = ("error", "Username already exists. Pick another one.")
    else:
        st.session_state.auth_msg = ("warning", "Please fill in both fields.")

# ----------------------------- Styles & Theming -----------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORIES = ["House", "Work", "Study", "Personal", "Custom"]
PRIORITIES = ["High", "Medium", "Low"]

CAT_KEYS = {"House": "H", "Work": "W", "Study": "S", "Personal": "P", "Custom": ""}
PRI_KEYS = {"High": "T", "Medium": "M", "Low": "L"}

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem !important;
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
    div[data-testid="column"]:nth-child(2) div[data-testid="stButton"] button {
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
    
    div[data-testid="stButton"] button { 
        width: 100%;
        height: auto !important;
        padding: 0.4rem 0.2rem !important;
        transition: background-color 0.05s ease, border-color 0.05s ease, color 0.05s ease, transform 0.05s ease !important;
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

    div[data-testid="stVerticalBlockBorderWrapper"]:has(div[data-testid="stExpander"]) {
        border-radius: 14px !important;
        padding: 0.6rem 0.9rem 0.9rem 0.9rem !important;
        margin-bottom: 0.7rem !important;
    }

    /* Force transparency on Streamlit Expander to allow parent background to bleed through */
    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        background-color: transparent !important;
        transition: all 0.3s ease;
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
        transition: opacity 0.05s ease;
        margin: 0 !important;
        padding: 0.4rem 0 !important;
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
        
        # Display any auth messages from callbacks
        if st.session_state.auth_msg:
            msg_type, msg_text = st.session_state.auth_msg
            if msg_type == "error":
                st.error(msg_text)
            elif msg_type == "success":
                st.success(msg_text)
            elif msg_type == "warning":
                st.warning(msg_text)
            st.session_state.auth_msg = None
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            st.text_input("Username", key="login_user")
            # Binding on_change directly to the password field triggers the function when Enter is pressed
            st.text_input("Password", type="password", key="login_pass", on_change=attempt_login)
            st.button("Login", type="primary", use_container_width=True, on_click=attempt_login)
                    
        with tab2:
            st.text_input("Choose a Username", key="sign_user")
            # Binding on_change directly to the password field triggers the function when Enter is pressed
            st.text_input("Choose a Password", type="password", key="sign_pass", on_change=attempt_signup)
            st.button("Create Account", type="primary", use_container_width=True, on_click=attempt_signup)
                    
        st.write("---")
        if st.button("Continue as Guest", type="secondary", use_container_width=True):
            st.session_state.logged_in = True
            st.session_state.username = "guest"
            st.rerun()

else:
    st.markdown(
        """
        <style>
        /* --- Right List Column Scrolling --- */
        div[data-testid="column"]:has(#right-col-anchor) {
            height: 88vh !important;
            max-height: 88vh !important;
            overflow-y: scroll !important;
            scroll-behavior: smooth !important;
            padding-right: 15px !important;
            -ms-overflow-style: none !important; 
            scrollbar-width: none !important; 
        }
        div[data-testid="column"]:has(#right-col-anchor)::-webkit-scrollbar {
            display: none !important;
        }

        /* --- Left Control Panel (Glassmorphism & Legibility) --- */
        div[data-testid="column"]:has(#left-panel-marker) {
            background: rgba(255, 255, 255, 0.65) !important;
            padding: 1.5rem !important;
            border-radius: 16px !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            height: fit-content !important;
        }
        body.custom-dark div[data-testid="column"]:has(#left-panel-marker) {
            background: rgba(14, 17, 23, 0.55) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
        }

        /* Captions: Category, Priority, Due */
        div[data-testid="column"]:has(#left-panel-marker) div[data-testid="stCaptionContainer"] p {
            color: #2c3e50 !important;
            font-weight: 700 !important;
            font-size: 0.85rem !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 0.5rem;
        }
        body.custom-dark div[data-testid="column"]:has(#left-panel-marker) div[data-testid="stCaptionContainer"] p {
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
    st.session_state.setdefault("new_category", "House")
    st.session_state.setdefault("new_priority", "Medium")
    st.session_state.setdefault("new_due_preset", "No date")
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
        if text:
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
            if "custom_cat_input" in st.session_state:
                st.session_state.custom_cat_input = ""

    tasks = get_tasks(st.session_state.username)
    sidebar_categories = sorted({t["category"] for t in tasks}) if tasks else []

    # ----------------------------- Sidebar -----------------------------

    with st.sidebar:
        st.markdown(f"<div class='profile-indicator'><span>👤</span> {st.session_state.username}</div>", unsafe_allow_html=True)
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
        category_filter = st.multiselect("Category", sidebar_categories, default=sidebar_categories)
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
            
        st.write("")
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
            valid_logs = [t for t in tasks if t['done'] and len(t['text'].strip()) >= 3]
            if not valid_logs:
                st.caption("No recent activities.")
            else:
                for log in valid_logs[:10]:
                    st.markdown(f"<span style='opacity: 0.7; font-size: 0.85rem;'>{log['text']}</span>", unsafe_allow_html=True)

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
            st.markdown("<div id='step-cat-marker'></div>", unsafe_allow_html=True)
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

        with st.container():
            st.markdown("<div id='step-pri-marker'></div>", unsafe_allow_html=True)
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

        with st.container():
            st.markdown("<div id='step-due-marker'></div>", unsafe_allow_html=True)
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

        if sort_by == "Priority":
            filtered.sort(key=lambda t: PRIORITY_ORDER.get(t["priority"], 3))
        elif sort_by == "Due date":
            filtered.sort(key=lambda t: (t["due_date"] is None, t["due_date"]))

        st.write("")
        st.write("")
        if tasks:
            done_count = sum(1 for t in tasks if t["done"])
            st.progress(done_count / len(tasks), text=f"{done_count} / {len(tasks)} completed")
        
        st.write("")

        if not filtered:
            st.caption("No tasks match your filters yet.")
        else:
            today = _get_local_today().isoformat()
            now_time = datetime.now()
            
            for t in filtered:
                with st.container(border=True):
                    st.markdown(f"<div class='task-card-marker' data-task-id='{t['id']}' style='display:none;'></div>", unsafe_allow_html=True)
                    
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
                        
                        html_string = f"""<div class="task-row border-{t['priority']} {done_class} {anim_class}"><div class="task-title {done_class}"><span>{t['text']}</span>{urgent_html}</div><div class="meta-tags">{tags_html}</div></div>"""
                        
                        st.markdown(html_string, unsafe_allow_html=True)
                        
                        # ---------------- Subtasks ----------------
                        subtasks = get_subtasks(t["id"])
                        sub_total = len(subtasks)
                        sub_done = sum(1 for s in subtasks if s["done"])

                        if sub_total > 0:
                            st.markdown('<div class="subtask-progress-wrap">', unsafe_allow_html=True)
                            st.progress(sub_done / sub_total, text=f"Subtasks: {sub_done}/{sub_total}")
                            st.markdown('</div>', unsafe_allow_html=True)

                        expander_label = f"📋 Subtasks ({sub_done}/{sub_total})" if sub_total else "📋 Add subtasks"
                        
                        is_expanded = (st.session_state.active_task_id == t["id"])
                        
                        with st.expander(expander_label, expanded=is_expanded):
                            for i, s in enumerate(subtasks):
                                sc_main, sc_btn = st.columns([9, 0.8], vertical_alignment="center")
                                with sc_main:
                                    sub_class = "is-done" if s["done"] else ""
                                    st.markdown(
                                        f'<div class="subtask-row {sub_class}">{s["text"]}</div>',
                                        unsafe_allow_html=True,
                                    )
                                with sc_btn:
                                    if s["done"]:
                                        st.button("↩️", key=f"subtog_{s['id']}", help="Mark incomplete", 
                                                  on_click=handle_subtask_toggle, args=(s["id"], t["id"], bool(s["done"]), st.session_state.username), use_container_width=True)
                                    else:
                                        st.button("✔️", key=f"subtog_{s['id']}", help="Mark complete", 
                                                  on_click=handle_subtask_toggle, args=(s["id"], t["id"], bool(s["done"]), st.session_state.username), use_container_width=True)
                                        
                                    st.button("🗑️", key=f"subdel_{s['id']}", help="Delete subtask",
                                              on_click=handle_subtask_delete, args=(s["id"], t["id"], st.session_state.username), use_container_width=True)
                                
                                # Subtask Divider
                                if i < len(subtasks) - 1:
                                    st.markdown("<hr style='margin: 0.15rem 0; border: none; border-top: 1px solid rgba(128, 128, 128, 0.15);' />", unsafe_allow_html=True)

                            st.caption("⚡ Press `/` to quickly start typing a subtask")
                            new_sc1, new_sc2 = st.columns([6, 1.5])
                            with new_sc1:
                                st.text_input(
                                    "New subtask",
                                    key=f"new_sub_{t['id']}",
                                    placeholder="Add a subtask... (Press '/' to focus)",
                                    label_visibility="collapsed",
                                    on_change=handle_subtask_add, 
                                    args=(t['id'], st.session_state.username)
                                )
                            with new_sc2:
                                st.button("Add", key=f"addsub_{t['id']}", use_container_width=True,
                                          on_click=handle_subtask_add, args=(t['id'], st.session_state.username))

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
                        if t["done"]:
                            st.button("↩️", key=f"tog_{t['id']}", help="Mark incomplete", 
                                      on_click=handle_task_toggle, args=(t["id"], bool(t["done"]), st.session_state.username), use_container_width=True)
                        else:
                            st.button("✔️", key=f"tog_{t['id']}", help="Mark complete", 
                                      on_click=handle_task_toggle, args=(t["id"], bool(t["done"]), st.session_state.username), use_container_width=True)
                        
                        if st.button("✏️", key=f"edit_{t['id']}", help="Edit task", use_container_width=True):
                            st.session_state[f"editing_{t['id']}"] = True
                        st.button("🗑️", key=f"del_{t['id']}", help="Delete task",
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
        const isDark = doc.body.classList.contains('custom-dark');
        const bg = window.getComputedStyle(doc.querySelector('.stApp') || doc.body).backgroundColor;
        const rgb = bg.match(/\d+/g);
        if (rgb && rgb.length >= 3) {
            const luma = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
            if (luma < 128 && !isDark) {
                doc.body.classList.add('custom-dark');
                doc.body.classList.remove('custom-light');
            } else if (luma >= 128 && isDark) {
                doc.body.classList.add('custom-light');
                doc.body.classList.remove('custom-dark');
            }
        }
        
        try {
            // Forcefully inject background colors via JS bypassing Streamlit's class engine entirely
            const markers = doc.querySelectorAll('.task-card-marker');
            markers.forEach(marker => {
                let card = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]');
                if (!card) card = marker.closest('div[data-testid="stVerticalBlock"]');
                if (!card) return;
                
                const isDone = card.querySelector('.task-row.is-done') !== null;
                const hasHigh = card.querySelector('.border-High') !== null;
                const hasMed = card.querySelector('.border-Medium') !== null;
                const hasLow = card.querySelector('.border-Low') !== null;
                
                card.style.setProperty('transition', 'background-color 0.3s ease, border-color 0.3s ease', 'important');
                
                if (isDone) {
                    card.style.setProperty('background-color', isDark ? 'rgba(29, 131, 72, 1)' : 'rgba(46, 204, 113, 1)', 'important');
                    card.style.setProperty('border-color', isDark ? 'rgba(20, 90, 50, 1)' : 'rgba(39, 174, 96, 1)', 'important');
                } else if (hasHigh) {
                    card.style.setProperty('background-color', isDark ? 'rgba(100, 30, 22, 0.85)' : 'rgba(250, 219, 216, 0.85)', 'important');
                    card.style.setProperty('border-color', 'rgba(231, 76, 60, 0.8)', 'important');
                } else if (hasMed) {
                    card.style.setProperty('background-color', isDark ? 'rgba(126, 81, 9, 0.85)' : 'rgba(253, 235, 208, 0.85)', 'important');
                    card.style.setProperty('border-color', 'rgba(243, 156, 18, 0.8)', 'important');
                } else if (hasLow) {
                    card.style.setProperty('background-color', isDark ? 'rgba(21, 67, 96, 0.85)' : 'rgba(214, 234, 248, 0.85)', 'important');
                    card.style.setProperty('border-color', 'rgba(52, 152, 219, 0.8)', 'important');
                }
            });
        } catch(e) {}
    }, 100);

    // Persist Scroll memory
    if (!doc.getElementById('scroll-controls')) {
        const controls = doc.createElement('div');
        controls.id = 'scroll-controls';
        controls.innerHTML = `
            <button id="scroll-up" style="background: rgba(128, 128, 128, 0.2); border: none; border-radius: 50%; width: 36px; height: 36px; cursor: pointer; color: inherit; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(5px); margin-bottom: 8px;">↑</button>
            <button id="scroll-down" style="background: rgba(128, 128, 128, 0.2); border: none; border-radius: 50%; width: 36px; height: 36px; cursor: pointer; color: inherit; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(5px);">↓</button>
        `;
        controls.style.cssText = 'position: fixed; right: 32px; bottom: 90px; display: flex; flex-direction: column; z-index: 9999; opacity: 0.7; transition: opacity 0.2s ease;';
        
        controls.onmouseover = () => controls.style.opacity = '1';
        controls.onmouseout = () => controls.style.opacity = '0.7';

        doc.body.appendChild(controls);

        const getScrollCol = () => {
            const anchor = doc.getElementById('right-col-anchor');
            return anchor ? anchor.closest('div[data-testid="column"]') : null;
        };

        controls.querySelector('#scroll-up').onclick = () => {
            const col = getScrollCol();
            if(col) col.scrollTo({top: 0, behavior: 'smooth'});
        };
        controls.querySelector('#scroll-down').onclick = () => {
            const col = getScrollCol();
            if(col) col.scrollTo({top: col.scrollHeight, behavior: 'smooth'});
        };
        
        setInterval(() => {
            const col = getScrollCol();
            if (col && !col.dataset.scrollBound) {
                col.dataset.scrollBound = "true";
                const savedScroll = sessionStorage.getItem('rightColScroll');
                if (savedScroll !== null) {
                    col.scrollTop = parseInt(savedScroll);
                }
                col.addEventListener('scroll', () => {
                    sessionStorage.setItem('rightColScroll', col.scrollTop);
                });
            }
        }, 300);
    }

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
            if (block && !block.classList.contains('progressive-base')) {
                block.classList.add('progressive-base');
                block.classList.add('progressive-hidden');
            }
        });

        if (taskInput && taskInput.value.trim().length === 0) {
            window.textLocked = false;
            window.categorySelected = false;
            window.prioritySelected = false;
            window.dueSelected = false;
        }

        if (window.textLocked) {
            catBlock?.classList.add('progressive-visible');
            catBlock?.classList.remove('progressive-hidden');
        } else {
            catBlock?.classList.add('progressive-hidden');
            catBlock?.classList.remove('progressive-visible');
        }

        if (window.textLocked && window.categorySelected) {
            priBlock?.classList.add('progressive-visible');
            priBlock?.classList.remove('progressive-hidden');
        } else {
            priBlock?.classList.add('progressive-hidden');
            priBlock?.classList.remove('progressive-visible');
        }

        if (window.textLocked && window.categorySelected && window.prioritySelected) {
            dueBlock?.classList.add('progressive-visible');
            dueBlock?.classList.remove('progressive-hidden');
        } else {
            dueBlock?.classList.add('progressive-hidden');
            dueBlock?.classList.remove('progressive-visible');
        }

        if (window.textLocked && window.categorySelected && window.prioritySelected && window.dueSelected) {
            addBlock?.classList.add('progressive-visible');
            addBlock?.classList.remove('progressive-hidden');
        } else {
            addBlock?.classList.add('progressive-hidden');
            addBlock?.classList.remove('progressive-visible');
        }
    }, 100);

    // --- TRUE OPTIMISTIC UI: Event Delegation ---
    doc.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        
        const txt = btn.innerText.trim();
        
        if (txt === '🗑️') {
            const marker = btn.closest('div[data-testid="stVerticalBlockBorderWrapper"]')?.querySelector('.task-card-marker');
            if (marker && !e.target.closest('div[data-testid="stExpanderDetails"]')) {
                const card = marker.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || marker.closest('div[data-testid="stVerticalBlock"]');
                if (card) card.classList.add('optimistic-fade');
            } else {
                const row = btn.closest('div[data-testid="column"]')?.parentElement;
                if (row) row.classList.add('optimistic-fade');
            }
        }
        else if (txt === '✔️' || txt === '↩️') {
            // Instantly flip the icon so it feels perfectly responsive
            const p = btn.querySelector('p');
            if (p) p.innerText = txt === '✔️' ? '↩️' : '✔️';
            
            // Instantly apply visual toggle logic
            const isSubtask = btn.closest('div[data-testid="stExpanderDetails"]') !== null;
            if (isSubtask) {
                const subRow = btn.closest('div[data-testid="column"]')?.parentElement.querySelector('.subtask-row');
                if (subRow) subRow.classList.toggle('is-done', txt === '✔️');
            } else {
                const card = btn.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || btn.closest('div[data-testid="stVerticalBlock"]');
                if (card) {
                    const mainRow = card.querySelector('.task-row');
                    const mainTitle = card.querySelector('.task-title');
                    if (mainRow) mainRow.classList.toggle('is-done', txt === '✔️');
                    if (mainTitle) mainTitle.classList.toggle('is-done', txt === '✔️');
                }
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
        
        const isCat = ['House', 'Work', 'Study', 'Personal', 'Custom'].some(kw => txt.includes(kw));
        const isPri = ['High', 'Medium', 'Low'].some(kw => txt.includes(kw));
        const isDue = ['Today', 'Tomorrow', 'This week', 'Next week', 'No date'].some(kw => txt.includes(kw));
        
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
            const m = doc.activeElement.closest('div[data-testid="stVerticalBlockBorderWrapper"]')?.querySelector('.task-card-marker');
            if (m) activeCard = m.closest('div[data-testid="stVerticalBlockBorderWrapper"]') || m.closest('div[data-testid="stVerticalBlock"]');
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
            const isTyping = (activeTag === 'input' || activeTag === 'textarea');
            const hasText = taskInput ? taskInput.value.trim().length > 0 : false;
            const key = e.key.toLowerCase();
            
            const isHotkey = ['1','2','3','4','5','6','h','w','s','p','t','m','l'].includes(key);

            if (!isTyping) {
                // Intercept and destroy Streamlit native hotkeys for our mapped keys
                if (isHotkey || key === '/') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }

                if (key === '/') {
                    let targetInput = null;
                    
                    if (window.latestTaskId) {
                        const cardMarker = doc.querySelector(`.task-card-marker[data-task-id="${window.latestTaskId}"]`);
                        if (cardMarker) {
                            const targetCard = cardMarker.closest('div[data-testid="stVerticalBlockBorderWrapper"]');
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
                    if (key === '5') { clickBtn('Custom'); window.dueSelected = true; }
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
