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
        conn.commit()

def get_tasks(username):
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE username = ? ORDER BY created_at DESC", (username,)).fetchall()
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

def save_state_for_undo(username):
    st.session_state.undo_stack.append(get_tasks(username))
    st.session_state.redo_stack.clear() 
    if len(st.session_state.undo_stack) > 20: 
        st.session_state.undo_stack.pop(0)

def perform_undo(username):
    if st.session_state.undo_stack:
        st.session_state.redo_stack.append(get_tasks(username))
        last_state = st.session_state.undo_stack.pop()
        _restore_state(last_state, username)
        st.session_state.pending_toast = "↩️ Undid last action"

def perform_redo(username):
    if st.session_state.redo_stack:
        st.session_state.undo_stack.append(get_tasks(username))
        next_state = st.session_state.redo_stack.pop()
        _restore_state(next_state, username)
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
        conn.execute("DELETE FROM tasks WHERE id = ? AND username = ?", (task_id, username))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Task deleted"

def clear_completed(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE done = 1 AND username = ?", (username,))
        conn.commit()
    st.session_state.pending_toast = "🧹 Cleared completed tasks"

def clear_all(username):
    save_state_for_undo(username)
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE username = ?", (username,))
        conn.commit()
    st.session_state.pending_toast = "🗑️ Cleared all tasks"

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

# ----------------------------- Styles & Theming -----------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORIES = ["House", "Work", "Study", "Personal"]
PRIORITIES = ["High", "Medium", "Low"]

CAT_KEYS = {"House": "H", "Work": "W", "Study": "S", "Personal": "P"}
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
    
    /* Dynamic Header Styles */
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
        transition: opacity 0.2s ease;
    }
    .task-row.is-done { opacity: 0.4; }
    .task-title {
        font-size: 1.05rem;
        font-weight: 400;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
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
    
    /* Smooth Transitions for ALL Streamlit Buttons */
    div[data-testid="stButton"] button { 
        width: 100%;
        height: auto !important;
        padding: 0.4rem 0.2rem !important;
        transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease, transform 0.1s ease !important;
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

    def _end_of_week(base):
        return base + timedelta(days=(4 - base.weekday()) % 7)

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
            add_task(text, st.session_state.new_priority, st.session_state.new_category, due_date, st.session_state.username)
            st.session_state.task_input = "" 
            st.session_state.options_modified = False

    tasks = get_tasks(st.session_state.username)
    categories = sorted({t["category"] for t in tasks}) if tasks else []

    # ----------------------------- Sidebar -----------------------------

    with st.sidebar:
        st.markdown(f"<div class='profile-indicator'><span>👤</span> {st.session_state.username}</div>", unsafe_allow_html=True)
        if st.button("Sign out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.undo_stack.clear()
            st.session_state.redo_stack.clear()
            st.rerun()
            
        st.write("---")
        
        st.header("Filters")
        search = st.text_input("Search", label_visibility="collapsed", placeholder="Search tasks...")
        status_filter = st.radio("Status", ["All", "Active", "Completed"], horizontal=True, label_visibility="collapsed")
        category_filter = st.multiselect("Category", categories, default=categories)
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
        filtered = tasks
        if search:
            filtered = [t for t in filtered if search.lower() in t["text"].lower()]
        if status_filter == "Active":
            filtered = [t for t in filtered if not t["done"]]
        elif status_filter == "Completed":
            filtered = [t for t in filtered if t["done"]]
        if categories:
            filtered = [t for t in filtered if t["category"] in category_filter]

        if sort_by == "Priority":
            filtered.sort(key=lambda t: PRIORITY_ORDER.get(t["priority"], 1))
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
                with st.container():
                    col1, col2, col3 = st.columns([0.4, 7.5, 1.5], vertical_alignment="center")
                    
                    with col1:
                        new_done = st.checkbox("", value=bool(t["done"]), key=f"chk_{t['id']}")
                        if new_done != bool(t["done"]):
                            set_done(t["id"], new_done, st.session_state.username)
                            st.rerun()
                            
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
                            if st.button("Del", key=f"del_{t['id']}", help="Delete task"):
                                delete_task(t["id"], st.session_state.username)
                                st.rerun()

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
    
    // Dynamic Quotes logic
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
            inputs.forEach(inp => {
                if(inp.placeholder === "E.g., Review Big O time complexity") taskInput = inp;
            });
            
            const optState = doc.getElementById('options-state');
            const isModified = optState ? optState.getAttribute('data-modified') === 'true' : false;
            
            const buttons = Array.from(doc.querySelectorAll('button'));
            const addTaskBtn = buttons.find(b => b.innerText.includes('Add task') && !b.innerText.includes('Cancel'));
            
            if (addTaskBtn) {
                addTaskBtn.style.transition = 'background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease';
            }

            if (taskInput && taskInput.value.trim().length > 0) {
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
            inputs.forEach(inp => {
                if(inp.placeholder === "E.g., Review Big O time complexity") taskInput = inp;
            });
            
            const activeTag = doc.activeElement ? doc.activeElement.tagName.toLowerCase() : '';
            const isTyping = (activeTag === 'input' || activeTag === 'textarea');
            const hasText = taskInput ? taskInput.value.trim().length > 0 : false;
            const key = e.key.toLowerCase();
            
            const isHotkey = ['1','2','3','4','5','6','h','w','s','p','t','m','l'].includes(key);

            if (!isTyping) {
                if (hasText && isHotkey) {
                    e.preventDefault(); 
                    
                    const clickBtn = (textFragment) => {
                        const buttons = Array.from(doc.querySelectorAll('button'));
                        const btn = buttons.find(b => b.innerText.includes(textFragment));
                        if(btn) btn.click();
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

            if (e.key === 'Enter' && taskInput) {
                if (activeTag === 'input' && doc.activeElement !== taskInput) return; 
                
                if (hasText) {
                    e.preventDefault(); 
                    
                    if (isTyping && doc.activeElement === taskInput) {
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
