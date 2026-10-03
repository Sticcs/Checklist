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


def _join(client, task_id):
    token = client.post(f"/api/tasks/{task_id}/share-link").json()["token"]
    other, other_username = _second_guest(client)
    other.post(f"/api/assignments/join/{token}")
    return other, other_username


# ----------------------------- Last edited by -----------------------------

def test_last_edited_is_null_on_a_fresh_task(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    assert task["last_edited_by"] is None
    assert task["last_edited_at"] is None


def test_last_edited_set_by_owner_on_done_toggle(guest_client):
    client, username = guest_client
    task = _add_task(client)
    r = client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert r.json()["last_edited_by"] == username
    assert r.json()["last_edited_at"]


def test_last_edited_set_by_collaborator_on_links_edit(guest_client):
    client, owner_username = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])

    other.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})

    # The owner's own fetch reflects the collaborator's edit, not their own.
    reloaded = client.get(f"/api/tasks/{task['id']}").json()
    assert reloaded["last_edited_by"] == other_username
    assert reloaded["last_edited_by"] != owner_username


def test_last_edited_set_on_subtask_changes(guest_client):
    client, username = guest_client
    task = _add_task(client)

    add = client.post(f"/api/tasks/{task['id']}/subtasks", json={"text": "Step 1"})
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == username

    subtask_id = add.json()["subtask"]["id"]
    client.delete(f"/api/subtasks/{subtask_id}")
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == username


def test_last_edited_survives_undo_of_an_unrelated_action(guest_client):
    client, username = guest_client
    task = _add_task(client, text="Essay")
    client.patch(f"/api/tasks/{task['id']}/done", json={"done": True})
    assert client.get(f"/api/tasks/{task['id']}").json()["last_edited_by"] == username

    # An unrelated mutation - its undo snapshot is what actually gets
    # restored below, not anything to do with last_edited_by itself.
    client.post("/api/tasks", json={"text": "Task B", "priority": "Medium", "category": "General"})
    r = client.post("/api/undo")
    assert r.status_code == 200

    reloaded = client.get(f"/api/tasks/{task['id']}").json()
    assert reloaded["last_edited_by"] == username


# ----------------------------- Hide/unhide own links -----------------------------

def test_adder_can_hide_and_unhide_their_own_link(guest_client):
    client, username = guest_client
    task = _add_task(client)
    add = client.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})
    link = add.json()["links"][0]
    assert link["added_by"] == username

    r = client.patch(f"/api/tasks/{task['id']}/links/{link['id']}/hidden", json={"hidden": True})
    assert r.status_code == 200
    hidden_link = next(l for l in r.json()["links"] if l["id"] == link["id"])
    assert hidden_link["hidden"] is True

    r2 = client.patch(f"/api/tasks/{task['id']}/links/{link['id']}/hidden", json={"hidden": False})
    assert next(l for l in r2.json()["links"] if l["id"] == link["id"])["hidden"] is False


def test_hidden_link_is_invisible_to_other_collaborators_but_visible_to_adder(guest_client):
    client, owner_username = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])

    add = other.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})
    link = add.json()["links"][0]
    assert link["added_by"] == other_username

    other.patch(f"/api/tasks/{task['id']}/links/{link['id']}/hidden", json={"hidden": True})

    # The owner (not the adder) no longer sees the link at all.
    owner_view = client.get(f"/api/tasks/{task['id']}").json()
    assert owner_view["links"] == []

    # The adder still sees their own hidden link.
    adder_view = other.get(f"/api/tasks/{task['id']}").json()
    assert len(adder_view["links"]) == 1
    assert adder_view["links"][0]["hidden"] is True


def test_only_the_adder_can_hide_their_link(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    add = client.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})
    link = add.json()["links"][0]

    r = other.patch(f"/api/tasks/{task['id']}/links/{link['id']}/hidden", json={"hidden": True})
    assert r.status_code == 403


def test_hide_nonexistent_link_is_404(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    r = client.patch(f"/api/tasks/{task['id']}/links/not-a-real-id/hidden", json={"hidden": True})
    assert r.status_code == 404


def test_editing_links_does_not_destroy_another_collaborators_hidden_link(guest_client):
    """update_task_links is a whole-array replacement endpoint, but each
    viewer only ever sees their own filtered view - submitting that back
    verbatim must not silently delete a link someone else has hidden from
    them (see routers/tasks.py's update_task_links)."""
    client, owner_username = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])

    hidden = other.patch(
        f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Private", "url": "https://x"}]}
    ).json()["links"][0]
    other.patch(f"/api/tasks/{task['id']}/links/{hidden['id']}/hidden", json={"hidden": True})

    # The owner can't even see "Private" - adds their own link instead,
    # submitting what they believe is the complete list.
    client.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Public", "url": "https://y"}]})

    # The adder's hidden link must have survived that unrelated edit.
    adder_view = other.get(f"/api/tasks/{task['id']}").json()
    names = {l["name"] for l in adder_view["links"]}
    assert names == {"Public", "Private"}


def test_list_tasks_filters_hidden_links_for_the_owner(guest_client):
    client, owner_username = guest_client
    task = _add_task(client)
    other, _ = _join(client, task["id"])

    add = other.patch(f"/api/tasks/{task['id']}/links", json={"links": [{"name": "Doc", "url": "https://x"}]})
    link = add.json()["links"][0]
    other.patch(f"/api/tasks/{task['id']}/links/{link['id']}/hidden", json={"hidden": True})

    tasks = client.get("/api/tasks").json()["tasks"]
    reloaded = next(t for t in tasks if t["id"] == task["id"])
    assert reloaded["links"] == []
