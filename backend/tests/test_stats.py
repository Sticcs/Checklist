from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from app import db


def _utc_today() -> date:
    # get_stats judges "today" in UTC (see crud.get_stats's own comment on
    # why - created_at is always a UTC timestamp now), so test setup needs
    # to seed activity against that same UTC "today", not this machine's
    # own local date.today() - the two only actually differ near a day
    # boundary, but a flaky test that only fails once a day is worse than
    # one that's always right.
    return datetime.now(timezone.utc).date()


def _add_task(client, text="Buy milk"):
    r = client.post("/api/tasks", json={"text": text, "priority": "Medium", "category": "General"})
    assert r.status_code == 201
    return r.json()


def _insert_completed_activity(username: str, day: date) -> None:
    """Directly craft an activity_log row for a past day - the streak/heatmap
    logic keys off created_at's date, and there's no way to backdate a real
    completion through the API, so tests that need multi-day history write
    straight to the table."""
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO activity_log (username, action, detail, created_at) "
                "VALUES (:username, 'completed', 'Backfilled', :created_at)"
            ),
            {"username": username, "created_at": day.isoformat() + "T12:00:00"},
        )


def test_stats_all_zero_with_no_activity(guest_client):
    client, _ = guest_client
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["current_streak"] == 0
    assert body["longest_streak"] == 0
    assert body["completed_today"] == 0
    assert body["completed_this_week"] == 0
    assert body["total_completed"] == 0
    assert len(body["daily_counts"]) == 30


def test_stats_reflects_a_real_completion_today(guest_client):
    client, username = guest_client
    task = _add_task(client)
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    r = client.get("/api/stats")
    body = r.json()
    assert body["completed_today"] == 1
    assert body["completed_this_week"] == 1
    assert body["total_completed"] == 1
    assert body["current_streak"] == 1
    assert body["longest_streak"] == 1
    assert body["daily_counts"][-1] == {"date": _utc_today().isoformat(), "count": 1}


def test_current_streak_counts_consecutive_days_including_today(guest_client):
    client, username = guest_client
    today = _utc_today()
    for offset in range(4):  # today, yesterday, 2 and 3 days ago
        _insert_completed_activity(username, today - timedelta(days=offset))

    body = client.get("/api/stats").json()
    assert body["current_streak"] == 4
    assert body["longest_streak"] == 4
    assert body["total_completed"] == 4


def test_streak_not_broken_by_empty_today(guest_client):
    client, username = guest_client
    today = _utc_today()
    # Yesterday and the day before have activity; today doesn't yet.
    _insert_completed_activity(username, today - timedelta(days=1))
    _insert_completed_activity(username, today - timedelta(days=2))

    body = client.get("/api/stats").json()
    assert body["current_streak"] == 2
    assert body["completed_today"] == 0


def test_streak_broken_by_gap(guest_client):
    client, username = guest_client
    today = _utc_today()
    _insert_completed_activity(username, today)
    _insert_completed_activity(username, today - timedelta(days=1))
    # Gap at 2 days ago
    _insert_completed_activity(username, today - timedelta(days=3))
    _insert_completed_activity(username, today - timedelta(days=4))

    body = client.get("/api/stats").json()
    assert body["current_streak"] == 2  # today + yesterday only
    assert body["longest_streak"] == 2  # both runs are length 2


def test_completed_this_week_excludes_older_activity(guest_client):
    client, username = guest_client
    today = _utc_today()
    _insert_completed_activity(username, today)
    _insert_completed_activity(username, today - timedelta(days=10))  # outside the 7-day window

    body = client.get("/api/stats").json()
    assert body["completed_this_week"] == 1
    assert body["total_completed"] == 2


def test_stats_isolated_per_user(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    from fastapi.testclient import TestClient

    from app.main import app

    other = TestClient(app)
    other.post("/api/auth/guest")
    body = other.get("/api/stats").json()
    assert body["total_completed"] == 0
    assert body["current_streak"] == 0
