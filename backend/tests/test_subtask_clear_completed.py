from fastapi.testclient import TestClient

from app.main import app


def _add_task(client, text="Task", priority="Medium", category="General"):
    r = client.post(
        "/api/tasks",
        json={"text": text, "priority": priority, "category": category, "due_date": None},
    )
    assert r.status_code == 201
    return r.json()


def _add_subtask(client, task_id, text="Sub"):
    r = client.post(f"/api/tasks/{task_id}/subtasks", json={"text": text})
    assert r.status_code == 201
    return r.json()["subtask"]


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


def test_clears_only_done_subtasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    done1 = _add_subtask(client, task["id"], "Done one")
    done2 = _add_subtask(client, task["id"], "Done two")
    pending = _add_subtask(client, task["id"], "Still pending")
    client.patch(f"/api/subtasks/{done1['id']}", json={"done": True})
    client.patch(f"/api/subtasks/{done2['id']}", json={"done": True})

    r = client.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 200
    body = r.json()
    remaining_ids = {s["id"] for s in body["subtasks"]}
    assert remaining_ids == {pending["id"]}

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["id"] == task["id"])
    assert [s["id"] for s in reloaded["subtasks"]] == [pending["id"]]


def test_leaves_other_tasks_subtasks_untouched(guest_client):
    client, _ = guest_client
    task_a = _add_task(client, text="Task A")
    task_b = _add_task(client, text="Task B")
    done_a = _add_subtask(client, task_a["id"], "Done in A")
    done_b = _add_subtask(client, task_b["id"], "Done in B")
    client.patch(f"/api/subtasks/{done_a['id']}", json={"done": True})
    client.patch(f"/api/subtasks/{done_b['id']}", json={"done": True})

    client.post(f"/api/tasks/{task_a['id']}/subtasks/clear-completed")

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded_b = next(t for t in tasks if t["id"] == task_b["id"])
    assert len(reloaded_b["subtasks"]) == 1
    assert reloaded_b["subtasks"][0]["id"] == done_b["id"]


def test_parent_demoted_to_not_done_when_subtasks_remain(guest_client):
    """Marking the task itself done also marks every subtask done (see
    set_done's cascade) - clearing the completed ones here leaves an
    incomplete one behind, so the parent must drop back to not-done."""
    client, _ = guest_client
    task = _add_task(client)
    _add_subtask(client, task["id"], "One")
    kept = _add_subtask(client, task["id"], "Two")
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})

    # Un-complete just the one we want to survive the clear, so it's the
    # only subtask left incomplete going in.
    client.patch(f"/api/subtasks/{kept['id']}", json={"done": False})

    r = client.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 200
    assert r.json()["parent_done"] is False

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["id"] == task["id"])
    assert reloaded["done"] is False
    assert [s["id"] for s in reloaded["subtasks"]] == [kept["id"]]


def test_parent_done_state_untouched_when_nothing_remains(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    sub = _add_subtask(client, task["id"])
    client.patch(f"/api/subtasks/{sub['id']}", json={"done": True})

    r = client.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 200
    assert r.json()["subtasks"] == []

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["id"] == task["id"])
    assert reloaded["subtasks"] == []


def test_no_done_subtasks_is_a_safe_no_op(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    sub = _add_subtask(client, task["id"])

    r = client.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["subtasks"]] == [sub["id"]]


def test_stranger_cannot_clear_completed_subtasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    _add_subtask(client, task["id"])
    stranger, _ = _second_guest(client)

    r = stranger.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 404


def test_collaborator_can_clear_completed_subtasks(guest_client):
    client, _ = guest_client
    task = _add_task(client, category="Assessment")
    other, _ = _join(client, task["id"])
    done = _add_subtask(client, task["id"], "Done")
    client.patch(f"/api/subtasks/{done['id']}", json={"done": True})

    r = other.post(f"/api/tasks/{task['id']}/subtasks/clear-completed")
    assert r.status_code == 200
    assert r.json()["subtasks"] == []
