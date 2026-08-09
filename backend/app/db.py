import sqlite3
from contextlib import closing

from app.config import settings


def get_conn() -> sqlite3.Connection:
    # Reads settings.db_path on every call (not cached at import time) so tests
    # can point this at a tmp_path file by monkeypatching settings.db_path.
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Concurrent writes are newly possible under FastAPI's threadpool (routes
    # run as plain `def`, so Starlette dispatches them to worker threads) in a
    # way they weren't under Streamlit's single-threaded rerun model.
    # busy_timeout makes a second writer wait and retry instead of raising
    # "database is locked" immediately.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    with closing(get_conn()) as conn:
        # WAL lets readers and a writer proceed concurrently instead of
        # blocking each other; it's a persistent, database-level setting so it
        # only needs to be set once (here, at startup) rather than per connection.
        conn.execute("PRAGMA journal_mode = WAL")
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
                username TEXT,
                pinned INTEGER NOT NULL DEFAULT 0
            )
        """)
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
