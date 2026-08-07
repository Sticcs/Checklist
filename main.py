import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
from datetime import date, timedelta, datetime
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

# Global Toast Queue
if "pending_toast" in st.session_state:
    st.toast(st.session_state.pending_toast)
    del st.session_state.pending_toast

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
        conn.execute(
            "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username) "
            "VALUES (?, 0, ?, ?, ?, ?, ?)",
            (text, priority, category or "General", due_date, datetime.now().isoformat(), username),
        )
        conn.commit()
    st.session_state.pending_toast = "✅ Task added"

def set_done(task_id, done, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ? AND username = ?", (int(done), task_id, username))
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
        conn.commit()
    st.session_state.pending_toast = "➕ Subtask added"

def set_subtask_done(subtask_id, done, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE subtasks SET done = ? WHERE id = ?", (int(done), subtask_id))
        conn.commit()

def delete_subtask(subtask_id, username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Subtask deleted"

def mark_all_completed(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("UPDATE tasks SET done = 1 WHERE username = ?", (username,))
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

def handle_task_check(task_id, username):
    st.session_state.active_task_id = None 
    new_done = st.session_state[f"chk_{task_id}"]
    set_done(task_id, new_done, username)

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

def handle_subtask_check(subtask_id, task_id, username):
    st.session_state.active_task_id = task_id
    key = f"subchk_{subtask_id}"
    new_done = st.session_state[key]
    set_subtask_done(subtask_id, new_done, username)

def handle_subtask_delete(subtask_id, task_id, username):
    st.session_state.active_task_id = task_id
    delete_subtask(subtask_id, username)

# ----------------------------- Styles & Theming -----------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORIES = ["House", "Work", "Study", "Personal", "Custom"]
PRIORITIES = ["High", "Medium", "Low"]

CAT_KEYS = {"House": "H", "Work": "W", "Study": "S", "Personal": "P", "Custom": "C"}
PRI_KEYS = {"High": "T", "Medium": "M", "Low": "L"}

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem !important;
    }

    .stApp {
        background-attachment: fixed !important;
        background-size: cover !important;
        background-position: center !important;
        transition: background-image 0.3s ease;
    }
    [data-testid="stSidebar"] {
        box-shadow: 5px 0 25px rgba(0,0,0,0.5);
        transition: transform 0.3s ease, box-shadow 0.3s ease, background-color 0.3s ease;
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
    body.custom-dark .main .block-container {
        background-color: rgba(14, 17, 23, 0.65);
        border-radius: 16px;
        padding: 2rem;
        margin-top: 2rem;
        backdrop-filter: blur(8px);
    }
    body.custom-light .stApp {
        background-image: url("https://img.magnific.com/free-vector/green-monstera-leaves-with-copy-space-vector_53876-111532.jpg?semt=ais_hybrid&w=740&q=80") !important;
    }
    body.custom-light [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.85) !important;
        box-shadow: 5px 0 25px rgba(0,0,0,0.15);
        backdrop-filter: blur(10px);
    }
    body.custom-light .main .block-container {
        background-color: rgba(255, 255, 255, 0.85);
        border-radius: 16px;
        padding: 2rem;
        margin-top: 2rem;
        backdrop-filter: blur(8px);
    }
    h1, h2, h3, h4 {
        font-weight: 500 !important;
        letter-spacing: -0.5px;
    }
    
    #dynamic-header {
        font-size: 2.75rem;
        font-weight: 700;
        margin-bottom: 1.5rem;
        margin-top: 0.5rem;
        transition: opacity 0.6s ease-in-out;
        min-height: 4rem; 
        display: flex;
        align-items: center;
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
        transition: background-color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
    }
    body.custom-dark div[data-testid="stVerticalBlockBorderWrapper"]:has(div[data-testid="stExpander"]) {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    body.custom-light div[data-testid="stVerticalBlockBorderWrapper"]:has(div[data-testid="stExpander"]) {
        background-color: rgba(255, 255, 255, 0.92) !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        transition: all 0.3s ease;
    }
    div[data-testid="stExpander"] summary {
        transition: opacity 0.2s ease;
        padding: 0.3rem 0 !important;
    }
    div[data-testid="stExpander"] summary svg {
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[data-testid="stExpanderDetails"] {
        animation: expandFade 0.3s ease;
        transition: all 0.3s ease;
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
    }
    .subtask-row.is-done {
        text-decoration: line-through;
        opacity: 0.5;
    }
    
    .no-scrollbar-col::-webkit-scrollbar {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()

# ----------------------------- Auth Routing -----------------------------

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; margin-top: 2rem;'>✅ My Checklist</h1>", unsafe_allow_html=True)
        st.write("")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            l_user = st.text_input("Username", key="login_user")
            l_pass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login", type="primary", use_container_width=True):
                if verify_user(l_user, l_pass):
                    st.session_state.logged_in = True
                    st.session_state.username = l_user.strip()
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    
        with tab2:
            s_user = st.text_input("Choose a Username", key="sign_user")
            s_pass = st.text_input("Choose a Password", type="password", key="sign_pass")
            if st.button("Create Account", type="primary", use_container_width=True):
                if s_user and s_pass:
                    if create_user(s_user, s_pass):
                        st.success("Account created! You can now log in.")
                    else:
                        st.error("Username already exists. Pick another one.")
                else:
                    st.warning("Please fill in both fields.")

else:
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
        "Today": lambda: date.today().isoformat(),
        "Tomorrow": lambda: (date.today() + timedelta(days=1)).isoformat(),
        "This week": lambda: _end_of_week(date.today()).isoformat(),
        "Next week": lambda: (_end_of_week(date.today()) + timedelta(days=7)).isoformat(),
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
                    
            add_task(text, st.session_state.new_priority, cat, due_date, st.session_state.username)
            
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
        st.markdown("<div id='dynamic-header'>Stay locked in.</div>", unsafe_allow_html=True)
        st.markdown(f"<div id='options-state' data-modified='{str(st.session_state.options_modified).lower()}' style='display:none;'></div>", unsafe_allow_html=True)

        st.text_input(
            "Task",
            placeholder="E.g., Review Big O time complexity",
            key="task_input",
            label_visibility="collapsed",
        )

        st.caption("Category")
        cat_cols = st.columns(len(CATEGORIES), gap="small")
        for col, cat in zip(cat_cols, CATEGORIES):
            with col:
                st.button(
                    f"{cat} [{CAT_KEYS[cat]}]",
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

        st.write("")
        st.button("Add task", on_click=submit_new_task, type="primary")

    with spacer_col:
        st.empty()

    with right_col:
        st.markdown("<div id='right-col-anchor'></div>", unsafe_allow_html=True)
        
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
            today = date.today().isoformat()
            now_time = datetime.now()
            
            for t in filtered:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([0.4, 7.5, 1.5], vertical_alignment="center")
                    
                    with col1:
                        st.checkbox("", value=bool(t["done"]), key=f"chk_{t['id']}", 
                                    on_change=handle_task_check, args=(t["id"], st.session_state.username))
                            
                    with col2:
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
                        
                    with col3:
                        d1, d2 = st.columns(2)
                        with d1:
                            if st.button("Edit", key=f"edit_{t['id']}", help="Edit task"):
                                st.session_state[f"editing_{t['id']}"] = True
                        with d2:
                            st.button("Del", key=f"del_{t['id']}", help="Delete task",
                                      on_click=handle_task_delete, args=(t["id"], st.session_state.username))

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
                        for s in subtasks:
                            sc1, sc2, sc3 = st.columns([0.5, 6.5, 1], vertical_alignment="center")
                            with sc1:
                                st.checkbox("", value=bool(s["done"]), key=f"subchk_{s['id']}",
                                            on_change=handle_subtask_check, args=(s["id"], t["id"], st.session_state.username))
                            with sc2:
                                sub_class = "is-done" if s["done"] else ""
                                st.markdown(
                                    f'<div class="subtask-row {sub_class}">{s["text"]}</div>',
                                    unsafe_allow_html=True,
                                )
                            with sc3:
                                st.button("✕", key=f"subdel_{s['id']}", help="Delete subtask",
                                          on_click=handle_subtask_delete, args=(s["id"], t["id"], st.session_state.username))

                        new_sc1, new_sc2 = st.columns([6, 1.5])
                        with new_sc1:
                            st.text_input(
                                "New subtask",
                                key=f"new_sub_{t['id']}",
                                placeholder="Add a subtask...",
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

# ----------------------------- Custom JavaScript Injection -----------------------------
components.html(
    """
    <script>
    const doc = window.parent.document;
    
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
            }, 600); 
        }
    }, 8000); 

    setInterval(() => {
        const bg = window.getComputedStyle(doc.querySelector('.stApp') || doc.body).backgroundColor;
        const rgb = bg.match(/\d+/g);
        if (rgb && rgb.length >= 3) {
            const luma = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
            if (luma < 128) {
                doc.body.classList.add('custom-dark');
                doc.body.classList.remove('custom-light');
            } else {
                doc.body.classList.add('custom-light');
                doc.body.classList.remove('custom-dark');
            }
        }
    }, 200);

    setInterval(() => {
        const anchor = doc.getElementById('right-col-anchor');
        if (anchor) {
            const rightCol = anchor.closest('div[data-testid="column"]');
            if (rightCol && rightCol.style.overflowY !== 'auto') {
                rightCol.style.height = '85vh';
                rightCol.style.overflowY = 'auto';
                rightCol.style.paddingRight = '12px';
                rightCol.style.scrollBehavior = 'smooth';
                rightCol.style.scrollbarWidth = 'none'; 
                rightCol.style.msOverflowStyle = 'none';
                rightCol.classList.add('no-scrollbar-col');
            }
        }
    }, 500);

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

        doc.getElementById('scroll-up').onclick = () => {
            const anchor = doc.getElementById('right-col-anchor');
            if(anchor) anchor.closest('div[data-testid="column"]').scrollTo({top: 0, behavior: 'smooth'});
        };
        doc.getElementById('scroll-down').onclick = () => {
            const anchor = doc.getElementById('right-col-anchor');
            if(anchor) {
                const col = anchor.closest('div[data-testid="column"]');
                col.scrollTo({top: col.scrollHeight, behavior: 'smooth'});
            }
        };
    }

    setInterval(() => {
        const optionBtns = doc.querySelectorAll('div[data-testid="stButton"] button');
        optionBtns.forEach(btn => {
            if (!btn.dataset.magicClick) {
                btn.dataset.magicClick = "true";
                btn.addEventListener('mousedown', function() {
                    const btnText = this.innerText;
                    if (!btnText.includes('Add task') && this.closest('div[data-testid="stHorizontalBlock"]')) {
                        const siblings = this.closest('div[data-testid="stHorizontalBlock"]').querySelectorAll('button');
                        siblings.forEach(sib => {
                            sib.style.removeProperty('background-color');
                            sib.style.removeProperty('border-color');
                            sib.style.removeProperty('color');
                        });
                        this.style.backgroundColor = '#ff4b4b';
                        this.style.borderColor = '#ff4b4b';
                        this.style.color = 'white';
                    }
                });
            }
        });
    }, 500);

    doc.addEventListener('change', function(e) {
        if (e.target && e.target.type === 'checkbox') {
            const block = e.target.closest('div[data-testid="stHorizontalBlock"]');
            if (block) {
                const row = block.querySelector('.task-row');
                const subRow = block.querySelector('.subtask-row');
                
                if (row) {
                    if (e.target.checked) {
                        row.classList.add('is-done');
                        const title = row.querySelector('.task-title');
                        if (title) title.classList.add('is-done');
                    } else {
                        row.classList.remove('is-done');
                        const title = row.querySelector('.task-title');
                        if (title) title.classList.remove('is-done');
                    }
                }
                
                if (subRow) {
                    if (e.target.checked) {
                        subRow.classList.add('is-done');
                    } else {
                        subRow.classList.remove('is-done');
                    }
                }
            }
        }
    });

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
            
            const optState = doc.getElementById('options-state');
            const isModified = optState ? optState.getAttribute('data-modified') === 'true' : false;
            
            const buttons = Array.from(doc.querySelectorAll('button'));
            const addTaskBtn = buttons.find(b => b.innerText.includes('Add task') && !b.innerText.includes('Cancel'));
            
            if (addTaskBtn) {
                addTaskBtn.style.transition = 'background-color 0.05s ease, color 0.05s ease, border-color 0.05s ease';
            }

            if (customInput && doc.activeElement === customInput) {
                indicator.classList.add('visible');
                indicator.innerText = 'Enter to lock custom tag';
                indicator.style.backgroundColor = 'rgba(155, 89, 182, 0.95)'; 
            } else if (taskInput && taskInput.value.trim().length > 0) {
                indicator.classList.add('visible');
                
                if (doc.activeElement === taskInput) {
                    indicator.innerText = 'Enter to lock text & set options';
                    indicator.style.backgroundColor = 'rgba(243, 156, 18, 0.95)';
                } else {
                    indicator.innerText = 'Enter again to add task';
                    indicator.style.backgroundColor = 'rgba(46, 204, 113, 0.95)';
                }
                
                if (addTaskBtn) {
                    if (isModified) {
                        addTaskBtn.style.backgroundColor = 'rgba(46, 204, 113, 1)'; 
                        addTaskBtn.style.borderColor = 'rgba(46, 204, 113, 1)';
                        addTaskBtn.style.color = 'white';
                        addTaskBtn.style.pointerEvents = 'auto';
                        addTaskBtn.style.opacity = '1';
                    } else {
                        addTaskBtn.style.backgroundColor = 'rgba(243, 156, 18, 1)'; 
                        addTaskBtn.style.borderColor = 'rgba(243, 156, 18, 1)';
                        addTaskBtn.style.color = 'white';
                        addTaskBtn.style.pointerEvents = 'auto';
                        addTaskBtn.style.opacity = '1';
                    }
                }
                
            } else {
                indicator.classList.remove('visible');
                
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
            
            const isHotkey = ['1','2','3','4','5','6','h','w','s','p','c','t','m','l'].includes(key);

            if (!isTyping) {
                // Focus into an active Subtask box automatically
                if (key === '/') {
                    const subInputs = Array.from(doc.querySelectorAll('input[placeholder="Add a subtask..."]'))
                        .filter(inp => inp.getBoundingClientRect().height > 0);
                    if (subInputs.length > 0) {
                        e.preventDefault();
                        subInputs[0].focus();
                        return;
                    }
                }

                if (hasText && isHotkey) {
                    e.preventDefault(); 
                    
                    const clickBtn = (textFragment) => {
                        const buttons = Array.from(doc.querySelectorAll('button'));
                        const btn = buttons.find(b => b.innerText.includes(textFragment));
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

                    if (key === '1') clickBtn('Today');
                    if (key === '2') clickBtn('Tomorrow');
                    if (key === '3') clickBtn('This week');
                    if (key === '4') clickBtn('Next week');
                    if (key === '5') clickBtn('Custom');
                    if (key === '6') clickBtn('No date');
                    
                    if (key === 'h') clickBtn('House');
                    if (key === 'w') clickBtn('Work');
                    if (key === 's') clickBtn('Study');
                    if (key === 'p') clickBtn('Personal');
                    if (key === 'c') clickBtn('Custom');
                    
                    if (key === 't') clickBtn('High');
                    if (key === 'm') clickBtn('Medium');
                    if (key === 'l') clickBtn('Low');
                    
                    return; 
                } 
                else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && taskInput) {
                    taskInput.focus();
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
                    
                    if (doc.activeElement === taskInput) {
                        taskInput.blur(); 
                    } else {
                        setTimeout(() => {
                            const buttons = doc.querySelectorAll('button');
                            buttons.forEach(btn => {
                                if(btn.innerText.includes('Add task') && !btn.innerText.includes('Cancel')) {
                                    btn.click();
                                }
                            });
                        }, 150); 
                    }
                }
            }
        });
    }
    
    setTimeout(setupMagic, 500);
    </script>
    """,
    height=0,
    width=0,
)
