from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.config import settings
from app.models import CollaboratorsResponse, ShareLinkResponse, Task
from app.paths import is_desktop_build
from app.security import CurrentUser, get_current_user

router = APIRouter(tags=["collaboration"])

# Collaboration is scoped to Assignments only (category == "Assessment") -
# the main task list, Shopping, and every other category have no sharing
# concept. Matches ASSESSMENT_CATEGORY on the frontend (frontend/src/constants.ts).
ASSESSMENT_CATEGORY = "Assessment"


def _require_owned_assignment(task_id: int, username: str) -> dict:
    task = crud.get_task(task_id, username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if task["category"] != ASSESSMENT_CATEGORY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only Assignments can be shared")
    return task


def _require_desktop_disabled() -> None:
    # The desktop build's local server reads/writes its own local SQLite
    # file, entirely separate from the deployed Postgres database - a token
    # minted here wouldn't exist on the server a recipient's link would hit,
    # so this isn't a reachability problem fixable by URL rewriting. See
    # frontend's useIsDesktopApp() for the matching UI-side gate.
    if is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sharing isn't available in the desktop app")


def _share_url(token: str) -> str:
    return f"{settings.public_base_url}/assignment/join/{token}"


@router.post("/api/tasks/{task_id}/share-link", response_model=ShareLinkResponse)
def create_share_link(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> ShareLinkResponse:
    _require_desktop_disabled()
    _require_owned_assignment(task_id, current_user.username)
    token = crud.get_or_create_share_token(task_id, current_user.username)
    return ShareLinkResponse(token=token, url=_share_url(token))


@router.post("/api/tasks/{task_id}/share-link/regenerate", response_model=ShareLinkResponse)
def regenerate_share_link(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> ShareLinkResponse:
    _require_desktop_disabled()
    _require_owned_assignment(task_id, current_user.username)
    token = crud.regenerate_share_token(task_id, current_user.username)
    return ShareLinkResponse(token=token, url=_share_url(token))


@router.delete("/api/tasks/{task_id}/share-link", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    _require_owned_assignment(task_id, current_user.username)
    crud.revoke_share_link(task_id, current_user.username)


@router.get("/api/tasks/{task_id}/collaborators", response_model=CollaboratorsResponse)
def get_collaborators(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> CollaboratorsResponse:
    _require_owned_assignment(task_id, current_user.username)
    return CollaboratorsResponse(collaborators=crud.list_collaborators(task_id))


@router.delete("/api/tasks/{task_id}/collaborators/{username}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collaborator(
    task_id: int, username: str, current_user: CurrentUser = Depends(get_current_user)
) -> None:
    # Owner can remove anyone; a collaborator can only remove themselves
    # ("leave"). get_task_for_user (not get_task) so a collaborator leaving
    # their own access doesn't 404 before the owner-vs-self check even runs.
    task = crud.get_task_for_user(task_id, current_user.username)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    is_owner = task["username"] == current_user.username
    if not is_owner and username != current_user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only remove yourself")
    crud.remove_collaborator(task_id, username)


@router.post("/api/assignments/join/{token}", response_model=Task)
def join_assignment(token: str, current_user: CurrentUser = Depends(get_current_user)) -> Task:
    task = crud.get_task_by_share_token(token)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This share link is invalid or has been revoked")
    if task["username"] != current_user.username:
        # Idempotent - add_collaborator dedupes, so joining twice (or
        # re-opening the same link later) is a no-op, not an error.
        crud.add_collaborator(task["id"], current_user.username)
    task["subtasks"] = crud.get_subtasks(task["id"])
    return task
