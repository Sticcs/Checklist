from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, create_engine, event, inspect, text

from app.config import settings

# Schema is defined via SQLAlchemy's Table/Column (not raw DDL strings) so
# auto-increment primary keys translate correctly to whichever dialect is in
# use (SQLite's AUTOINCREMENT vs Postgres's SERIAL/IDENTITY) without needing
# dialect-conditional CREATE TABLE statements. The actual queries in crud.py
# still use raw SQL via text() - only the schema needs this abstraction.
metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("username", String, primary_key=True),
    Column("password", String, nullable=False),
    # Set only for accounts created via "Sign in with Google" (see
    # get_or_create_google_user) - such accounts still get a normal (random,
    # unusable) password hash rather than a nullable password column, so
    # this is the only schema change needed to support them. NULL for every
    # username/password/guest account, which is the vast majority.
    Column("google_sub", String, nullable=True, unique=True),
)

tasks_table = Table(
    "tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("text", Text, nullable=False),
    Column("done", Integer, nullable=False, server_default=text("0")),
    Column("priority", String, nullable=False, server_default="Medium"),
    Column("category", String, nullable=False, server_default="General"),
    Column("due_date", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("username", String, nullable=True),
    Column("pinned", Integer, nullable=False, server_default=text("0")),
    Column("position", Float, nullable=False, server_default=text("0")),
    Column("notes", Text, nullable=True),
    Column("urgent", Integer, nullable=False, server_default=text("0")),
)

subtasks_table = Table(
    "subtasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("done", Integer, nullable=False, server_default=text("0")),
    Column("created_at", String, nullable=False),
    Column("urgent", Integer, nullable=False, server_default=text("0")),
    Column("due_date", String, nullable=True),
    Column("notes", Text, nullable=True),
)

activity_log_table = Table(
    "activity_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, nullable=False),
    Column("action", String, nullable=False),
    Column("detail", Text, nullable=False),
    Column("created_at", String, nullable=False),
    Column("task_id", Integer, nullable=True),
)

_engine = None


def _build_engine():
    if settings.database_url:
        # Neon/Supabase hand out plain postgres:// or postgresql:// URLs.
        # SQLAlchemy's default driver for that scheme is psycopg2, which
        # isn't installed (requirements.txt only has psycopg v3) - force the
        # +psycopg suffix so it actually uses the driver we ship.
        url = settings.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        # pool_pre_ping guards against Neon/Supabase closing idle connections
        # while the free-tier database is paused/asleep - a dead connection
        # gets discarded and replaced instead of raising on first use.
        return create_engine(url, pool_pre_ping=True)

    engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        # Concurrent writes are possible under FastAPI's threadpool (routes
        # run as plain `def`, dispatched to worker threads) in a way they
        # weren't under Streamlit's single-threaded rerun model. busy_timeout
        # makes a second writer wait and retry instead of raising immediately.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    return engine


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def reset_engine() -> None:
    """Test-only: drop the cached engine so the next get_engine() call rebuilds
    one from whatever settings.db_path/database_url currently are. Needed
    because (unlike the old per-call sqlite3.connect()) the engine is now
    built once and reused for connection pooling."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        # WAL lets readers and a writer proceed concurrently instead of
        # blocking each other; it's a persistent, database-level setting so
        # it only needs to be set once (here, at startup).
        with engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode = WAL"))
    metadata.create_all(engine)

    # create_all() only creates *missing* tables - it never alters an
    # existing one, so a `tasks` table created before the "position" column
    # existed (e.g. the real checklist.db) needs an explicit migration here,
    # same defensive pattern the original main.py used for schema changes.
    inspector = inspect(engine)
    existing_task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "position" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN position FLOAT NOT NULL DEFAULT 0"))
            # Backfill so the initial "Manual" order matches what users
            # already see today (newest first, i.e. highest id first).
            conn.execute(text("UPDATE tasks SET position = -id"))

    if "notes" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN notes TEXT"))

    if "urgent" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN urgent INTEGER NOT NULL DEFAULT 0"))

    existing_subtask_columns = {c["name"] for c in inspector.get_columns("subtasks")}
    if "urgent" not in existing_subtask_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN urgent INTEGER NOT NULL DEFAULT 0"))

    if "due_date" not in existing_subtask_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN due_date TEXT"))

    if "notes" not in existing_subtask_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN notes TEXT"))

    existing_activity_columns = {c["name"] for c in inspector.get_columns("activity_log")}
    if "task_id" not in existing_activity_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE activity_log ADD COLUMN task_id INTEGER"))

    existing_user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "google_sub" not in existing_user_columns:
        with engine.begin() as conn:
            # No UNIQUE constraint here (unlike the Table def above, which
            # only applies to fresh installs) - adding one via ALTER TABLE
            # isn't portable across SQLite/Postgres without dialect-specific
            # DDL, and get_or_create_google_user already looks up by
            # google_sub before ever inserting, so the practical uniqueness
            # holds without the database enforcing it too.
            conn.execute(text("ALTER TABLE users ADD COLUMN google_sub TEXT"))
