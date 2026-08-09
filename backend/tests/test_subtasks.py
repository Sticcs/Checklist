def _add_task(client, text="Parent task"):
    r = client.post("/api/tasks", json={"text": text, "priority": "Medium", "category": "General"})
    return r.json()


def test_add_subtask(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    r = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step one"})
    assert r.status_code == 201
    body = r.json()
    assert body["subtask"]["text"] == "Step one"
    assert body["subtask"]["done"] is False
    assert body["parent_done"] is False

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks[0]["subtasks"]) == 1


def test_adding_subtask_unmarks_completed_parent(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    r = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "New step"})
    assert r.json()["parent_done"] is False

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["done"] is False


def test_completing_all_subtasks_completes_parent(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    s1 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 1"}).json()["subtask"]
    s2 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 2"}).json()["subtask"]

    r = client.patch(f"/api/subtasks/{s1['id']}", json={"done": True})
    assert r.json()["parent_done"] is False  # s2 still open

    r = client.patch(f"/api/subtasks/{s2['id']}", json={"done": True})
    assert r.json()["parent_done"] is True

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["done"] is True


def test_uncompleting_one_subtask_uncompletes_parent(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    s1 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 1"}).json()["subtask"]
    client.patch(f"/api/subtasks/{s1['id']}", json={"done": True})
    assert client.get("/api/tasks").json()["tasks"][0]["done"] is True

    r = client.patch(f"/api/subtasks/{s1['id']}", json={"done": False})
    assert r.json()["parent_done"] is False


def test_delete_subtask(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    s1 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 1"}).json()["subtask"]

    r = client.delete(f"/api/subtasks/{s1['id']}")
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks[0]["subtasks"] == []


def test_deleting_last_open_subtask_completes_parent(guest_client):
    # Matches main.py's delete_subtask behavior: if every *remaining* subtask
    # is done, the parent becomes done - deleting the only open one among
    # otherwise-done subtasks flips the parent to done.
    client, _ = guest_client
    task = _add_task(client)
    s1 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Done one"}).json()["subtask"]
    s2 = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Open one"}).json()["subtask"]
    client.patch(f"/api/subtasks/{s1['id']}", json={"done": True})

    r = client.delete(f"/api/subtasks/{s2['id']}")
    assert r.json()["parent_done"] is True


def test_subtask_operations_on_nonexistent_id_404(guest_client):
    client, _ = guest_client
    assert client.patch("/api/subtasks/999", json={"done": True}).status_code == 404
    assert client.delete("/api/subtasks/999").status_code == 404


def test_cannot_touch_another_users_subtask(client):
    from fastapi.testclient import TestClient

    from app.main import app

    client_a = TestClient(app)
    client_a.post("/api/auth/guest")
    task = _add_task(client_a)
    subtask = client_a.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "A's step"}).json()["subtask"]

    client_b = TestClient(app)
    client_b.post("/api/auth/guest")
    r = client_b.patch(f"/api/subtasks/{subtask['id']}", json={"done": True})
    assert r.status_code == 404
