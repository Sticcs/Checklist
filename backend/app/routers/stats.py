from fastapi import APIRouter, Depends

from app import crud
from app.models import StatsResponse
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def get_stats(current_user: CurrentUser = Depends(get_current_user)) -> StatsResponse:
    return crud.get_stats(current_user.username)
