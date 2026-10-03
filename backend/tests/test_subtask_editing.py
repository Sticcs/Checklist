from fastapi.testclient import TestClient

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


def _join(client, task_id):
    token = client.post(f"/api/tasks/{task_id}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    return other, other_username


# ----------------------------- Editing subtask text -----------------------------

def test_edit_subtask_text(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = client.patch(f"/api/subtasks/{subtask_id}/text", json={"text": "Final"})
    assert r.status_code == 200
    assert r.json()["subtask"]["text"] == "Final"

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["subtasks"][0]["text"] == "Final"


def test_edit_subtask_text_rejects_blank(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = client.patch(f"/api/subtasks/{subtask_id}/text", json={"text": "   "})
    assert r.status_code == 400


def test_collaborator_can_edit_subtask_text(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = other.patch(f"/api/subtasks/{subtask_id}/text", json={"text": "Edited by collaborator"})
    assert r.status_code == 200
    assert r.json()["subtask"]["text"] == "Edited by collaborator"


def test_stranger_cannot_edit_subtask_text(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    stranger, _ = _second_guest(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = stranger.patch(f"/api/subtasks/{subtask_id}/text", json={"text": "Hijacked"})
    assert r.status_code == 404


# ----------------------------- Collaborator access to urgent/due-date -----------------------------
# toggle_subtask_urgent and update_subtask_due_date used to be owner-only
# (_require_owning_task) even though the assignment workspace's mini task
# panel is collaborator-accessible for everything else about a subtask -
# fixed to match toggle_subtask_done/update_subtask_assignee/remove_subtask.

def test_collaborator_can_mark_subtask_urgent(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = other.patch(f"/api/subtasks/{subtask_id}/urgent", json={"urgent": True})
    assert r.status_code == 200
    assert r.json()["subtask"]["urgent"] is True


def test_collaborator_can_set_subtask_due_date(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    r = other.patch(f"/api/subtasks/{subtask_id}/due-date", json={"due_date": "2026-12-25"})
    assert r.status_code == 200
    assert r.json()["subtask"]["due_date"] == "2026-12-25"


def test_stranger_cannot_mark_urgent_or_set_due_date(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    stranger, _ = _second_guest(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    assert stranger.patch(f"/api/subtasks/{subtask_id}/urgent", json={"urgent": True}).status_code == 404
    assert (
        stranger.patch(f"/api/subtasks/{subtask_id}/due-date", json={"due_date": "2026-12-25"}).status_code == 404
    )


# ----------------------------- Last edited by -----------------------------

def test_subtask_urgent_toggle_updates_last_edited_by(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    other.patch(f"/api/subtasks/{subtask_id}/urgent", json={"urgent": True})
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == other_username


def test_subtask_due_date_updates_last_edited_by(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    other.patch(f"/api/subtasks/{subtask_id}/due-date", json={"due_date": "2026-12-25"})
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == other_username


def test_subtask_text_edit_updates_last_edited_by(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Draft"}).json()["subtask"]["id"]

    other.patch(f"/api/subtasks/{subtask_id}/text", json={"text": "Edited"})
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == other_username
