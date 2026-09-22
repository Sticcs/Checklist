from fastapi.testclient import TestClient

from app import presence
from app.main import app


def _add_task(client, text="Assignment", priority="Medium", category="Assessment", due_date=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": due_date},
    )
    assert r.status_code == 201
    return r.json()


def _second_guest(client):
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def test_heartbeat_reports_self_online(guest_client):
    client, owner = guest_client
    task = _add_task(client)

    r = client.post(f"/api/tasks/{task['id']}/presence")
    assert r.status_code == 200
    assert r.json()["online"] == [owner]


def test_two_collaborators_see_each_other_online(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    client.post(f"/api/tasks/{task['id']}/presence")
    r = other.post(f"/api/tasks/{task['id']}/presence")

    assert set(r.json()["online"]) == {owner, other_username}


def test_presence_requires_assignment_access(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _second_guest(client)

    r = other.post(f"/api/tasks/{task['id']}/presence")
    assert r.status_code == 404


def test_presence_requires_assessment_category(guest_client):
    client, _ = guest_client
    task = _add_task(client, category="Study")
    r = client.post(f"/api/tasks/{task['id']}/presence")
    assert r.status_code == 400


def test_stale_heartbeat_drops_out_of_online_list(guest_client, monkeypatch):
    client, owner = guest_client
    task = _add_task(client)

    client.post(f"/api/tasks/{task['id']}/presence")
    assert owner in presence.online_users(task["id"])

    # Simulate the online window elapsing without waiting for it in real
    # time - same monkeypatch-a-constant style as the rest of this suite.
    monkeypatch.setattr(presence, "ONLINE_WINDOW_SECONDS", -1)
    assert presence.online_users(task["id"]) == []
