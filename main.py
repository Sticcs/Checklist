import streamlit as st
import streamlit.components.v1 as components
import sqlite3
from datetime import date, timedelta, datetime
from contextlib import closing

DB_PATH = "checklist.db"

# ----------------------------- UI Config & State -----------------------------

st.set_page_config(page_title="Checklist", layout="wide")

if "undo_stack" not in st.session_state:
    st.session_state.undo_stack = []
if "redo_stack" not in st.session_state:
    st.session_state.redo_stack = []

# ----------------------------- Database layer -----------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'Medium',
                category TEXT NOT NULL DEFAULT 'General',
                due_date TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

def get_tasks():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def _restore_state(state_tasks):
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks")
        for t in state_tasks:
            conn.execute(
                "INSERT INTO tasks (id, text, done, priority, category, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (t['id'], t['text'], t['done'], t['priority'], t['category'], t['due_date'], t['created_at'])
            )
        conn.commit()

def save_state_for_undo():
    st.session_state.undo_stack.append(get_tasks())
    st.session_state.redo_stack.clear() 
    if len(st.session_state.undo_stack) > 20: 
        st.session_state.undo_stack.pop(0)

def perform_undo():
    if st.session_state.undo_stack:
        st.session_state.redo_stack.append(get_tasks())
        last_state = st.session_state.undo_stack.pop()
        _restore_state(last_state)
        st.toast("↩️ Undid last action")

def perform_redo():
    if st.session_state.redo_stack:
        st.session_state.undo_stack.append(get_tasks())
        next_state = st.session_state.redo_stack.pop()
        _restore_state(next_state)
        st.toast("↪️ Redid last action")

def add_task(text, priority, category, due_date):
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute(
            "INSERT INTO tasks (text, done, priority, category, due_date, created_at) "
            "VALUES (?, 0, ?, ?, ?, ?)",
            (text, priority, category or "General", due_date, datetime.now().isoformat()),
        )
        conn.commit()
    st.toast("✅ Task added")

def set_done(task_id, done):
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (int(done), task_id))
        conn.commit()
    status = "completed" if done else "unmarked"
    st.toast(f"✅ Task {status}")

def delete_task(task_id):
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    st.toast("🗑️ Task deleted")

def clear_completed():
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks WHERE done = 1")
        conn.commit()
    st.toast("🧹 Cleared completed tasks")

def clear_all():
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM tasks")
        conn.commit()
    st.toast("🗑️ Cleared all tasks")

def mark_all_completed():
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute("UPDATE tasks SET done = 1")
        conn.commit()
    st.toast("✅ Marked all as completed")

def update_task(task_id, text, priority, category, due_date):
    save_state_for_undo()
    with closing(get_conn()) as conn:
        conn.execute(
            "UPDATE tasks SET text = ?, priority = ?, category = ?, due_date = ? WHERE id = ?",
            (text, priority, category, due_date, task_id),
        )
        conn.commit()
    st.toast("💾 Task updated")

# ----------------------------- Styles & Theming -----------------------------

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORIES = ["House", "Work", "Study"]
PRIORITIES = ["High", "Medium", "Low"]

