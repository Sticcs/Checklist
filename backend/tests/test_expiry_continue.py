from fastapi.testclient import TestClient

from app.main import app


def _second_guest(client):
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def _add_task(client, text="Task", list_id=None):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": "Medium", "category": "General", "due_date": None, "list_id": list_id},
    )
    assert r.status_code == 201
    return r.json()


def _create_expiry_list(client, expires_at="2026-12-31T23:59"):
    r = client.post("/api/lists", json={"kind": "expiry", "expires_at": expires_at})
    assert r.status_code == 201
    return r.json()


def test_clear_completed_in_list_only_deletes_done_tasks_in_that_list(guest_client):
    client, _ = guest_client
    expiry = _create_expiry_list(client)
    other = _create_expiry_list(client, expires_at="2026-11-30T23:59")

    done_task = _add_task(client, "Done in expiry", list_id=expiry["id"])
    not_done_task = _add_task(client, "Not done in expiry", list_id=expiry["id"])
    done_in_other = _add_task(client, "Done in other list", list_id=other["id"])
    client.patch(f"/api/tasks/{done_task['id']}/done", json={"done": True})
    client.patch(f"/api/tasks/{done_in_other['id']}/done", json={"done": True})

    r = client.post(f"/api/lists/{expiry['id']}/clear-completed")
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 1

    tasks = client.get("/api/tasks").json()["tasks"]
    ids = {t["id"] for t in tasks}
    assert done_task["id"] not in ids
    assert not_done_task["id"] in ids
    # A done task in a *different* list is untouched.
    assert done_in_other["id"] in ids


def test_clear_completed_in_list_also_removes_their_subtasks(guest_client):
    client, _ = guest_client
    expiry = _create_expiry_list(client)
    done_task = _add_task(client, "Done with subtask", list_id=expiry["id"])
    sub = client.post(f"/api/tasks/{done_task['id']}/subtasks", json={"text": "sub"}).json()["subtask"]
    client.patch(f"/api/tasks/{done_task['id']}/done", json={"done": True})

    r = client.post(f"/api/lists/{expiry['id']}/clear-completed")
    assert r.status_code == 200
    assert r.json()["deleted_count"] == 1

    # The subtask's owning task is gone, so looking it up via the normal
    # subtask-mutation path now 404s.
    r2 = client.patch(f"/api/subtasks/{sub['id']}", json={"done": True})
    assert r2.status_code == 404


def test_continue_expiry_list_sets_new_expiry_and_resets_cycle(guest_client):
    client, _ = guest_client
    expiry = _create_expiry_list(client, expires_at="2026-01-01T00:00")

    r = client.post(f"/api/lists/{expiry['id']}/continue", json={"expires_at": "2027-06-15T12:00"})
    assert r.status_code == 200
    body = r.json()
    assert body["expires_at"] == "2027-06-15T12:00"
    # cycle_started_at moved to "now" - no longer equal to the original
    # created_at (which continue_expiry_list never touches).
    assert body["cycle_started_at"] != body["created_at"]


def test_continue_expiry_list_flags_incomplete_tasks_as_carried_over(guest_client):
    client, _ = guest_client
    expiry = _create_expiry_list(client)
    incomplete = _add_task(client, "Still open", list_id=expiry["id"])
    done = _add_task(client, "Already done", list_id=expiry["id"])
    client.patch(f"/api/tasks/{done['id']}/done", json={"done": True})

    client.post(f"/api/lists/{expiry['id']}/continue", json={"expires_at": "2027-06-15T12:00"})

    tasks = client.get("/api/tasks").json()["tasks"]
    incomplete_after = next(t for t in tasks if t["id"] == incomplete["id"])
    done_after = next(t for t in tasks if t["id"] == done["id"])
    assert incomplete_after["carried_over"] is True
    assert done_after["carried_over"] is False


def test_continue_expiry_list_404_for_someone_elses_list(guest_client):
    client, _ = guest_client
    expiry = _create_expiry_list(client)
    stranger, _ = _second_guest(client)
    r = stranger.post(f"/api/lists/{expiry['id']}/continue", json={"expires_at": "2027-06-15T12:00"})
    assert r.status_code == 404


def test_new_task_defaults_to_not_carried_over(guest_client):
    client, _ = guest_client
    task = _add_task(client, "Fresh task")
    assert task["carried_over"] is False
