def _texts(client):
    return sorted(t["text"] for t in client.get("/api/tasks").json()["tasks"])


def test_undo_redo_not_available_initially(guest_client):
    client, _ = guest_client
    body = client.get("/api/tasks").json()
    assert body["can_undo"] is False
    assert body["can_redo"] is False

    assert client.post("/api/undo").status_code == 409
    assert client.post("/api/redo").status_code == 409


def test_undo_reverts_add_task(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"})
    assert _texts(client) == ["Task A"]

    r = client.post("/api/undo")
    assert r.status_code == 200
    assert r.json()["tasks"] == []
    assert _texts(client) == []


def test_redo_reapplies_undone_action(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"})
    client.post("/api/undo")
    assert _texts(client) == []

    r = client.post("/api/redo")
    assert r.status_code == 200
    assert _texts(client) == ["Task A"]


def test_new_action_clears_redo_stack(guest_client):
    client, _ = guest_client
    client.post("/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"})
    client.post("/api/undo")
    assert client.get("/api/tasks").json()["can_redo"] is True

    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    body = client.get("/api/tasks").json()
    assert body["can_redo"] is False
    assert client.post("/api/redo").status_code == 409


def test_full_mutate_mutate_undo_undo_redo_round_trip(guest_client):
    """The exit criterion from the migration plan: a sequence of mutations,
    two undos, then one redo, must land on exactly the expected state at
    every step - including subtasks, which are restored via a separate table
    wipe-and-reinsert (_restore_subtasks) that's easy to get subtly wrong."""
    client, _ = guest_client

    # 1. Add task A
    task_a = client.post(
        "/api/tasks", json={"text": "Task A", "priority": "High", "category": "Work"}
    ).json()
    assert _texts(client) == ["Task A"]

    # 2. Add a subtask to A
    client.post(f"/api/tasks/{task_a['id']}/subtasks", json={"text": "Subtask A1"})
    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks[0]["subtasks"]) == 1
    assert tasks[0]["subtasks"][0]["text"] == "Subtask A1"

    # 3. Add task B
    client.post("/api/tasks", json={"text": "Task B", "priority": "Low", "category": "House"})
    assert _texts(client) == ["Task A", "Task B"]

    # Undo #1: should remove Task B, leaving Task A + its subtask intact
    r = client.post("/api/undo")
    assert r.status_code == 200
    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t["text"] for t in tasks] == ["Task A"]
    assert len(tasks[0]["subtasks"]) == 1
    assert tasks[0]["subtasks"][0]["text"] == "Subtask A1"

    # Undo #2: should remove the subtask, leaving Task A with no subtasks
    r = client.post("/api/undo")
    assert r.status_code == 200
    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t["text"] for t in tasks] == ["Task A"]
    assert tasks[0]["subtasks"] == []

    body = client.get("/api/tasks").json()
    assert body["can_undo"] is True  # the "add Task A" snapshot is still there
    assert body["can_redo"] is True

    # Redo: should bring the subtask back
    r = client.post("/api/redo")
    assert r.status_code == 200
    tasks = client.get("/api/tasks").json()["tasks"]
    assert [t["text"] for t in tasks] == ["Task A"]
    assert len(tasks[0]["subtasks"]) == 1
    assert tasks[0]["subtasks"][0]["text"] == "Subtask A1"


def test_undo_redo_isolated_per_user(client):
    from fastapi.testclient import TestClient

    from app.main import app

    client_a = TestClient(app)
    client_a.post("/api/auth/guest")
    client_a.post("/api/tasks", json={"text": "A's task", "priority": "Medium", "category": "General"})

    client_b = TestClient(app)
    client_b.post("/api/auth/guest")
    # B has never mutated anything - nothing to undo, and B's undo must not
    # affect A's stack or A's data.
    assert client_b.post("/api/undo").status_code == 409

    tasks_a = client_a.get("/api/tasks").json()["tasks"]
    assert len(tasks_a) == 1
