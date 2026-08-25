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


def test_undo_completing_a_task_removes_it_from_the_streak(guest_client):
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"}
    ).json()

    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    stats = client.get("/api/stats").json()
    assert stats["total_completed"] == 1
    assert stats["current_streak"] == 1

    r = client.post("/api/undo")
    assert r.status_code == 200
    assert r.json()["tasks"][0]["done"] is False

    stats = client.get("/api/stats").json()
    assert stats["total_completed"] == 0
    assert stats["current_streak"] == 0


def test_redo_recompleting_a_task_restores_the_streak(guest_client):
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"}
    ).json()
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    client.post("/api/undo")
    assert client.get("/api/stats").json()["total_completed"] == 0

    r = client.post("/api/redo")
    assert r.status_code == 200
    assert r.json()["tasks"][0]["done"] is True

    stats = client.get("/api/stats").json()
    assert stats["total_completed"] == 1
    assert stats["current_streak"] == 1


def test_undo_unrelated_action_does_not_touch_a_separate_completion(guest_client):
    """Undoing the *second* action (adding Task B) shouldn't remove Task A's
    completion from the streak - only a done-state flip should."""
    client, _ = guest_client
    task_a = client.post(
        "/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"}
    ).json()
    client.patch(f"/api/tasks/{task_a['id']}/done", json={"done": True})
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})

    assert client.get("/api/stats").json()["total_completed"] == 1

    client.post("/api/undo")  # undoes "add Task B"
    stats = client.get("/api/stats").json()
    assert stats["total_completed"] == 1  # Task A's completion is untouched


def test_undo_of_unrelated_action_preserves_subtask_notes(guest_client):
    """restore_subtasks() deletes and reinserts every subtask on any
    undo/redo (see its docstring) - notes have no undo history of their own
    (like task notes), so this only round-trips correctly if the reinsert
    actually carries the notes column along."""
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "Task A", "priority": "Medium", "category": "General"}
    ).json()
    subtask = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 1"}).json()["subtask"]
    client.patch(f"/api/subtasks/{subtask['id']}/notes", json={"notes": "Remember to bring snacks"})

    # An unrelated mutation - its undo snapshot is what actually gets
    # restored below, not anything to do with the subtask itself.
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    r = client.post("/api/undo")
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    task_a = next(t for t in tasks if t["text"] == "Task A")
    assert task_a["subtasks"][0]["notes"] == "Remember to bring snacks"


def test_undo_of_unrelated_action_preserves_assigned_task_id(guest_client):
    """restore_state() deletes and reinserts every task on any undo/redo -
    assigned_task_id (an assessment "filed under" a task, see
    set_task_assignment) has no undo history of its own, so this only
    round-trips correctly if the reinsert actually carries that column
    along - same class of bug as the subtask-notes case above."""
    client, _ = guest_client
    main_task = client.post(
        "/api/tasks", json={"text": "Main task", "priority": "Medium", "category": "General"}
    ).json()
    assessment = client.post(
        "/api/tasks", json={"text": "Assessment", "priority": "Medium", "category": "Assessment"}
    ).json()
    client.patch(f"/api/tasks/{assessment['id']}/assign", json={"assigned_task_id": main_task["id"]})

    # An unrelated mutation - its undo snapshot is what actually gets
    # restored below, not anything to do with the assignment itself.
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    r = client.post("/api/undo")
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded_assessment = next(t for t in tasks if t["text"] == "Assessment")
    assert reloaded_assessment["assigned_task_id"] == main_task["id"]


def test_undo_of_unrelated_action_preserves_in_progress(guest_client):
    """restore_state() deletes and reinserts every task on any undo/redo -
    in_progress (see set_task_in_progress) has no undo history of its own,
    so this only round-trips correctly if the reinsert actually carries that
    column along - same class of bug as the assigned_task_id case above."""
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "Essay", "priority": "Medium", "category": "Assessment"}
    ).json()
    client.patch(f"/api/tasks/{task['id']}/in-progress", json={"in_progress": True})

    # An unrelated mutation - its undo snapshot is what actually gets
    # restored below, not anything to do with in_progress itself.
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    r = client.post("/api/undo")
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["text"] == "Essay")
    assert reloaded["in_progress"] is True


def test_undo_of_unrelated_action_preserves_links(guest_client):
    """Same class of bug as the assigned_task_id/in_progress cases above:
    restore_state() deletes and reinserts every task on any undo/redo, so
    links (see set_task_links) must round-trip through that reinsert too."""
    client, _ = guest_client
    task = client.post(
        "/api/tasks", json={"text": "Essay", "priority": "Medium", "category": "Assessment"}
    ).json()
    client.patch(
        f"/api/tasks/{task['id']}/links",
        json={"links": [{"name": "Rubric", "url": "https://example.edu/rubric"}]},
    )

    # An unrelated mutation - its undo snapshot is what actually gets
    # restored below, not anything to do with links themselves.
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    r = client.post("/api/undo")
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["text"] == "Essay")
    assert reloaded["links"] == [{"name": "Rubric", "url": "https://example.edu/rubric"}]


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
