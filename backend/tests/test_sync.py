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
    import_urls: list[str] = []

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
            if json.get("username") == "carol" and json.get("password") == "other-password":
                return _FakeResponse(200, cookies={settings.cookie_name: "fake-session-token-carol"})
            return _FakeResponse(401)
        if url.split("?")[0].endswith("/api/import"):
            if (cookies or {}).get(settings.cookie_name) not in ("fake-session-token", "fake-session-token-carol"):
                return _FakeResponse(401)
            _FakeWebsiteClient.imported_payloads.append(json)
            _FakeWebsiteClient.import_urls.append(url)
            tasks = (json or {}).get("tasks", [])
            subtask_count = sum(len(t.get("subtasks", [])) for t in tasks)
            return _FakeResponse(200, {"imported_tasks": len(tasks), "imported_subtasks": subtask_count})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, cookies=None):
        assert url.endswith("/api/export")
        token = (cookies or {}).get(settings.cookie_name)
        if token == "fake-session-token":
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
        if token == "fake-session-token-carol":
            return _FakeResponse(200, {"version": 1, "exported_at": "2026-01-01T00:00:00", "tasks": []})
        return _FakeResponse(401)


@pytest.fixture(autouse=True)
def _reset_fake_website_imports():
    _FakeWebsiteClient.imported_payloads = []
    _FakeWebsiteClient.import_urls = []


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


def test_sync_now_replaces_the_currently_logged_in_local_account(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    # Local account is a guest, unrelated username to the website's "alice".
    guest_resp = client.post("/api/auth/guest")
    guest_username = guest_resp.json()["username"]
    client.post("/api/tasks", json={"text": "Already local", "priority": "Medium", "category": "General"})

    r = client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 0}

    # Pull is a mirror, not a merge: the pre-existing local task is gone,
    # replaced entirely by the website's.
    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t["text"] for t in tasks] == ["Task from the website"]

    # Sanity: nothing landed in some other/new account - it's specifically
    # the currently-authenticated local guest that got the imported task.
    assert client.get("/api/auth/me").json()["username"] == guest_username


def test_sync_now_does_not_duplicate_across_repeated_calls(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1  # each pull replaces the last, not adds to it


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
    # Portable fields only, matching /api/export's own shape - no username/
    # created_at/position leaking into the pushed payload. id is included
    # (needed to remap assigned_task_id references on the receiving end).
    assert set(sent_tasks[0].keys()) == {
        "id", "text", "priority", "category", "due_date", "done", "pinned", "urgent", "notes",
        "assigned_task_id", "in_progress", "links", "subtasks",
    }
    # Push mirrors onto the website (see crud.import_data's replace mode) -
    # it must ask for that explicitly, not fall back to the regular
    # file-import endpoint's additive default.
    assert _FakeWebsiteClient.import_urls == ["https://checklist-kmtw.onrender.com/api/import?replace=true"]


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


# ----------------------------- Persisted website link -----------------------------


def test_website_link_status_requires_desktop_build(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: False)
    client.post("/api/auth/guest")
    r = client.get("/api/auth/website-link")
    assert r.status_code == 503


def test_website_link_status_starts_unlinked(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    client.post("/api/auth/guest")
    r = client.get("/api/auth/website-link")
    assert r.status_code == 200
    assert r.json() == {"linked": False, "username": None}


def test_pull_with_credentials_persists_the_link(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})

    r = client.get("/api/auth/website-link")
    assert r.json() == {"linked": True, "username": "alice"}


def test_push_with_credentials_persists_the_link(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})

    r = client.get("/api/auth/website-link")
    assert r.json() == {"linked": True, "username": "alice"}


def test_sync_without_credentials_reuses_the_linked_account(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    # No body at all this time - same as a fresh app launch calling
    # autosave/Ctrl+S without ever re-prompting for credentials.
    r = client.post("/api/auth/sync")
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 0}


def test_push_without_credentials_reuses_the_linked_account(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")
    client.post("/api/tasks", json={"text": "Autosaved task", "priority": "Medium", "category": "General"})

    client.post("/api/auth/push", json={"username": "alice", "password": "correct-password"})
    r = client.post("/api/auth/push", json={})  # empty body, same as autosave's silent push
    assert r.status_code == 200
    assert len(_FakeWebsiteClient.imported_payloads) == 2


def test_sync_without_credentials_and_no_link_fails(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    client.post("/api/auth/guest")
    r = client.post("/api/auth/sync")
    assert r.status_code == 400


def test_relinking_overwrites_the_previous_link(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")

    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    client.post("/api/auth/sync", json={"username": "carol", "password": "other-password"})

    r = client.get("/api/auth/website-link")
    assert r.json() == {"linked": True, "username": "carol"}

    # And a credential-less call now reuses carol, not alice.
    r2 = client.post("/api/auth/sync")
    assert r2.status_code == 200
    assert r2.json() == {"imported_tasks": 0, "imported_subtasks": 0}  # carol's fake account has no tasks


def test_unlink_clears_the_stored_link(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)
    client.post("/api/auth/guest")
    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})

    r = client.post("/api/auth/website-link/clear")
    assert r.status_code == 204

    assert client.get("/api/auth/website-link").json() == {"linked": False, "username": None}
    assert client.post("/api/auth/sync").status_code == 400


def test_unlink_requires_desktop_build(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: False)
    client.post("/api/auth/guest")
    r = client.post("/api/auth/website-link/clear")
    assert r.status_code == 503


def test_website_link_is_per_local_account(client, monkeypatch):
    """Two different local accounts linking to (the same or different)
    website accounts don't clobber each other's link - it's keyed by the
    local username, not global."""
    monkeypatch.setattr("app.routers.auth.is_desktop_build", lambda: True)
    monkeypatch.setattr("app.routers.auth.httpx.Client", _FakeWebsiteClient)

    client.post("/api/auth/guest")
    client.post("/api/auth/sync", json={"username": "alice", "password": "correct-password"})
    client.post("/api/auth/logout")

    client.post("/api/auth/guest")  # a second, different local guest account
    r = client.get("/api/auth/website-link")
    assert r.json() == {"linked": False, "username": None}
