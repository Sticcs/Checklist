from fastapi import APIRouter, HTTPException, status

from app import crud
from app.models import PublicItemDoneUpdate, PublicListResponse

# The app's only unauthenticated routes - no Depends(get_current_user)
# anywhere in this file. A list's share_token (see lists_table in db.py) is
# the sole credential; anyone holding a valid one can view and check items
# off with no login of any kind, by design (see the user-confirmed scoping
# for this feature). Every function this router calls into
# (crud.get_public_list_items/toggle_public_list_item) re-derives item
# membership from the resolved list row itself, never trusting a client-
# supplied id in isolation - see toggle_public_list_item's docstring for why
# that's the actual security boundary here.
router = APIRouter(prefix="/api/public/lists", tags=["public"])


def _require_list(token: str) -> dict:
    list_row = crud.get_list_by_share_token(token)
    if list_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has been revoked")
    return list_row


@router.get("/{token}", response_model=PublicListResponse)
def get_public_list(token: str) -> PublicListResponse:
    list_row = _require_list(token)
    items = crud.get_public_list_items(list_row)
    return PublicListResponse(list_name=list_row["name"], items=items)


@router.patch("/{token}/items/{item_id}", response_model=PublicListResponse)
def update_public_list_item(token: str, item_id: int, body: PublicItemDoneUpdate) -> PublicListResponse:
    list_row = _require_list(token)
    crud.toggle_public_list_item(list_row, item_id, body.done)
    # Return the fresh list either way - a no-op toggle (item_id didn't
    # actually belong to this list) just gets back the unchanged list rather
    # than an error, so a stranger probing ids learns nothing about whether
    # that id exists anywhere else.
    items = crud.get_public_list_items(list_row)
    return PublicListResponse(list_name=list_row["name"], items=items)
