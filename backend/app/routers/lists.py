from fastapi import APIRouter, Depends, HTTPException, status

from app import crud
from app.config import settings
from app.models import ListEntry, ListRenameUpdate, ListShareLinkResponse, ListsResponse
from app.paths import is_desktop_build
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _require_desktop_disabled() -> None:
    # Same reasoning as routers/collaboration.py's helper of the same name -
    # the desktop build's local SQLite is unreachable from a public URL, so
    # a token minted there is useless regardless of URL. Kept as its own
    # small copy rather than promoted into app/paths.py, which desktop.py
    # also imports outside any FastAPI request context.
    if is_desktop_build():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sharing isn't available in the desktop app")


def _entry(row: dict) -> ListEntry:
    return ListEntry(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        position=row["position"],
        has_share_link=bool(row.get("share_token")),
    )


def _share_url(token: str) -> str:
    return f"{settings.public_base_url}/list/{token}"


@router.get("", response_model=ListsResponse)
def get_lists(current_user: CurrentUser = Depends(get_current_user)) -> ListsResponse:
    return ListsResponse(lists=[_entry(r) for r in crud.get_lists(current_user.username)])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ListEntry)
def create_list(current_user: CurrentUser = Depends(get_current_user)) -> ListEntry:
    return _entry(crud.create_list(current_user.username))


@router.patch("/{list_id}", response_model=ListEntry)
def rename_list(
    list_id: int, body: ListRenameUpdate, current_user: CurrentUser = Depends(get_current_user)
) -> ListEntry:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is required")
    row = crud.rename_list(list_id, current_user.username, name)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return _entry(row)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    # Deletes a custom list outright (row + its tasks); for the built-in
    # Shopping list, clears its items but keeps the row - see
    # crud.delete_or_clear_list.
    if not crud.delete_or_clear_list(list_id, current_user.username):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")


@router.post("/{list_id}/share-link", response_model=ListShareLinkResponse)
def create_share_link(
    list_id: int, current_user: CurrentUser = Depends(get_current_user)
) -> ListShareLinkResponse:
    _require_desktop_disabled()
    token = crud.get_or_create_list_share_token(list_id, current_user.username)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return ListShareLinkResponse(token=token, url=_share_url(token))


@router.post("/{list_id}/share-link/regenerate", response_model=ListShareLinkResponse)
def regenerate_share_link(
    list_id: int, current_user: CurrentUser = Depends(get_current_user)
) -> ListShareLinkResponse:
    _require_desktop_disabled()
    token = crud.regenerate_list_share_token(list_id, current_user.username)
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return ListShareLinkResponse(token=token, url=_share_url(token))


@router.delete("/{list_id}/share-link", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(list_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    if not crud.revoke_list_share_link(list_id, current_user.username):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
