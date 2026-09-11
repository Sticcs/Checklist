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


def _fresh_anonymous_client():
    return TestClient(app)


def _notifications(client):
    r = client.get("/api/notifications")
    assert r.status_code == 200
    return r.json()


# ----------------------------- item_checked -----------------------------


def test_collaborator_checking_off_a_task_notifies_the_owner(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    body = _notifications(client)
    assert body["unread_count"] == 1
    entry = body["notifications"][0]
    assert entry["kind"] == "item_checked"
    assert entry["actor_username"] == other_username
    assert entry["task_id"] == task["id"]
    assert task["text"] in entry["message"]
    assert entry["read"] is False


def test_owner_toggling_their_own_task_does_not_notify_themselves(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    assert _notifications(client)["notifications"] == []


def test_repeated_done_true_does_not_spam_notifications(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    assert len(_notifications(client)["notifications"]) == 1


def test_marking_not_done_does_not_notify(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    other.patch(f"/api/tasks/{task['id']}/done", json={"done": False})

    assert _notifications(client)["notifications"] == []


def test_collaborator_checking_off_a_subtask_notifies_the_owner(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    other.patch(f"/api/subtasks/{subtask_id}", json={"done": True})

    body = _notifications(client)
    assert len(body["notifications"]) == 1
    entry = body["notifications"][0]
    assert entry["kind"] == "item_checked"
    assert entry["actor_username"] == other_username
    assert "Sub 1" in entry["message"]
    assert task["text"] in entry["message"]


def test_anonymous_public_list_toggle_notifies_the_owner(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    item = client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    ).json()
    token = client.post(f"/api/lists/{created['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    anon.patch(f"/api/public/lists/{token}/items/{item['id']}", json={"done": True})

    body = _notifications(client)
    assert len(body["notifications"]) == 1
    entry = body["notifications"][0]
    assert entry["kind"] == "item_checked"
    assert entry["actor_username"] is None
    assert "Milk" in entry["message"]
    assert created["name"] in entry["message"]


def test_repeated_anonymous_toggle_does_not_spam(guest_client):
    client, _ = guest_client
    created = client.post("/api/lists").json()
    item = client.post(
        "/api/tasks", json={"text": "Milk", "priority": "Medium", "category": "General", "list_id": created["id"]}
    ).json()
    token = client.post(f"/api/lists/{created['id']}/share-link").json()["token"]

    anon = _fresh_anonymous_client()
    anon.patch(f"/api/public/lists/{token}/items/{item['id']}", json={"done": True})
    anon.patch(f"/api/public/lists/{token}/items/{item['id']}", json={"done": True})

    assert len(_notifications(client)["notifications"]) == 1


# ----------------------------- subtask_assigned -----------------------------


def test_being_assigned_a_subtask_notifies_you(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": other_username})

    body = _notifications(other)
    assert len(body["notifications"]) == 1
    entry = body["notifications"][0]
    assert entry["kind"] == "subtask_assigned"
    assert entry["actor_username"] == owner
    assert entry["task_id"] == task["id"]
    assert "Sub 1" in entry["message"]

    # The owner assigning it doesn't notify themselves.
    assert _notifications(client)["notifications"] == []


def test_assigning_to_yourself_does_not_notify(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": owner})

    assert _notifications(client)["notifications"] == []


def test_unassigning_does_not_notify(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    subtask_id = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"}).json()["subtask"]["id"]

    client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": other_username})
    client.patch(f"/api/subtasks/{subtask_id}/assignee", json={"assigned_username": None})

    # Only the one assignment notification, nothing from the unassign.
    assert len(_notifications(other)["notifications"]) == 1


# ----------------------------- access_revoked -----------------------------


def test_owner_removing_a_collaborator_notifies_them(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    client.delete(f"/api/tasks/{task['id']}/collaborators/{other_username}")

    body = _notifications(other)
    assert len(body["notifications"]) == 1
    entry = body["notifications"][0]
    assert entry["kind"] == "access_revoked"
    assert entry["actor_username"] == owner
    assert entry["task_id"] is None
    assert task["text"] in entry["message"]


def test_self_leave_does_not_notify_anyone(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = other.delete(f"/api/tasks/{task['id']}/collaborators/{other_username}")
    assert r.status_code == 204

    assert _notifications(other)["notifications"] == []
    assert _notifications(client)["notifications"] == []


# ----------------------------- Read/unread -----------------------------


def test_mark_one_read(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    notification_id = _notifications(client)["notifications"][0]["id"]
    r = client.post(f"/api/notifications/{notification_id}/read")
    assert r.status_code == 204

    body = _notifications(client)
    assert body["unread_count"] == 0
    assert body["notifications"][0]["read"] is True


def test_mark_all_read(guest_client):
    client, owner = guest_client
    task_a = _add_task(client, text="Assignment A")
    task_b = _add_task(client, text="Assignment B")
    token_a = client.post(f"/api/tasks/{task_a['id']}/share-link").json()["token"]
    token_b = client.post(f"/api/tasks/{task_b['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token_a}")
    other.post(f"/api/assignments/join/{token_b}")
    other.patch(f"/api/tasks/{task_a['id']}/done", json={"done": True})
    other.patch(f"/api/tasks/{task_b['id']}/done", json={"done": True})

    assert _notifications(client)["unread_count"] == 2
    r = client.post("/api/notifications/read-all")
    assert r.status_code == 204
    assert _notifications(client)["unread_count"] == 0


def test_cannot_mark_someone_elses_notification_read(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    notification_id = _notifications(client)["notifications"][0]["id"]

    stranger, _ = _second_guest(client)
    r = stranger.post(f"/api/notifications/{notification_id}/read")
    assert r.status_code == 404
    # The real owner's notification is untouched.
    assert _notifications(client)["notifications"][0]["read"] is False


def test_unauthenticated_cannot_list_notifications(client):
    r = client.get("/api/notifications")
    assert r.status_code == 401
