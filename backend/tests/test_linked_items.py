from fastapi.testclient import TestClient

from app.main import app


def _second_guest(client):
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


def _add_task(client, text="Task", list_id=None, linked_task_id=None):
    r = client.post(
        "/api/tasks",
        json={
            "text": text,
            "priority": "Medium",
            "category": "General",
            "due_date": None,
            "list_id": list_id,
            "linked_task_id": linked_task_id,
        },
    )
    assert r.status_code == 201
    return r.json()


def _add_subtask(client, task_id, text="Subtask", linked_subtask_id=None):
    r = client.post(
        f"/api/tasks/{task_id}/subtasks",
        json={"text": text, "linked_subtask_id": linked_subtask_id},
    )
    assert r.status_code == 201
    return r.json()["subtask"]


def test_create_task_with_linked_task_id(guest_client):
    client, _ = guest_client
    source = _add_task(client, text="Source task")
    copy = _add_task(client, text="Source task", linked_task_id=source["id"])
    assert copy["linked_task_id"] == source["id"]


def test_create_task_linked_to_someone_elses_task_404s(guest_client):
    client, _ = guest_client
    stranger, _ = _second_guest(client)
    stranger_task = _add_task(stranger, text="Not yours")
    r = client.post(
        "/api/tasks",
        json={
            "text": "Copy",
            "priority": "Medium",
            "category": "General",
            "due_date": None,
            "linked_task_id": stranger_task["id"],
        },
    )
    assert r.status_code == 404


def test_toggling_linked_task_propagates_to_original(guest_client):
    client, _ = guest_client
    source = _add_task(client, text="Source task")
    copy = _add_task(client, text="Source task", linked_task_id=source["id"])

    r = client.patch(f"/api/tasks/{copy['id']}/done", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True

    original = client.get(f"/api/tasks/{source['id']}").json()
    assert original["done"] is True


def test_toggling_original_task_propagates_to_linked_copy(guest_client):
    client, _ = guest_client
    source = _add_task(client, text="Source task")
    copy = _add_task(client, text="Source task", linked_task_id=source["id"])

    r = client.patch(f"/api/tasks/{source['id']}/done", json={"done": True})
    assert r.status_code == 200

    copy_after = client.get(f"/api/tasks/{copy['id']}").json()
    assert copy_after["done"] is True


def test_create_subtask_with_linked_subtask_id(guest_client):
    client, _ = guest_client
    source_task = _add_task(client, text="Source task")
    source_sub = _add_subtask(client, source_task["id"], text="Source subtask")

    target_task = _add_task(client, text="Target task")
    copy_sub = _add_subtask(client, target_task["id"], text="Source subtask", linked_subtask_id=source_sub["id"])
    assert copy_sub["linked_subtask_id"] == source_sub["id"]


def test_create_subtask_linked_to_someone_elses_subtask_404s(guest_client):
    client, _ = guest_client
    stranger, _ = _second_guest(client)
    stranger_task = _add_task(stranger, text="Stranger task")
    stranger_sub = _add_subtask(stranger, stranger_task["id"], text="Stranger subtask")

    target_task = _add_task(client, text="Target task")
    r = client.post(
        f"/api/tasks/{target_task['id']}/subtasks",
        json={"text": "Copy", "linked_subtask_id": stranger_sub["id"]},
    )
    assert r.status_code == 404


def test_toggling_linked_subtask_propagates_both_ways(guest_client):
    client, _ = guest_client
    source_task = _add_task(client, text="Source task")
    source_sub = _add_subtask(client, source_task["id"], text="Source subtask")

    target_task = _add_task(client, text="Target task")
    copy_sub = _add_subtask(client, target_task["id"], text="Source subtask", linked_subtask_id=source_sub["id"])

    r = client.patch(f"/api/subtasks/{copy_sub['id']}", json={"done": True})
    assert r.status_code == 200
    assert r.json()["subtask"]["done"] is True

    source_after = client.get(f"/api/tasks/{source_task['id']}").json()
    source_sub_after = next(s for s in source_after["subtasks"] if s["id"] == source_sub["id"])
    assert source_sub_after["done"] is True

    # And the reverse direction.
    r2 = client.patch(f"/api/subtasks/{source_sub['id']}", json={"done": False})
    assert r2.status_code == 200
    target_after = client.get(f"/api/tasks/{target_task['id']}").json()
    copy_sub_after = next(s for s in target_after["subtasks"] if s["id"] == copy_sub["id"])
    assert copy_sub_after["done"] is False
