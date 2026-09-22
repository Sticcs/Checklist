from sqlalchemy import text

from app import crud, db


def test_utc_now_iso_carries_a_real_timezone_offset():
    # Not just "has a Z or +" - a full round-trip through datetime.fromisoformat
    # confirms it's genuinely a valid, timezone-aware ISO 8601 string, which is
    # what makes the frontend's `new Date(...)` interpret it correctly instead
    # of silently treating it as the viewer's own local time.
    from datetime import datetime

    stamp = crud.utc_now_iso()
    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_startup_backfills_naive_legacy_timestamps(client):
    # Simulates a row written before utc_now_iso() existed - a bare
    # datetime.now().isoformat() string with no timezone marker at all.
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username, position) "
                "VALUES ('legacy task', 0, 'Medium', 'General', NULL, '2026-01-01T12:00:00.000000', 'nobody', 0)"
            )
        )

    db.init_db()  # simulates a server restart with the fix now deployed

    with engine.connect() as conn:
        row = conn.execute(text("SELECT created_at FROM tasks WHERE text = 'legacy task'")).mappings().fetchone()
    assert row["created_at"] == "2026-01-01T12:00:00.000000+00:00"


def test_backfill_is_idempotent_and_leaves_already_fixed_rows_alone(client):
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tasks (text, done, priority, category, due_date, created_at, username, position) "
                "VALUES ('legacy task', 0, 'Medium', 'General', NULL, '2026-01-01T12:00:00', 'nobody', 0)"
            )
        )

    db.init_db()
    db.init_db()
    db.init_db()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT created_at FROM tasks WHERE text = 'legacy task'")).mappings().fetchone()
    # Not double (or triple) suffixed - "+00:00" appears exactly once.
    assert row["created_at"] == "2026-01-01T12:00:00+00:00"


def test_backfill_skips_null_read_at(client):
    # notifications.read_at is nullable (unread) - the migration must not
    # choke on or corrupt a NULL value.
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO notifications (username, kind, message, created_at, read_at) "
                "VALUES ('nobody', 'item_checked', 'test', '2026-01-01T12:00:00', NULL)"
            )
        )

    db.init_db()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT read_at FROM notifications WHERE message = 'test'")).mappings().fetchone()
    assert row["read_at"] is None