st.markdown(
    """
    <style>
    /* Global App Backgrounds & Sidebar Shadow */
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

    /* Dark Mode specific (Driven by JS Class) */
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

    /* Light Mode specific (Driven by JS Class) */
    body.custom-light .stApp {
        background-image: url("https://img.magnific.com/free-photo/faux-watermelon-peperomia-plant-light-gray-background_53876-142828.jpg?semt=ais_test_b&w=740&q=80") !important;
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

    /* Minimalist Typography */
    h1, h2, h3, h4 {
        font-weight: 500 !important;
        letter-spacing: -0.5px;
    }
    
    /* Clean Task List Design */
    .task-row {
        padding: 0.8rem 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.25);
        display: flex;
        flex-direction: column;
        justify-content: center;
        transition: opacity 0.2s ease;
    }
    .task-row.is-done {
        opacity: 0.4;
    }
    .task-title {
        font-size: 1.05rem;
        font-weight: 400;
        margin-bottom: 4px;
    }
    .task-title.is-done {
        text-decoration: line-through;
    }
    
    /* Priority Accent Lines */
    .border-High { border-left: 2px solid #e74c3c; padding-left: 12px; }
    .border-Medium { border-left: 2px solid #f39c12; padding-left: 12px; }
    .border-Low { border-left: 2px solid #3498db; padding-left: 12px; }
    
    /* Subtle Badges */
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

    /* Refine Buttons */
    div[data-testid="column"] button { width: 100%; }
    div[data-testid="stHorizontalBlock"] { gap: 0.5rem; }
    section[data-testid="stSidebar"] button {
        border-radius: 6px;
        font-weight: 400;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()

# ----------------------------- Quick-add state defaults -----------------------------

st.session_state.setdefault("task_input", "")
st.session_state.setdefault("new_category", "House")
st.session_state.setdefault("new_priority", "Medium")
st.session_state.setdefault("new_due_preset", "No date")
st.session_state.setdefault("new_due_custom", None)

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

def set_category(cat): st.session_state.new_category = cat
def set_priority(pri): st.session_state.new_priority = pri
def set_due_preset(preset): st.session_state.new_due_preset = preset

def submit_new_task():
    text = st.session_state.task_input.strip()
    if text:
        due_date = DUE_PRESETS[st.session_state.new_due_preset]()
        add_task(text, st.session_state.new_priority, st.session_state.new_category, due_date)
        st.session_state.task_input = "" 

tasks = get_tasks()
categories = sorted({t["category"] for t in tasks}) if tasks else []

# ----------------------------- Sidebar -----------------------------

with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search", label_visibility="collapsed", placeholder="Search tasks...")
    status_filter = st.radio("Status", ["All", "Active", "Completed"], horizontal=True, label_visibility="collapsed")
    category_filter = st.multiselect("Category", categories, default=categories)
    sort_by = st.selectbox("Sort by", ["Priority", "Due date", "Newest first"])
    
    st.write("---")
    
    col_u, col_r = st.columns(2)
    with col_u:
        if st.button("↩️ Undo", disabled=len(st.session_state.undo_stack) == 0):
            perform_undo()
            st.rerun()
    with col_r:
        if st.button("↪️ Redo", disabled=len(st.session_state.redo_stack) == 0):
            perform_redo()
            st.rerun()
        
    st.write("")
    if st.button("Mark all completed"):
        mark_all_completed()
        st.rerun()
    if st.button("Clear completed"):
        clear_completed()
        st.rerun()
    if st.button("Clear all"):
        clear_all()
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
    st.title("Checklist")
    st.write("")
    st.write("")

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
                cat,
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
                pri,
                key=f"pri_btn_{pri}",
                on_click=set_priority,
                args=(pri,),
                type="primary" if st.session_state.new_priority == pri else "secondary",
            )

    st.caption("Due")
    due_cols = st.columns(len(DUE_PRESETS), gap="small")
    for col, preset in zip(due_cols, DUE_PRESETS.keys()):
        with col:
            st.button(
                preset,
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
    # ----------------------------- Apply filters -----------------------------
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

    # ----------------------------- Task list -----------------------------
    if not filtered:
        st.caption("No tasks match your filters yet.")
    else:
        today = date.today().isoformat()
        for t in filtered:
            with st.container():
                col1, col2, col3 = st.columns([0.4, 7.5, 1.5], vertical_alignment="center")
                
                with col1:
                    new_done = st.checkbox("", value=bool(t["done"]), key=f"chk_{t['id']}")
                    if new_done != bool(t["done"]):
                        set_done(t["id"], new_done)
                        st.rerun()
                        
                with col2:
                    done_class = "is-done" if t["done"] else ""
                    
                    tags_html = f'<span class="badge">{t["category"]}</span>'
                    if t["due_date"]:
                        overdue = (not t["done"]) and t["due_date"] < today
                        due_class = "badge overdue" if overdue else "badge"
                        tags_html += f'<span class="{due_class}">{t["due_date"]}</span>'
                        
                    st.markdown(
                        f"""
                        <div class="task-row border-{t['priority']} {done_class}">
                            <div class="task-title {done_class}">{t['text']}</div>
                            <div class="meta-tags">{tags_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    
                with col3:
                    d1, d2 = st.columns(2)
                    with d1:
                        if st.button("Edit", key=f"edit_{t['id']}", help="Edit task"):
                            st.session_state[f"editing_{t['id']}"] = True
                    with d2:
                        if st.button("Del", key=f"del_{t['id']}", help="Delete task"):
                            delete_task(t["id"])
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
                                    e_due.isoformat() if e_due else None,
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
    
    // 1. DYNAMIC THEME TRACKER
    // Streamlit toggles themes by changing the background color in its root CSS.
    // This constantly checks that color and assigns a class to the body so our custom CSS updates properly.
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


    // 2. ENTER INDICATOR & KEYBOARD SHORTCUTS
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
                border-radius: 4px;
                font-size: 0.85rem;
                font-weight: 500;
                opacity: 0;
                transform: translateY(10px);
                transition: all 0.2s ease;
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
        indicator.innerText = 'Press Enter to add';
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

            if (taskInput && taskInput.value.trim().length > 0) {
                indicator.classList.add('visible');
            } else {
                indicator.classList.remove('visible');
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

            if ((e.ctrlKey || e.metaKey) && !isTyping) {
                if (e.key.toLowerCase() === 'z') {
                    e.preventDefault();
                    const buttons = Array.from(doc.querySelectorAll('button'));
                    const undoBtn = buttons.find(b => b.innerText.includes('Undo'));
                    if (undoBtn && !undoBtn.disabled) undoBtn.click();
                } else if (e.key.toLowerCase() === 'y') {
                    e.preventDefault();
                    const buttons = Array.from(doc.querySelectorAll('button'));
                    const redoBtn = buttons.find(b => b.innerText.includes('Redo'));
                    if (redoBtn && !redoBtn.disabled) redoBtn.click();
                }
            }

            if (!taskInput) return;

            if (activeTag !== 'input' && activeTag !== 'textarea') {
                if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                    taskInput.focus();
                }
            }

            if (e.key === 'Enter') {
                if (activeTag === 'input' && doc.activeElement !== taskInput) return; 
                
                if (taskInput.value.trim().length > 0) {
                    e.preventDefault(); 
                    taskInput.blur(); 
                    
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
        });
    }
    
    setTimeout(setupMagic, 500);
    </script>
    """,
    height=0,
    width=0,
)