from fastapi.testclient import TestClient

from app import crud
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


def _add_page(client, task_id, title="Page 1"):
    r = client.post(f"/api/tasks/{task_id}/pages", json={"title": title})
    assert r.status_code == 201
    return r.json()["pages"][-1]["id"]


def _set_page_content(client, task_id, page_id, content):
    pages = client.get(f"/api/tasks/{task_id}").json()["pages"]
    updated = [{**p, "content": content} if p["id"] == page_id else p for p in pages]
    r = client.patch(f"/api/tasks/{task_id}/pages", json={"pages": updated})
    assert r.status_code == 200
    return r.json()


def test_no_version_recorded_for_a_page_never_persisted_before(guest_client):
    """A legacy/fresh task's pages column is still genuinely empty until
    the very first pages save - a page id appearing for the first time in
    that save (e.g. the implicit "page-1" synthesized client-side) has
    nothing to diff against, so it's not worth a version entry. Hits
    set_task_pages directly (not via _add_page, which would already have
    persisted the page with empty content first)."""
    client, _ = guest_client
    task = _add_task(client)
    assert task["pages"] == []

    r = client.patch(
        f"/api/tasks/{task['id']}/pages",
        json={"pages": [{"id": "page-1", "title": "Page 1", "content": "First draft"}]},
    )
    assert r.status_code == 200

    versions = client.get(f"/api/tasks/{task['id']}/pages/page-1/versions").json()["versions"]
    assert versions == []

    # A *second* save, now that the page genuinely has a prior state to
    # diff against, does record one.
    client.patch(
        f"/api/tasks/{task['id']}/pages",
        json={"pages": [{"id": "page-1", "title": "Page 1", "content": "Second draft"}]},
    )
    versions = client.get(f"/api/tasks/{task['id']}/pages/page-1/versions").json()["versions"]
    assert len(versions) == 1


def test_editing_an_existing_pages_content_records_a_version(guest_client):
    client, username = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])  # persists with content=""
    _set_page_content(client, task["id"], page_id, "First real content")

    r = client.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions")
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["actor_username"] == username


def test_rapid_saves_by_same_actor_coalesce_into_one_version(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])
    _set_page_content(client, task["id"], page_id, "Draft 1")
    _set_page_content(client, task["id"], page_id, "Draft 2")
    _set_page_content(client, task["id"], page_id, "Draft 3")

    r = client.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions")
    versions = r.json()["versions"]
    assert len(versions) == 1

    # The coalesced entry stays frozen at whichever save first created it -
    # "Draft 2"/"Draft 3" are just skipped, not merged in. A checkpoint that
    # kept drifting to match current content could never actually restore
    # you to "before this editing session".
    full = client.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions/{versions[0]['id']}")
    assert full.json()["content"] == "Draft 1"


def test_restore_overwrites_current_content_and_is_undoable(guest_client, monkeypatch):
    from app import crud as crud_module

    client, _ = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])
    _set_page_content(client, task["id"], page_id, "Original content")

    monkeypatch.setattr(crud_module, "PAGE_VERSION_GAP_SECONDS", -1)
    _set_page_content(client, task["id"], page_id, "Changed content")

    versions = client.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions").json()["versions"]
    old_version_id = versions[-1]["id"]  # oldest - "Original content"

    r = client.post(f"/api/tasks/{task['id']}/pages/{page_id}/versions/{old_version_id}/restore")
    assert r.status_code == 200
    restored_page = next(p for p in r.json()["pages"] if p["id"] == page_id)
    assert restored_page["content"] == "Original content"

    undo_r = client.post("/api/undo")
    assert undo_r.status_code == 200
    after_undo = client.get(f"/api/tasks/{task['id']}").json()
    reverted_page = next(p for p in after_undo["pages"] if p["id"] == page_id)
    assert reverted_page["content"] == "Changed content"


def test_restore_nonexistent_version_is_404(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])
    r = client.post(f"/api/tasks/{task['id']}/pages/{page_id}/versions/999999/restore")
    assert r.status_code == 404


def test_deleting_a_page_deletes_its_version_history(guest_client, monkeypatch):
    from app import crud as crud_module

    client, _ = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])
    _set_page_content(client, task["id"], page_id, "Draft 1")
    monkeypatch.setattr(crud_module, "PAGE_VERSION_GAP_SECONDS", -1)
    _set_page_content(client, task["id"], page_id, "Draft 2")
    assert client.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions").json()["versions"]

    client.delete(f"/api/tasks/{task['id']}/pages/{page_id}")

    assert crud.list_page_versions(task["id"], page_id, "irrelevant") == []


def test_collaborator_can_see_and_restore_versions(guest_client, monkeypatch):
    from app import crud as crud_module

    client, _ = guest_client
    task = _add_task(client)
    other, other_username = _join(client, task["id"])
    page_id = _add_page(client, task["id"])
    _set_page_content(client, task["id"], page_id, "Owner's draft")
    monkeypatch.setattr(crud_module, "PAGE_VERSION_GAP_SECONDS", -1)
    _set_page_content(other, task["id"], page_id, "Collaborator's edit")

    r = other.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions")
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert any(v["actor_username"] != other_username for v in versions)

    restore_r = other.post(f"/api/tasks/{task['id']}/pages/{page_id}/versions/{versions[-1]['id']}/restore")
    assert restore_r.status_code == 200


def test_stranger_cannot_see_versions(guest_client):
    client, _ = guest_client
    task = _add_task(client)
    page_id = _add_page(client, task["id"])
    stranger, _ = _second_guest(client)
    r = stranger.get(f"/api/tasks/{task['id']}/pages/{page_id}/versions")
    assert r.status_code == 404
