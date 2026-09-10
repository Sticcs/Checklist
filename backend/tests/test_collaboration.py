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
    """A second, independent logged-in identity sharing the same test
    database as `client` (the engine is a module-level global keyed off
    settings, set up once by the `client` fixture) but with its own cookie
    jar, so it can act as a different collaborator account."""
    other = TestClient(app)
    r = other.post("/api/auth/guest")
    assert r.status_code == 200
    return other, r.json()["username"]


# ----------------------------- Share-link lifecycle -----------------------------

def test_create_share_link_is_get_or_create(guest_client):
    client, _ = guest_client
    task = _add_task(client)

    r1 = client.post(f"/api/tasks/{task['id']}/share-link")
    assert r1.status_code == 200
    r2 = client.post(f"/api/tasks/{task['id']}/share-link")
    assert r2.status_code == 200
    assert r1.json()["token"] == r2.json()["token"]
    assert r1.json()["url"].endswith(f"/assignment/join/{r1.json()['token']}")


def test_share_link_requires_assessment_category(guest_client):
    client, _ = guest_client
    task = _add_task(client, category="Study")
    r = client.post(f"/api/tasks/{task['id']}/share-link")
    assert r.status_code == 400


def test_share_link_requires_ownership(client):
    client.post("/api/auth/guest")
    task = _add_task(client)
    other, _ = _second_guest(client)
    r = other.post(f"/api/tasks/{task['id']}/share-link")
    assert r.status_code == 404


def test_regenerate_invalidates_the_old_token(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    old_token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]

    new_token = client.post(f"/api/tasks/{task['id']}/share-link/regenerate").json()["token"]
    assert new_token != old_token

    other, _ = _second_guest(client)
    other.post("/api/auth/guest")
    r = other.post(f"/api/assignments/join/{old_token}")
    assert r.status_code == 404
    r = other.post(f"/api/assignments/join/{new_token}")
    assert r.status_code == 200


def test_revoke_clears_the_link_but_keeps_collaborators(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = client.delete(f"/api/tasks/{task['id']}/share-link")
    assert r.status_code == 204

    # Link no longer works for a new joiner...
    third, _ = _second_guest(client)
    r = third.post(f"/api/assignments/join/{token}")
    assert r.status_code == 404

    # ...but the existing collaborator's access is untouched.
    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert [c["username"] for c in collabs] == [other_username]


def test_share_link_requires_desktop_disabled(guest_client, monkeypatch):
    monkeypatch.setattr("app.routers.collaboration.is_desktop_build", lambda: True)
    client, _ = guest_client
    task = _add_task(client)
    r = client.post(f"/api/tasks/{task['id']}/share-link")
    assert r.status_code == 503


# ----------------------------- Join -----------------------------

def test_join_adds_caller_as_collaborator(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]

    other, other_username = _second_guest(client)
    r = other.post(f"/api/assignments/join/{token}")
    assert r.status_code == 200
    assert r.json()["id"] == task["id"]

    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert [c["username"] for c in collabs] == [other_username]


def test_owner_joining_own_link_is_a_noop(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]

    r = client.post(f"/api/assignments/join/{token}")
    assert r.status_code == 200

    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert collabs == []


def test_joining_twice_does_not_duplicate(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)

    other.post(f"/api/assignments/join/{token}")
    other.post(f"/api/assignments/join/{token}")

    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert [c["username"] for c in collabs] == [other_username]


def test_join_invalid_token_404s(guest_client):
    client, _ = guest_client
    r = client.post("/api/assignments/join/not-a-real-token")
    assert r.status_code == 404


def test_join_requires_auth(client):
    r = client.post("/api/assignments/join/some-token")
    assert r.status_code == 401


# ----------------------------- Collaborator access -----------------------------

def test_collaborator_can_toggle_done(guest_client):
    client, owner = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = other.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] is True
    # Persisted under the owner's own task list, not the collaborator's.
    owner_tasks = {t["id"]: t for t in client.get("/api/tasks").json()["tasks"]}
    assert owner_tasks[task["id"]]["done"] is True


def test_collaborator_can_edit_links_and_pages(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = other.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})
    assert r.status_code == 200
    assert r.json()["links"] == [{"name": "Doc", "url": "https://x"}]

    r = other.patch(
        f"/api/tasks/{task['id']}/pages",
        json={"pages": [{"id": "p1", "title": "Page 1", "content": "hello"}]},
    )
    assert r.status_code == 200
    assert r.json()["pages"][0]["content"] == "hello"


def test_collaborator_can_manage_mini_subtasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = other.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Sub 1"})
    assert r.status_code == 201
    subtask_id = r.json()["subtask"]["id"]

    r = other.patch(f"/api/subtasks/{subtask_id}", json={"done": True})
    assert r.status_code == 200

    r = other.delete(f"/api/subtasks/{subtask_id}")
    assert r.status_code == 200


