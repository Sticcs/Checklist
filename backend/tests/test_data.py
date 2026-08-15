def _add_task(client, **overrides):
    body = {"text": "Task A", "priority": "High", "category": "Work", "due_date": None}
    body.update(overrides)
    return client.post("/api/tasks", json=body).json()


def test_export_includes_task_and_subtask_fields(guest_client):
    client, _ = guest_client
    task = _add_task(client, text="Plan trip", pinned=False)
    client.patch(f"/api/tasks/{task['id']}/pin", json={"pinned": True})
    client.patch(f"/api/tasks/{task['id']}/notes", json={"notes": "Bring passport"})
    subtask = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Book flights"}).json()["subtask"]
    client.patch(f"/api/subtasks/{subtask['id']}/notes", json={"notes": "Check visa rules"})
    client.patch(f"/api/subtasks/{subtask['id']}/urgent", json={"urgent": True})

    r = client.get("/api/export")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="checklist-export.json"'
    body = r.json()

    assert body["version"] == 1
    assert len(body["tasks"]) == 1
    exported = body["tasks"][0]
    # Portable fields only - no id/username/created_at/position leaking out.
    assert set(exported.keys()) == {
        "text", "priority", "category", "due_date", "done", "pinned", "urgent", "notes", "subtasks",
    }
    assert exported["text"] == "Plan trip"
    assert exported["pinned"] is True
    assert exported["notes"] == "Bring passport"
    assert len(exported["subtasks"]) == 1
    assert exported["subtasks"][0]["text"] == "Book flights"
    assert exported["subtasks"][0]["notes"] == "Check visa rules"
    assert exported["subtasks"][0]["urgent"] is True


def test_import_recreates_tasks_and_subtasks(guest_client):
    client, _ = guest_client
    payload = {
        "version": 1,
        "exported_at": "2026-01-01T00:00:00",
        "tasks": [
            {
                "text": "Imported task",
                "priority": "Low",
                "category": "Personal",
                "due_date": "2026-02-01",
                "done": True,
                "pinned": True,
                "urgent": False,
                "notes": "From export",
                "subtasks": [
                    {"text": "Sub A", "done": True, "urgent": False, "due_date": None, "notes": "hi"},
                    {"text": "Sub B", "done": False, "urgent": True, "due_date": None, "notes": None},
                ],
            }
        ],
    }

    r = client.post("/api/import", json=payload)
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 2}

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["text"] == "Imported task"
    assert task["done"] is True
    assert task["pinned"] is True
    assert task["notes"] == "From export"
    assert len(task["subtasks"]) == 2
    assert {s["text"] for s in task["subtasks"]} == {"Sub A", "Sub B"}


def test_import_is_additive_not_a_replace(guest_client):
    client, _ = guest_client
    _add_task(client, text="Already here")

    payload = {
        "version": 1,
        "exported_at": "2026-01-01T00:00:00",
        "tasks": [{"text": "Imported", "priority": "Medium", "category": "General", "subtasks": []}],
    }
    client.post("/api/import", json=payload)

    texts = sorted(t["text"] for t in client.get("/api/tasks").json()["tasks"])
    assert texts == ["Already here", "Imported"]


def test_export_then_import_round_trip_preserves_data(guest_client):
    client, _ = guest_client
    task = _add_task(client, text="Round trip")
    client.patch(f"/api/tasks/{task['id']}/notes", json={"notes": "note text"})
    client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "step"})
    subtask = client.get("/api/tasks").json()["tasks"][0]["subtasks"][0]
    client.patch(f"/api/subtasks/{subtask['id']}/notes", json={"notes": "sub note"})

    exported = client.get("/api/export").json()
    client.post("/api/tasks/clear-all")  # so the re-imported copy is unambiguous
    r = client.post("/api/import", json=exported)
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["text"] == "Round trip"
    assert tasks[0]["notes"] == "note text"
    assert tasks[0]["subtasks"][0]["notes"] == "sub note"


def test_import_with_replace_wipes_existing_data_first(guest_client):
    client, _ = guest_client
    _add_task(client, text="Already here")

    payload = {
        "version": 1,
        "exported_at": "2026-01-01T00:00:00",
        "tasks": [{"text": "Imported", "priority": "Medium", "category": "General", "subtasks": []}],
    }
    r = client.post("/api/import?replace=true", json=payload)
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 1, "imported_subtasks": 0}

    texts = [t["text"] for t in client.get("/api/tasks").json()["tasks"]]
    assert texts == ["Imported"]


def test_import_with_replace_and_no_tasks_just_clears(guest_client):
    client, _ = guest_client
    _add_task(client, text="Already here")

    payload = {"version": 1, "exported_at": "2026-01-01T00:00:00", "tasks": []}
    r = client.post("/api/import?replace=true", json=payload)
    assert r.status_code == 200
    assert r.json() == {"imported_tasks": 0, "imported_subtasks": 0}
    assert client.get("/api/tasks").json()["tasks"] == []


def test_import_requires_auth(client):
    r = client.post(
        "/api/import",
        json={"version": 1, "exported_at": "2026-01-01T00:00:00", "tasks": []},
    )
    assert r.status_code == 401
