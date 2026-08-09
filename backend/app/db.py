from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, event, text

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
)

subtasks_table = Table(
    "subtasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("done", Integer, nullable=False, server_default=text("0")),
    Column("created_at", String, nullable=False),
)

activity_log_table = Table(
    "activity_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, nullable=False),
    Column("action", String, nullable=False),
    Column("detail", Text, nullable=False),
    Column("created_at", String, nullable=False),
)

_engine = None


def _build_engine():
    if settings.database_url:
        # pool_pre_ping guards against Neon/Supabase closing idle connections
        # while the free-tier database is paused/asleep - a dead connection
        # gets discarded and replaced instead of raising on first use.
        return create_engine(settings.database_url, pool_pre_ping=True)

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
