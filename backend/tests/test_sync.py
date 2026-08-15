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
    holding one task."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None):
        assert url.endswith("/api/auth/login")
        if json.get("username") == "alice" and json.get("password") == "correct-password":
            return _FakeResponse(200, cookies={settings.cookie_name: "fake-session-token"})
        return _FakeResponse(401)

    def get(self, url, cookies=None):
        assert url.endswith("/api/export")
        if cookies.get(settings.cookie_name) == "fake-session-token":
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
