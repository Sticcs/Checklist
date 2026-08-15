import pytest

from app import paths
from app.config import settings


class _FakeResponse:
    def __init__(self, status_code, json_data=None, cookies=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.cookies = cookies or {}

    def json(self):
        return self._json


class _FakeWebsiteClient:
    """Stands in for httpx.Client so tests never make a real network call -
    simulates a website with exactly one account, alice/correct-password,
    holding one task. Also records every /api/import payload it receives
    (class-level, since a fresh instance is constructed per `with` block),
    so push tests can assert what was actually sent - see the autouse
    fixture below that resets it between tests."""

    imported_payloads: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, cookies=None):
        if url.endswith("/api/auth/login"):
            if json.get("username") == "alice" and json.get("password") == "correct-password":
                return _FakeResponse(200, cookies={settings.cookie_name: "fake-session-token"})
            return _FakeResponse(401)
        if url.endswith("/api/import"):
            if (cookies or {}).get(settings.cookie_name) != "fake-session-token":
                return _FakeResponse(401)
            _FakeWebsiteClient.imported_payloads.append(json)
            tasks = (json or {}).get("tasks", [])
            subtask_count = sum(len(t.get("subtasks", [])) for t in tasks)
            return _FakeResponse(200, {"imported_tasks": len(tasks), "imported_subtasks": subtask_count})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, cookies=None):
        assert url.endswith("/api/export")
        if (cookies or {}).get(settings.cookie_name) == "fake-session-token":
            return _FakeResponse(
                200,
                {
                    "version": 1,
                    "exported_at": "2026-01-01T00:00:00",
                    "tasks": [
                        {
                            "text": "Task from the website",
                            "priority": "Medium",
                            "category": "General",
                            "subtasks": [],
                        }
                    ],
                },
            )
        return _FakeResponse(401)


@pytest.fixture(autouse=True)
def _reset_fake_website_imports():
    _FakeWebsiteClient.imported_payloads = []


def test_login_with_website_credentials_bootstraps_local_account_and_data(client, monkeypatch):
    monkeypatch.setattr(paths, "is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    # No local "alice" account exists yet - this is the first time.
    r = client.post("/api/auth/login", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 200
    assert r.json() == {"username": "alice", "is_guest": False}

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["text"] == "Task from the website"


def test_login_bootstrap_does_not_apply_outside_desktop_build(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: False)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    r = client.post("/api/auth/login", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 401


def test_login_bootstrap_only_fires_once_per_username(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    client.post("/api/auth/login", json={"username": "alice", "password": "correct-password"})
    client.post("/api/auth/logout")

    # Second login: local "alice" now exists with a locally-set password, so
    # this checks *that* - the website is never consulted again, and the
    # task shouldn't be re-imported as a duplicate.
    r = client.post("/api/auth/login", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 200
    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1


def test_sync_now_requires_desktop_build(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: False)
    client.post("/api/auth/guest")
    r = client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 503


def test_sync_now_requires_local_login(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    r = client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 401


def test_sync_now_rejects_bad_website_credentials(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    r = client.post("/api/auth/sync", json={"username": "alice", "password": "wrong-password"})
    assert r.status_code == 401


def test_sync_now_imports_into_currently_logged_in_local_account(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    # Local account is a guest, unrelated username to the website's "alice".
    guest_resp = client.post("/api/auth/guest")
    guest_username = guest_resp.json()["username"]
    client.post("/api/tasks", json={"text": "Already local", "priority": "Medium", "category": "General"})

    r = client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 0}

    tasks = client.get("/api/tasks").json()["tasks"]
    texts = sorted(t["text"] for t in tasks)
    assert texts == ["Already local", "Task from the website"]

    # Sanity: nothing landed in some other/new account - it's specifically
    # the currently-authenticated local guest that got the imported task.
    assert client.get("/api/auth/me").json()["username"] == guest_username


def test_sync_now_is_additive_across_repeated_calls(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 2  # deliberately duplicates, like Import already does - not a bug


def test_push_requires_desktop_build(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: False)
    client.post("/api/auth/guest")
    r = client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 503


def test_push_requires_local_login(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    r = client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 401


def test_push_rejects_bad_website_credentials(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    r = client.post("/api/auth/push", json={"username": "alice", "password": "wrong-password"})
    assert r.status_code == 401
    assert _FakeWebsiteClient.imported_payloads == []


def test_push_sends_local_tasks_to_the_website(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    client.post("/api/auth/guest")
    client.post("/api/tasks", json={"text": "Local task to push", "priority": "High", "category": "Work"})
    task_id = client.get("/api/tasks").json()["tasks"][0]["id"]
    client.post(f"/api/tasks/{task_id}/subtasks", json={"text": "Local subtask"})

    r = client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 1}

    # The website's /api/import actually received this local task - not just
    # a locally-fabricated success response.
    assert len(_FakeWebsiteClient.imported_payloads) == 1
    sent_tasks = _FakeWebsiteClient.imported_payloads[0]["tasks"]
    assert len(sent_tasks) == 1
    assert sent_tasks[0]["text"] == "Local task to push"
    assert sent_tasks[0]["subtasks"][0]["text"] == "Local subtask"
    # Portable fields only, matching /api/export's own shape - no id/
    # username/created_at/position leaking into the pushed payload.
    assert set(sent_tasks[0].keys()) == {
        "text", "priority", "category", "due_date", "done", "pinned", "urgent", "notes", "subtasks",
    }


def test_push_does_not_touch_local_data(client, monkeypatch):
    """Push is one-directional - the local account's own tasks are read-only
    from push's perspective, never modified by the response it gets back."""
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    client.post("/api/auth/guest")
    client.post("/api/tasks", json={"text": "Stays local", "priority": "Medium", "category": "General"})

    client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})

    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t["text"] for t in tasks] == ["Stays local"]
