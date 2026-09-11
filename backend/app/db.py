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
    # Alt+click-to-assign (see routers/tasks.py's /assign): set on an
    # assessment task, pointing at the plain task it's filed under - never
    # the other way around, and never chained (an assessment can't be
    # assigned to another assessment). Self-referencing, so no ForeignKey
    # object here, matching this file's existing no-FK-constraints
    # convention (see google_sub's migration comment below).
    Column("assigned_task_id", Integer, nullable=True),
    # Set when the user clicks "Start" on an assessment (see the frontend's
    # AssignmentWorkspace) - cleared again once the task is marked done (see
    # set_done). Purely a "have I opened this and begun working on it" flag,
    # not a workflow state machine - there's no in-progress -> not-started
    # transition other than completing or un-completing the task itself.
    Column("in_progress", Integer, nullable=False, server_default=text("0")),
    # JSON-encoded list of {"name", "url"} objects (see the frontend's
    # AssignmentWorkspace "Add link" panel) - stored as a single TEXT blob
    # rather than a separate table since links are always read/written as
    # one whole list for a task, never queried or joined on individually.
    Column("links", Text, nullable=True),
    # JSON-encoded list of {"id", "title", "content"} objects - the
    # AssignmentWorkspace's multi-page tabs (each page is its own rich-text
    # doc, same html shape as `notes`). Same "whole list, one blob" reasoning
    # as `links` above. `notes` itself remains page 1's content for anything
    # written before this existed - see crud.get_task_pages.
    Column("pages", Text, nullable=True),
    # Set when the owner generates a share link for an Assignment (see
    # routers/collaboration.py). NULL = no active link. Regenerating
    # overwrites it (silently invalidating the old link); revoking sets it
    # back to NULL. Never exposed on the Task response model (see models.py)
    # so other users can't see or reuse the owner's live token via a normal
    # task fetch - only routers/collaboration.py's owner-gated endpoints read it.
    Column("share_token", String, nullable=True),
    # Set only for a task that's an item in a custom list (see lists_table
    # below) - null for every ordinary task, including Assessment/Shopping-
    # category ones, which are still routed by `category` alone. No FK (see
    # google_sub's comment above). A custom list's items are found by this
    # column; Shopping's items are still found by category, never list_id -
    # see crud.get_or_create_shopping_list's docstring for why the two
    # built-in tabs (Shopping) and user-created ones (custom) use different
    # membership rules despite sharing the same lists_table/UI.
    Column("list_id", Integer, nullable=True),
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
    # Who this mini task (in an Assignment workspace's own bare-bones task
    # panel) is assigned to - the owner's own username, one of the
    # assignment's collaborators (see assignment_collaborators_table), or
    # null for unassigned. No FK (see google_sub's comment above); validated
    # against the current collaborator list at write time by
    # routers/subtasks.py, not enforced by the schema.
    Column("assigned_username", String, nullable=True),
)

website_links_table = Table(
    "website_links",
    metadata,
    # One link per local account (desktop app only - see routers/auth.py's
    # /sync and /push) - re-linking the same local account to a website
    # account just overwrites its row rather than growing a history.
    # Password is stored in plain text: this is the same local SQLite file
    # already holding every task, note, and the activity log unencrypted -
    # anyone with filesystem access to this machine already has all of that,
    # so encrypting only this one column wouldn't raise the actual trust
    # boundary any further.
    Column("username", String, primary_key=True),
    Column("website_username", String, nullable=False),
    Column("website_password", String, nullable=False),
    Column("linked_at", String, nullable=False),
)

assignment_collaborators_table = Table(
    "assignment_collaborators",
    metadata,
    # No FK to tasks/users (see google_sub's comment above for why - ALTER
    # TABLE-added constraints aren't portable across SQLite/Postgres). No DB
    # uniqueness on (task_id, username) either - crud.add_collaborator
    # dedupes before inserting, same convention as google_sub's uniqueness
    # being enforced in application code rather than the schema.
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", Integer, nullable=False),
    Column("username", String, nullable=False),
    Column("added_at", String, nullable=False),
)

lists_table = Table(
    "lists",
    metadata,
    # No FK (see google_sub's comment above). No DB uniqueness on
    # (username, kind='shopping') - crud.get_or_create_shopping_list checks
    # before inserting, same convention as everywhere else in this file.
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, nullable=False),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("position", Float, nullable=False, server_default=text("0")),
    # Mirrors tasks.share_token exactly (see its comment) - never exposed on
    # a response model a non-owner could reach.
    Column("share_token", String, nullable=True),
    # 'custom' (a user-created list via the "+" tab - its items are tasks
    # with list_id pointing at this row) or 'shopping' (the one, permanent,
    # lazily-created-per-account row backing the built-in Shopping tab -
    # its items are tasks with category='Shopping', never list_id; see
    # crud.get_or_create_shopping_list). This lets Shopping and custom lists
    # share one rename/delete/share code path, branching on `kind` only
    # where their membership rule or delete semantics genuinely differ.
    Column("kind", String, nullable=False, server_default="custom"),
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

# username is the recipient, not the actor - actor_username is who actually
# did it (null for an anonymous public-link visitor). Unlike activity_log
# (always logged under the task owner's username), notifications need to be
# addressable to whoever should see them, which for "your access was
# revoked" or "you were assigned this" is someone other than the task owner.
notifications_table = Table(
    "notifications",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("message", Text, nullable=False),
    Column("actor_username", String, nullable=True),
    Column("task_id", Integer, nullable=True),
    Column("created_at", String, nullable=False),
    Column("read_at", String, nullable=True),
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

    if "assigned_task_id" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN assigned_task_id INTEGER"))

    if "in_progress" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN in_progress INTEGER NOT NULL DEFAULT 0"))

    if "links" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN links TEXT"))

    if "pages" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN pages TEXT"))

    if "share_token" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN share_token TEXT"))

    if "list_id" not in existing_task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN list_id INTEGER"))

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

    if "assigned_username" not in existing_subtask_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE subtasks ADD COLUMN assigned_username TEXT"))

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
