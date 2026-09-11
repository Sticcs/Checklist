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


def test_owner_can_assign_a_mini_task_to_a_collaborator(guest_client):
    client, owner_username = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    r = client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": other_username})
    assert r.status_code == 200
    assert r.json()["subtask"]["assigned_username"] == other_username


def test_collaborator_can_assign_and_reassign(guest_client):
    client, owner_username = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    r = other.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": owner_username})
    assert r.status_code == 200
    assert r.json()["subtask"]["assigned_username"] == owner_username

    # Reassign to self.
    r = other.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": other_username})
    assert r.status_code == 200
    assert r.json()["subtask"]["assigned_username"] == other_username

    # Unassign.
    r = other.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": None})
    assert r.status_code == 200
    assert r.json()["subtask"]["assigned_username"] is None


def test_stranger_cannot_assign(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]
    other, other_username = _second_guest(client)

    r = other.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": other_username})
    assert r.status_code == 404


def test_cannot_assign_to_a_non_collaborator(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]
    _, stranger_username = _second_guest(client)

    r = client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": stranger_username})
    assert r.status_code == 400