def test_collaborator_cannot_edit_priority_category_or_due_date(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = other.patch(
        f"/api/tasks/{task['id']}",
        json={"text": "Renamed", "priority": "High", "category": "Assessment", "due_date": None},
    )
    assert r.status_code == 404


def test_collaborator_cannot_pin_reposition_notes_urgent_or_in_progress(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    assert other.patch(f"/api/tasks/{task['id']}/pin", json={"pinned": True}).status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/position", json={"position": 5}).status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/notes", json={"notes": "x"}).status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/urgent", json={"urgent": True}).status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/in-progress", json={"in_progress": True}).status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/due-date", json={"due_date": "2030-01-01"}).status_code == 404


def test_collaborator_cannot_delete_reassign_or_manage_sharing(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    assert other.delete(f"/api/tasks/{task['id']}").status_code == 404
    assert other.patch(f"/api/tasks/{task['id']}/assign", json={"assigned_task_id": None}).status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/share-link").status_code == 404
    assert other.post(f"/api/tasks/{task['id']}/share-link/regenerate").status_code == 404
    assert other.delete(f"/api/tasks/{task['id']}/share-link").status_code == 404
    assert other.get(f"/api/tasks/{task['id']}/collaborators").status_code == 404


def test_stranger_cannot_access_the_assignment_at_all(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _second_guest(client)

    assert other.patch(f"/api/tasks/{task['id']}/done", json={"done": True}).status_code == 404
    assert other.get(f"/api/tasks/{task['id']}").status_code == 404


# ----------------------------- Collaborator management -----------------------------

def test_owner_can_remove_any_collaborator(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    r = client.delete(f"/api/tasks/{task['id']}/collaborators/{other_username}")
    assert r.status_code == 204
    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert collabs == []


def test_collaborator_can_remove_only_themselves(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    a, a_username = _second_guest(client)
    b, b_username = _second_guest(client)
    a.post(f"/api/assignments/join/{token}")
    b.post(f"/api/assignments/join/{token}")

    # a tries to remove b - forbidden.
    r = a.delete(f"/api/tasks/{task['id']}/collaborators/{b_username}")
    assert r.status_code == 403

    # a removes themselves - allowed ("leave").
    r = a.delete(f"/api/tasks/{task['id']}/collaborators/{a_username}")
    assert r.status_code == 204

    collabs = client.get(f"/api/tasks/{task['id']}/collaborators").json()["collaborators"]
    assert [c["username"] for c in collabs] == [b_username]


# ----------------------------- Reads -----------------------------

def test_shared_with_me_lists_only_collaborated_tasks(guest_client):
    client, _ = guest_client
    own_task = _add_task(client, text="My own assignment")
    shared_task = _add_task(client, text="Shared assignment")
    token = client.post(f"/api/tasks/{shared_task['id']}/share-link").json()["token"]

    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    other.post("/api/tasks", json={"text": "Unrelated", "priority": "Medium", "category": "Assessment"})

    shared = other.get("/api/tasks/shared-with-me").json()
    assert [t["id"] for t in shared] == [shared_task["id"]]
    assert own_task["id"] not in [t["id"] for t in shared]


def test_single_task_fetch_works_for_owner_and_collaborator_not_strangers(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    collaborator, _ = _second_guest(client)
    collaborator.post(f"/api/assignments/join/{token}")
    stranger, _ = _second_guest(client)

    assert client.get(f"/api/tasks/{task['id']}").status_code == 200
    assert collaborator.get(f"/api/tasks/{task['id']}").status_code == 200
    assert stranger.get(f"/api/tasks/{task['id']}").status_code == 404


def test_share_token_never_appears_on_normal_task_responses(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    client.post(f"/api/tasks/{task['id']}/share-link")

    tasks = client.get("/api/tasks").json()["tasks"]
    assert "share_token" not in tasks[0]
    single = client.get(f"/api/tasks/{task['id']}").json()
    assert "share_token" not in single


# ----------------------------- Cleanup on delete -----------------------------

def test_deleting_the_task_removes_collaborators(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    client.delete(f"/api/tasks/{task['id']}")

    assert other.get(f"/api/tasks/{task['id']}").status_code == 404
    assert other.get("/api/tasks/shared-with-me").json() == []


def test_clearing_completed_removes_collaborators_for_cleared_tasks(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    token = client.post(f"/api/tasks/{task['id']}/share-link").json()["token"]
    other, _ = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")

    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    client.post("/api/tasks/clear-completed")

    assert other.get("/api/tasks/shared-with-me").json() == []
