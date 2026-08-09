import pytest
from fastapi.testclient import TestClient

from app import undo
from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Never touch the real checklist.db - point settings.db_path at a fresh
    # file per test. db.get_conn() reads settings.db_path on every call (not
    # cached at import time), so this takes effect for every request the
    # TestClient makes below.
    db_file = tmp_path / "test_checklist.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))

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
