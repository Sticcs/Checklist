import pytest
from fastapi.testclient import TestClient

from app import db, undo
from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Never touch the real checklist.db - point settings.db_path at a fresh
    # file per test, and force db.py to rebuild its cached SQLAlchemy engine
    # against that path (the engine is now built once and pooled, unlike the
    # old per-call sqlite3.connect(), so it won't pick up a settings change on
    # its own).
    db_file = tmp_path / "test_checklist.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))
    monkeypatch.setattr(settings, "database_url", None)
    db.reset_engine()

    # The undo/redo stacks are process-global (keyed by username); clear them
    # so state can't leak between tests that happen to reuse a username.
    undo._stacks.clear()

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def guest_client(client):
    resp = client.post("/api/auth/guest")
    assert resp.status_code == 200
    return client, resp.json()["username"]
