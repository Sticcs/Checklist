from fastapi.testclient import TestClient

from app import crud
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


def test_owner_and_collaborator_can_send_and_read_messages(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])

    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})
    assert r.status_code == 201
    assert r.json()["username"] == owner
    assert r.json()["text"] == "hi"

    body = other.get(f"/api/tasks/{task['id']}/messages").json()
    assert [m["text"] for m in body["messages"]] == ["hi"]
    assert body["unread_count"] == 1  # other hasn't read it yet


def test_sending_your_own_message_does_not_count_as_your_own_unread(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    assert client.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 0


def test_marking_read_clears_unread_count(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})
    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 1

    r = other.post(f"/api/tasks/{task['id']}/messages/read")
    assert r.status_code == 204
    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 0


def test_new_message_after_read_is_unread_again(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "first"})
    other.post(f"/api/tasks/{task['id']}/messages/read")
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "second"})

    assert other.get(f"/api/tasks/{task['id']}/messages").json()["unread_count"] == 1


def test_stranger_cannot_read_or_send(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _second_guest(client)

    assert other.get(f"/api/tasks/{task['id']}/messages").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"}).status_code == 404


def test_empty_message_rejected(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "   "})
    assert r.status_code == 400


def test_overlong_message_rejected(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    r = client.post(f"/api/tasks/{task['id']}/messages", json={"text": "x" * 2001})
    assert r.status_code == 400


def test_deleting_the_task_removes_messages(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    client.delete(f"/api/tasks/{task['id']}")

    assert crud.list_chat_messages(task["id"]) == []


def test_clearing_completed_removes_messages_for_cleared_tasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/messages", json={"text": "hi"})

    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    client.post("/api/tasks/clear-completed")

    assert crud.list_chat_messages(task["id"]) == []
