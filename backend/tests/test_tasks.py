def _add_task(client, text="Buy milk", priority="High", category="House", due_date=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": due_date},
    )
    assert r.status_code == 201
    return r.json()


def test_create_and_list_task(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["text"] == "Buy milk"
    assert task["done"] is False
    assert task["pinned"] is False
    assert task["subtasks"] == []

    r = client.get("/api/tasks")
    assert r.status_code == 200
    body = r.json()
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["id"] == task["id"]
    assert body["can_undo"] is True
    assert body["can_redo"] is False


def test_create_task_requires_text(guest_client):
    client, _ = guest_client
    r = client.post("/api/tasks", json={"text": "   ", "priority": "Medium", "category": "General"})
    assert r.status_code == 400


def test_toggle_done(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    r = client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True

    r = client.patch(f"/api/tasks/{task['id']}/done", json={"done": False})
    assert r.json()["done"] is False


def test_toggle_pin(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    r = client.patch(f"/api/tasks/{task['id']}/pin", json={"pinned": True})
    assert r.status_code == 200
    assert r.json()["pinned"] is True


def test_toggle_in_progress(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["in_progress"] is False

    r = client.patch(f"/api/tasks/{task['id']}/in-progress", json={"in_progress": True})
    assert r.status_code == 200
    assert r.json()["in_progress"] is True

    r = client.patch(f"/api/tasks/{task['id']}/in-progress", json={"in_progress": False})
    assert r.json()["in_progress"] is False


def test_completing_a_task_clears_in_progress(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.patch(f"/api/tasks/{task['id']}/in-progress", json={"in_progress": True})

    r = client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert r.status_code == 200
    assert r.json()["in_progress"] is False


def test_set_links(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["links"] == []

    r = client.patch(
        f"/api/tasks/{task['id']}/links",
        json={"links": [{"name": "Course site", "url": "https://example.edu/course"}]},
    )
    assert r.status_code == 200
    assert r.json()["links"] == [{"name": "Course site", "url": "https://example.edu/course"}]

    # Whole-list replacement - removing a link means PATCHing without it.
    r = client.patch(f"/api/tasks/{task['id']}/links", json={"links": []})
    assert r.json()["links"] == []


def test_edit_task(guest_client):
    client, _ = guest_client
    task = _add_task(client, text="Old text")

    r = client.patch(
        f"/api/tasks/{task['id']}",
        json={"text": "New text", "priority": "Low", "category": "Work", "due_date": "2026-01-01"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "New text"
    assert body["priority"] == "Low"
    assert body["due_date"] == "2026-01-01"


def test_delete_task(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    r = client.delete(f"/api/tasks/{task['id']}")
    assert r.status_code == 204

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks == []


def test_mutating_nonexistent_task_404s(guest_client):
    client, _ = guest_client
    assert client.patch("/api/tasks/999/done", json={"done": True}).status_code == 404
    assert client.delete("/api/tasks/999").status_code == 404


def test_cannot_mutate_another_users_task(client):
    from fastapi.testclient import TestClient

    from app.main import app

    client_a = TestClient(app)
    client_a.post("/api/auth/guest")
    task = _add_task(client_a)

    client_b = TestClient(app)
    client_b.post("/api/auth/guest")
    r = client_b.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert r.status_code == 404


def test_bulk_mark_all_completed(guest_client):
    client, _ = guest_client
    _add_task(client, text="One")
    _add_task(client, text="Two")

    r = client.post("/api/tasks/mark-all-completed")
    assert r.status_code == 200
    assert r.json()["updated_count"] == 2

    tasks = client.get("/api/tasks").json()["tasks"]
    assert all(t["done"] for t in tasks)


def test_bulk_clear_completed(guest_client):
    client, _ = guest_client
    t1 = _add_task(client, text="Done one")
    _add_task(client, text="Still active")
    client.patch(f"/api/tasks/{t1['id']}/done", json={"done": True})

    r = client.post("/api/tasks/clear-completed")
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 1

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["text"] == "Still active"


def test_bulk_clear_all(guest_client):
    client, _ = guest_client
    _add_task(client, text="One")
    _add_task(client, text="Two")

    r = client.post("/api/tasks/clear-all")
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 2

    assert client.get("/api/tasks").json()["tasks"] == []


def test_activity_log_records_actions(guest_client):
    client, _ = guest_client
    task = _add_task(client, text="Write report")
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    client.patch(f"/api/tasks/{task['id']}/pin", json={"pinned": True})
    client.delete(f"/api/tasks/{task['id']}")

    r = client.get("/api/activity")
    assert r.status_code == 200
    entries = r.json()
    actions = [e["action"] for e in entries]
    # Newest first
    assert actions[:4] == ["deleted", "pinned", "completed", "added"]
    assert all(e["detail"] == "Write report" for e in entries[:4])
