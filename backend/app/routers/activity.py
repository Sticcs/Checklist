from fastapi import APIRouter, Depends

from app import crud
from app.models import ActivityEntry
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=list[ActivityEntry])
def list_activity(
    limit: int = 15, current_user: CurrentUser = Depends(get_current_user)
) -> list[ActivityEntry]:
    return crud.get_activity_log(current_user.username, limit=limit)
